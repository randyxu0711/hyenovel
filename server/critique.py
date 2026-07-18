"""Critique 執行治理:把一次分析跑成「獨立背景任務」,與 HTTP 連線解耦。

問題:舊版把 orchestrator 直接掛在 SSE 連線上——前端一重整,連線斷了,
但背景那支 claude 還在跑(燒訂閱),前端既看不到也停不掉。

解法:每個 slug 一個 Run = 一條 asyncio.Task 跑 orchestrator,事件寫進
緩衝並廣播給所有訂閱者。連線只是「訂閱者」,斷了不影響 Run;重整後可:
  - GET  /api/critique/running   查還在跑的
  - POST /api/critique/{slug}    重新接上(補播已發事件 → 繼續直播)
  - DELETE /api/critique/{slug}  取消(cancel Task → orchestrator 的
                                  ClaudeSDKClient __aexit__ 收掉 claude 行程)
"""
import asyncio
import shutil
import time

import runstate

from . import config, ledger, orchestrator, sdk_runner
from .log import log

# phase name → 生長階(給 /running 顯示、前端成形動畫對齊)
_STEP = {"analyst": 1, "criticizer": 2, "render": 3}
_STAGE_OF_STEP = {1: "analyst", 2: "criticizer", 3: "render", 4: "done"}
_DONE_TTL = 600   # 已結束的 Run 留多久(秒)讓晚到的重整還接得到 done


class Run:
    def __init__(self, slug: str, title: str, fresh: bool = False):
        self.slug = slug
        self.title = title
        self.fresh = fresh                            # 本 Run 是「新孕育」嗎?只有 fresh 取消才清檔(見 _discard_story)
        self.dir = config.STORIES / slug             # 綁定一次;取消刪檔只認這個 Path,不再吃字串
        self.events: list[dict] = []                 # 已發事件(補播用)
        self.subscribers: set[asyncio.Queue] = set()
        self.status = "running"                       # running|done|error|cancelled
        self.step = 0
        self.stage_name = "analyst"                   # 給 run.json 的 stage
        self.reason = None
        self.resets_at = None
        self.cost = 0.0
        self.reanalyze = False                        # 本 Run 是「重新分析」嗎?done 才丟棄 .prev(見 _drive)
        self.task: asyncio.Task | None = None
        self.client = None                            # 當前 ClaudeSDKClient(取消時直接 disconnect)
        self.finished = asyncio.Event()
        self.started = time.time()


_runs: dict[str, Run] = {}


def list_running() -> list[dict]:
    return [{"slug": r.slug, "title": r.title, "status": r.status, "step": r.step}
            for r in _runs.values() if r.status == "running"]


def _persist(run: Run) -> None:
    """把 Run 當前狀態同步寫進 run.json(轉態時呼叫)。cost 以 ledger 累計為準。
    run.status 維持既有 SSE 詞彙(running|done|error|cancelled);run.json 另外把
    error 依 reason 映成 paused(usage-limit)/failed(其餘),二者詞彙刻意不同源。"""
    agg = ledger.aggregate(run.slug)
    cost = agg.get("last_run_cost_usd", 0.0) if not agg.get("empty") else run.cost
    if run.status == "error":
        rj_status = "paused" if run.reason == "usage-limit" else "failed"
    else:
        rj_status = run.status          # running | done
    runstate.write(run.dir, status=rj_status, stage=run.stage_name,
                   reason=run.reason, resets_at=run.resets_at,
                   title=run.title, cost_usd=cost)


def _record(run: Run, ev: dict):
    """記一個事件:更新狀態/相位,並廣播給所有訂閱者(同步,無 await → 對事件迴圈原子)。"""
    run.events.append(ev)
    kind = ev.get("event")
    data = ev.get("data", {})
    if kind == "phase":
        step = _STEP.get(data.get("name"), 0)
        if data.get("status") == "ok":
            step += 1
        run.step = max(run.step, step)
        if data.get("status") == "ok":
            run.stage_name = _STAGE_OF_STEP.get(run.step, run.stage_name)
            _persist(run)                                   # 推進才寫
    elif kind == "done":
        run.status = "done"
        run.cost = data.get("cost_usd", run.cost)
        run.step = 4
        run.stage_name = "done"
        _persist(run)
    elif kind == "error":
        run.cost = data.get("cost_usd", run.cost)   # 失敗也記已花的錢(F3),不讓成本消失
        run.reason = data.get("reason")
        run.resets_at = data.get("resets_at")
        if run.status == "running":
            run.status = "error"
        _persist(run)
    for q in list(run.subscribers):
        q.put_nowait(ev)


async def _drive(run: Run):
    """背景跑 orchestrator,把事件灌進緩衝/廣播。獨立於任何 HTTP 連線。"""
    def _hold(c):
        run.client = c
    try:
        async for ev in orchestrator.run_critique(run.slug, on_client=_hold):
            _record(run, ev)
    except asyncio.CancelledError:
        if run.status == "running":
            run.status = "cancelled"
        _record(run, {"event": "error",
                      "data": {"where": "cancel", "message": "已取消", "recoverable": False}})
        raise
    except Exception as e:  # noqa: BLE001 —— 任何意外都收斂成 error 事件,不讓 Task 默默死掉
        # 取消會先 disconnect client,使 receive 拋連線錯誤而非 CancelledError;
        # 已標記 cancelled 就別覆蓋成 error(那是取消的預期後果,非意外 → 不記 traceback)。
        if run.status == "running":
            log.exception(f"event=unexpected slug={run.slug}")
            run.status = "error"
            _record(run, {"event": "error",
                          "data": {"where": "run", "message": str(e), "recoverable": False,
                                   "reason": sdk_runner.classify_failure(str(e))}})
        else:
            _record(run, {"event": "error",
                          "data": {"where": "cancel", "message": "已取消", "recoverable": False}})
    finally:
        run.client = None
        if run.reanalyze and run.status == "done":
            runstate.discard_prev(run.dir)    # commit;失敗則保留 .prev(退路)
        run.finished.set()
        for q in list(run.subscribers):
            q.put_nowait(None)   # 串流結束哨兵


