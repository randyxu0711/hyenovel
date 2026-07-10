"""確定性編排器:把 story-critique SKILL.md 的手動流程寫成程式。

流程(控制流 100% 是這裡的 Python,LLM 只在派 analyst / criticizer 兩格):
  派 analyst ─▶ 閘門(viz.py --check 子行程)─ 失敗→帶錯重派(retry N)
  派 criticizer ─▶ 閘門 ─ 失敗→重派
  render.py + viz.py + index.py(純 Python,零 LLM)─▶ viz.json / md / index.json

閘門用「子行程」而非 in-process import:viz.py 內 read_json/load 在壞輸入時 sys.exit,
直接 import 呼叫會打死 server worker;子行程把失敗隔離成 exit code,順便原封重用閘門。

對外是 async generator,yield 統一事件信封 {event, data}:
  phase  {name, status:start|ok|retry|fail, attempt, detail?}
  done   {ok, cost_usd, artifacts[]}
  error  {where, message, recoverable}
"""
import asyncio
import subprocess
import sys

from claude_agent_sdk import ClaudeSDKClient

from . import config, sdk_runner
from .log import log, setup


def _run_py(args: list[str]) -> subprocess.CompletedProcess:
    """以本 venv 的 python 跑專案腳本(子行程隔離 sys.exit / jsonschema 依賴)。"""
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True, text=True, cwd=str(config.ROOT),
    )


def _gate(slug: str) -> tuple[bool, str]:
    """跑 viz.py <slug> --check:① schema ② 逐字引用。回 (通過?, 失敗明細 stdout)。
    注意:viz.py 把 feedback.json 當「可選」(同一閘門也用在 analyst 階段,當時還沒 feedback),
    所以這個閘門對「feedback 不存在」會「通過」。criticizer 階段須改用 _gate_feedback。"""
    p = _run_py([str(config.ROOT / "viz.py"), slug, "--check"])
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def _gate_feedback(slug: str) -> tuple[bool, str]:
    """criticizer 階段專用:先確認 feedback.json 真的被產出來,再跑共用閘門。
    沒這道,criticizer 沒寫檔時 _gate 會『空過』,orchestrator 會誤判成功並渲染出無回饋的結果。"""
    fp = config.STORIES / slug / "feedback.json"
    if not fp.exists():
        return False, (f"feedback.json 沒有被產生出來。請用 Write 工具實際寫出 "
                       f"stories/{slug}/feedback.json 檔案(不是只回報摘要)。")
    return _gate(slug)


async def _drive_phase(name, run_one, gate_fn, slug, first_prompt, retry_prompt):
    """一格的重試核心(與 client 解耦、可測)。run_one(prompt)->TurnResult 由呼叫者注入。
    三路:容量瞬時→有界退避(不佔 gate 額度);容量硬失敗→fail-fast 帶 resets_at;
    內容失敗→修正 prompt 重派(原行為)。"""
    cost = 0.0
    detail = ""
    ok = False
    transient = 0
    attempt = 0
    while attempt <= config.MAX_GATE_RETRIES:
        yield ("event", {"event": "phase", "data": {"name": name, "status": "start", "attempt": attempt}})
        log.info(f"phase={name} status=start attempt={attempt}")
        prompt = first_prompt if attempt == 0 else retry_prompt(detail)
        r = await run_one(prompt)
        cost += r.cost

        cap = sdk_runner._capacity_failure(r)
        if cap == "transient" and transient < config.TRANSIENT_MAX_RETRIES:
            transient += 1
            log.warning(f"phase={name} status=retry attempt={attempt} api_error={r.api_error_status} (overloaded)")
            yield ("event", {"event": "phase", "data": {
                "name": name, "status": "retry", "attempt": attempt,
                "detail": f"服務過載({r.api_error_status}),退避重試"}})
            await asyncio.sleep(config.BACKOFF_BASE * 2 ** transient)
            continue                                  # 不推進 attempt(不吃 gate 額度)
        if cap is not None:                           # "hard" 或 transient 耗盡
            resets = r.rate_limit.resets_at if r.rate_limit else None
            log.error(f"phase={name} status=fail reason=usage-limit resets_at={resets}")
            yield ("result", {"ok": False, "cost": cost, "reason": "usage-limit", "resets_at": resets})
            return

        gate_ok, detail = await asyncio.to_thread(gate_fn, slug)
        if gate_ok:
            ok = True
            yield ("event", {"event": "phase", "data": {"name": name, "status": "ok", "attempt": attempt}})
            log.info(f"phase={name} status=ok attempt={attempt}")
            break
        # 不把 detail(閘門 stdout)入 log:可能夾帶 analyst 逐字引用/欄位值,守 safe-to-log。
        log.warning(f"phase={name} status=retry attempt={attempt} (gate-fail)")
        yield ("event", {"event": "phase", "data": {
            "name": name, "status": "retry", "attempt": attempt, "detail": detail[:800]}})
        attempt += 1
    # reason 與硬上限路徑(line 上方 usage-limit)對稱:耗盡=閘門始終沒過(gate),成功=None。
    yield ("result", {"ok": ok, "cost": cost, "reason": None if ok else "gate"})