def start(slug: str, title: str, fresh: bool = False) -> Run:
    """開一個 Run;若該 slug 已在跑就回既有的(避免重整/重送造成雙重派工燒錢)。
    fresh=新孕育(取消時可清掉剛 ingest 的孤兒);重整/重接的既有 Run 保有原 fresh 值。"""
    if not config.valid_slug(slug):
        raise ValueError(f"invalid slug: {slug!r}")   # Run 只為合法 slug 存在 → run.dir 必為 STORIES 直下單段
    cur = _runs.get(slug)
    if cur and cur.status == "running":
        return cur
    run = Run(slug, title or (cur.title if cur else slug), fresh=fresh)
    _runs[slug] = run
    _persist(run)                       # 立刻寫 status=running + title(可見性)
    run.task = asyncio.create_task(_drive(run))
    return run


def reanalyze(slug: str, title: str) -> Run:
    """對『完整』故事再丟一次內文:snapshot 到 .prev 後走同一條 recover。
    守門看『產物完整』(與 resume_point 同權威),不看 run.json.status。"""
    if not config.valid_slug(slug):
        raise ValueError(f"invalid slug: {slug!r}")
    d = config.STORIES / slug
    if not runstate.is_complete(d):
        raise ValueError("只有完整分析過的故事能重新分析;未完成的請用『續跑』。")
    runstate.snapshot_to_prev(d)          # 搬空 → resume_point 自然回 analyst
    run = start(slug, title, fresh=False)
    run.reanalyze = True
    return run


async def attach(slug: str, title: str, fresh: bool = False):
    """開始-或-接上:先補播已發事件,再直播後續到串流結束。"""
    run = start(slug, title, fresh=fresh)
    q: asyncio.Queue = asyncio.Queue()
    run.subscribers.add(q)             # 先註冊,再快照 backlog —— 兩行間無 await,
    backlog = list(run.events)         # 故已發的進 backlog、之後的進 q,不漏不重
    done_already = run.finished.is_set()
    try:
        for ev in backlog:
            yield ev
        if done_already:
            return
        while True:
            ev = await q.get()
            if ev is None:
                break
            yield ev
    finally:
        run.subscribers.discard(q)


async def cancel(slug: str) -> bool:
    run = _runs.get(slug)
    if not run or run.status != "running" or not run.task:
        return False
    run.status = "cancelled"        # 先標記,_drive 的 except 才不會誤判成 error
    client = run.client
    if client is not None:
        try:
            await client.disconnect()   # 直接收掉 claude 子行程(task.cancel 在 __aexit__ 期間會漏掉)
        except Exception:               # noqa: BLE001
            pass
    run.task.cancel()
    try:
        await run.task
    except BaseException:  # noqa: BLE001 —— 取消必然拋 CancelledError/連線錯誤,吞掉
        pass
    _discard_story(run)    # 取消=連檔一起丟:ingest 出來的 source.md 等一併移除,不留孤兒
    return True


def _discard_story(run: Run) -> None:
    """刪掉這個 Run 綁定的故事目錄。**只清 fresh(新孕育)Run**:那才是本流程剛 ingest
    出來的孤兒,取消它才該連檔丟。既有故事的 source.md 是無版控退路的心血,絕不因取消而刪。
    目錄在 Run 建立時(slug 已過白名單)就固定,不從外部字串重建路徑,故無遍歷可乘之機;
    symlink 一律拒(不順著刪到外面)。"""
    if not run.fresh:
        return
    d = run.dir
    if d.is_symlink() or not d.is_dir():
        return
    if d.resolve().parent != config.STORIES.resolve():
        return              # belt-and-suspenders:確認仍在 STORIES 直下
    shutil.rmtree(d, ignore_errors=True)


def scan_crashed() -> None:
    """server 啟動:in-memory _runs 必空,任何 run.json=running 都是無活 Run 的孤兒
    → 標 failed/crash(可續)。不依賴 run.json 存在:純孤兒由 resume_point 自然處理。"""
    if not config.STORIES.is_dir():
        return
    for d in config.STORIES.iterdir():
        if not d.is_dir():
            continue
        rs = runstate.read(d)
        if rs and rs.get("status") == "running" and d.name not in _runs:
            runstate.write(d, status="failed", stage=rs.get("stage", "analyst"),
                           reason="crash", title=rs.get("title"),
                           cost_usd=rs.get("cost_usd", 0.0))


async def sweep_runs():
    """背景:清掉結束已久的 Run,避免 _runs 無限長。"""
    while True:
        await asyncio.sleep(120)
        now = time.time()
        for slug in [s for s, r in _runs.items()
                     if r.status != "running" and now - r.started > _DONE_TTL]:
            _runs.pop(slug, None)