async def _phase_with_retry(name, first_prompt, retry_prompt, slug, gate_fn=_gate, on_client=None):
    """一格「直接跑 agent → 過閘門 → 失敗重派」的確定性迴圈。

    name 即 .claude/agents/<name>.md:把該 agent 的 body 當 system_prompt、直接當主代理跑,
    沒有協調者、沒有 Task 巢狀。每格用**自己一個** ClaudeSDKClient(觀察/判斷隔離——
    criticizer 不該看到 analyst 那格的 context)。run_turn 等到 ResultMessage 才返回,且包
    wait_for 逾時。重試仍在同格 client 內,讓代理保有「剛剛做了什麼」的 context。
    gate_fn 回 (通過?, 失敗明細)。

    on_client(client|None):把當前 client 回報給上層(critique.Run),讓「取消」能直接
    disconnect 它、確實收掉 claude 子行程——光靠 task.cancel() 會在 __aexit__ 期間漏掉。"""
    async with ClaudeSDKClient(options=sdk_runner.agent_options(name)) as client:
        if on_client:
            on_client(client)
        try:
            async def run_one(prompt):
                return await asyncio.wait_for(
                    sdk_runner.run_turn(client, prompt), timeout=config.PHASE_TIMEOUT)
            async for item in _drive_phase(name, run_one, gate_fn, slug, first_prompt, retry_prompt):
                yield item
        finally:
            if on_client:
                on_client(None)


def _phase_error(where: str, gate_noun: str, res: dict) -> dict:
    """把一格失敗的 res 轉成統一 error 事件(analyst / criticizer 共用,免兩處重複)。
    usage-limit → 可恢復、帶 resets_at;其餘(閘門耗盡)→ 不可恢復、帶對應 gate 名詞。"""
    if res.get("reason") == "usage-limit":
        data = {"where": where, "message": "撞到訂閱用量上限,稍後再跑",
                "recoverable": True, "reason": "usage-limit", "resets_at": res.get("resets_at")}
    else:
        data = {"where": where, "message": f"{gate_noun} 閘門重試後仍未過", "recoverable": False}
    return {"event": "error", "data": data}


async def run_critique(slug: str, on_client=None):
    # 縱深防禦:slug 會拼路徑、也會當 argv 餵子行程(viz/render/index)。
    # API 邊界已擋,這裡再守一道(本函式也可被直接呼叫)。
    if not config.valid_slug(slug):
        yield {"event": "error", "data": {"where": "input",
               "message": "不合法的 slug", "recoverable": False}}
        return
    src = config.STORIES / slug / "source.md"
    if not src.exists():
        yield {"event": "error", "data": {"where": "input",
               "message": f"找不到 stories/{slug}/source.md", "recoverable": False}}
        return

    setup()
    total_cost = 0.0
    stage = "analyst"          # 目前跑到哪格;逾時報錯時標對階段
    try:
        # ── 第一格:analyst(自己一個協調者 client)──
        ana_first = (f"分析 stories/{slug}/:讀 source.md 與 schemas/analysis.schema.json,"
                     f"用 Write 工具產出 stories/{slug}/analysis.json。只回報簡短摘要。")
        ana_retry = lambda d: (f"analysis.json 沒過閘門:\n{d}\n"
                               f"請修正 stories/{slug}/analysis.json"
                               f"(逐字引用須對得上 source.md、符合 schema),用 Write 工具寫回。")
        res = None
        async for kind, payload in _phase_with_retry("analyst", ana_first, ana_retry, slug, on_client=on_client):
            if kind == "event":
                yield payload
            else:
                res = payload
        total_cost += res["cost"]
        if not res["ok"]:
            yield _phase_error("analyst", "analysis", res)
            return

        # ── 第二格:criticizer(另一個 client,隔離;閘門要求 feedback.json 真的存在)──
        stage = "criticizer"
        cri_first = (f"讀 stories/{slug}/analysis.json、source.md、schemas/feedback.schema.json,"
                     f"用 Write 工具產出 stories/{slug}/feedback.json"
                     f"(發展性、有輕重、不諂媚,每點掛逐字 quotes、refs 綁 node id)。只回報摘要。")
        cri_retry = lambda d: (f"feedback.json 沒過閘門:\n{d}\n"
                               f"請修正 stories/{slug}/feedback.json,用 Write 工具寫回。")
        res = None
        async for kind, payload in _phase_with_retry("criticizer", cri_first, cri_retry, slug,
                                                     gate_fn=_gate_feedback, on_client=on_client):
            if kind == "event":
                yield payload
            else:
                res = payload
        total_cost += res["cost"]
        if not res["ok"]:
            yield _phase_error("criticizer", "feedback", res)
            return
    except asyncio.TimeoutError:
        label = {"analyst": "分析(analyst)", "criticizer": "評論(criticizer)"}[stage]
        yield {"event": "error", "data": {"where": "timeout",
               "message": f"{label}階段逾時(> {config.PHASE_TIMEOUT}s)",
               "recoverable": False, "reason": "timeout"}}
        return
    except Exception as e:
        yield {"event": "error", "data": {"where": "sdk", "message": str(e),
               "recoverable": False, "reason": sdk_runner.classify_failure(str(e))}}
        return

    # ── 確定性層:render + viz + index(純 Python,無 LLM)──
    yield {"event": "phase", "data": {"name": "render", "status": "start"}}
    render = await asyncio.to_thread(_run_py, [str(config.ROOT / "render.py"), slug])
    viz = await asyncio.to_thread(_run_py, [str(config.ROOT / "viz.py"), slug])
    index = await asyncio.to_thread(_run_py, [str(config.ROOT / "index.py")])
    for label, proc in (("render", render), ("viz", viz), ("index", index)):
        if proc.returncode != 0:
            yield {"event": "error", "data": {"where": "render",
                   "message": f"{label}: " + (proc.stdout + proc.stderr)[:800], "recoverable": False}}
            return
    yield {"event": "phase", "data": {"name": "render", "status": "ok"}}
    yield {"event": "done", "data": {"ok": True, "cost_usd": round(total_cost, 4),
           "artifacts": ["viz.json", "feedback.md", "analysis.md", "index.json"]}}
