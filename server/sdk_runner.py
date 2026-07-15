"""ClaudeSDKClient 薄包裝:統一 options + 把 SDK 訊息收斂成我們要的東西。

兩種用法:
  - critique:一個協調者 client 連續發 query(派 analyst→看閘門→派 criticizer),
    不需 token 串流;run_turn() 把一輪跑完、回成本。
  - discuss:長命 client + token 串流(在 discuss.py 直接消費 receive_response)。
"""
import weakref
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock, ResultMessage, HookMatcher, RateLimitEvent, RateLimitInfo,
)
from . import config
from .log import log


def load_agent_prompt(name: str) -> str:
    """讀 .claude/agents/<name>.md,剝掉 YAML frontmatter,body 當 system_prompt。
    單一真相仍是那份 .md(不複製人格);Python 直接讀檔,不經 guard hook。"""
    text = (config.ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)   # ['', frontmatter, body];maxsplit=2 保留 body 內任何 '---'
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


_ASYNC_DISPATCH_SIG = "Async agent launched successfully"


class AsyncDispatchError(RuntimeError):
    """子代理以背景(async)模式執行——編排器要求同步。多半是 CLI 改了預設。"""


def contains_async_dispatch(text: str) -> bool:
    return _ASYNC_DISPATCH_SIG in (text or "")


def rate_limit_of(msg) -> RateLimitInfo | None:
    """若 msg 是 RateLimitEvent,回其 RateLimitInfo(帶 status/resets_at/utilization/…),否則 None。
    critique 與 discuss 兩條迴圈共用這一個偵測點,不長平行路。"""
    if isinstance(msg, RateLimitEvent):
        return msg.rate_limit_info
    return None


_COST_SEEN: "weakref.WeakKeyDictionary[object, float]" = weakref.WeakKeyDictionary()


def turn_cost(client, total_cost_usd: float | None) -> float:
    """把 ResultMessage.total_cost_usd 換算成「這一輪」的花費。

    SDK 文件明載該欄是 *Cumulative across the conversation*:CLI 內部是個 `+=` 累加器,
    同一個 ClaudeSDKClient 上每次 query 回報的都是「這個 client 開跑至今」的總額。
    (`query()` 函式每呼叫一次開新行程,才會看起來像單輪值。)照抄相加會重複計——
    重試與 discuss 多輪尤其嚴重。故在此扣掉同一 client 上一次的累計。

    注意這是**本機估算值**(SDK 用內建價目表算的),非帳單。
    """
    total = total_cost_usd or 0.0
    prev = _COST_SEEN.get(client, 0.0)
    _COST_SEEN[client] = total
    delta = total - prev
    if delta < 0:                      # 累加器倒退 = 語意變了(或 client 被重用),別瞎猜
        log.warning(f"cost accumulator went backwards ({prev} → {total}); recording as-is")
        return total
    return delta


@dataclass
class TurnResult:
    """一輪 run_turn 的結果。除文字/成本外,帶結構化失敗訊號供 critique 分流,及帳本用量。"""
    text: str
    cost: float
    is_error: bool
    api_error_status: int | None = None       # ResultMessage.api_error_status(429/500/529)
    rate_limit: RateLimitInfo | None = None    # 最新一筆 RateLimitEvent 的 info
    usage: dict | None = None                  # ResultMessage.usage(input/output/cache_* tokens)
    model_usage: dict | None = None            # ResultMessage.model_usage(按模型再拆)
    duration_ms: int | None = None             # 這輪牆鐘毫秒
    num_turns: int | None = None               # 這輪內部回合數


def _capacity_failure(r: "TurnResult") -> str | None:
    """把一輪結果分到容量失敗的哪一類(否則 None,交還內容閘門)。
      "transient" = 529/500,牆幾秒清 → 值得有界退避
      "hard"      = 429 或 RateLimitInfo 說 rejected,訂閱窗多小時才 reset → fail-fast
    """
    if r.api_error_status == 429:
        return "hard"
    if r.api_error_status in (500, 529):
        return "transient"
    if r.rate_limit is not None and r.rate_limit.status == "rejected":
        return "hard"
    return None


def classify_failure(message: str) -> str:
    """把已知死法簽章對到可讀 reason,給前端顯示、給我們冷卻判斷。"""
    m = message or ""
    if "Stream closed at sendRequest" in m or "Error in hook callback" in m:
        return "usage-limit"          # 訂閱額度撞頂:子行程被拆
    if _ASYNC_DISPATCH_SIG in m:
        return "async-dispatch"
    if "budget" in m.lower():
        return "budget"               # max_budget_usd 超支
    return "unknown"


# ── 縱深防禦:路徑白名單硬閘 ────────────────────────────────────────
# 就算代理被 source.md 內的注入騎劫,檔案工具也只能碰 stories/(讀寫)與
# schemas/(唯讀)—— 讀不到 repo 外的機密、寫不出 stories/ 之外。PreToolUse
# hook 對 analyst/criticizer(以主代理直接跑)的檔案工具呼叫觸發,故真正
# 接觸下毒文本的那一層也在守備範圍內。違規當下直接 deny,不重試。
_FILE_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}
_WRITE_ROOTS = [config.STORIES.resolve()]
_READ_ROOTS = [config.STORIES.resolve(), (config.ROOT / "schemas").resolve()]


def _within(target: Path, roots: list[Path]) -> bool:
    return any(target == r or r in target.parents for r in roots)


async def _guard_path(input_data, tool_use_id, context):
    """PreToolUse 閘:檔案工具的目標路徑必須落在白名單內,否則硬 deny。"""
    tool = input_data.get("tool_name", "")
    if tool not in _FILE_TOOLS:
        return {}
    ti = input_data.get("tool_input", {}) or {}
    raw = ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or ""
    try:
        target = Path(raw)
        if not target.is_absolute():
            target = config.ROOT / target
        target = target.resolve()
        roots = _READ_ROOTS if tool == "Read" else _WRITE_ROOTS
        ok = bool(raw) and _within(target, roots)
    except Exception:
        ok = False   # fail-closed:路徑解析不了就擋
    if ok:
        return {}
    who = input_data.get("agent_id", "main")
    log.warning(f"[guard] deny {tool} {raw!r} (agent={who})")
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"路徑越界,已擋:{raw}。僅允許讀寫 stories/、唯讀 schemas/。"
        ),
    }}


_GUARD_HOOKS = {
    "PreToolUse": [HookMatcher(matcher="Read|Write|Edit|MultiEdit|NotebookEdit",
                              hooks=[_guard_path])],
}


def agent_options(agent_name: str) -> ClaudeAgentOptions:
    """把 analyst/criticizer 當『主代理』直接跑:該 agent 的 body 當 system_prompt,
    只給 Read/Write,明令禁 Task(斷 async 子代理巢狀)與 Bash(斷亂試)。
    沒有協調者、沒有 Task 巢狀 —— 『本輪返回』與『檔已寫出』重新耦合。
    路徑白名單 hook 仍把檔案工具鎖在 stories/ 與 schemas/ 內。"""
    return ClaudeAgentOptions(
        cwd=str(config.ROOT),
        setting_sources=["project"],
        system_prompt=load_agent_prompt(agent_name),
        allowed_tools=["Read", "Write"],   # allow-list:只有這兩個可用(其餘一律不可)
        # 顯式硬 deny(即使 allow-list 已排除,仍列出讓意圖不用跨兩行對照):
        # Task=斷 async 子代理巢狀、Bash=斷亂試、Edit/NotebookEdit=逼全檔 Write、不做局部竄改。
        disallowed_tools=["Task", "Bash", "Edit", "NotebookEdit"],
        permission_mode="acceptEdits",
        hooks=_GUARD_HOOKS,
        model=config.CRITIQUE_MODEL,
        max_budget_usd=config.CRITIQUE_BUDGET_USD,
        max_turns=config.AGENT_MAX_TURNS,
        thinking={"type": "disabled"},   # 關掉 extended thinking:讓主代理回到當子代理時的行為。
        # 這活是「讀檔→照 .md 指令吐結構化 JSON」,不需大草稿紙;主代理預設 adaptive 會想到撞
        # max_tokens 截斷、還沒 Write 就死。max_thinking_tokens 在新模型已 deprecated(非零=adaptive,
        # 等於沒設),故用非 deprecated 的 thinking 旗標硬關。(若日後 A/B 證明想一下能提升分析深度,
        # 再換 {"type":"enabled","budget_tokens":N} 並確認不截斷。)
        include_partial_messages=False,
    )


def discuss_options(resume: str | None = None) -> ClaudeAgentOptions:
    """討論:read-only(v1 不開寫回 analysis.json),逐 token 串流。
    resume 帶 SDK session id → 斷線後接回同一對話。"""
    return ClaudeAgentOptions(
        cwd=str(config.ROOT),
        setting_sources=["project"],
        allowed_tools=["Read"],               # v1 唯讀:聊天不誤改正本
        permission_mode="default",
        hooks=_GUARD_HOOKS,                    # 讀也鎖在 stories/、schemas/ 內
        model=config.DISCUSS_MODEL,
        include_partial_messages=True,        # 逐 token delta
        resume=resume,
    )


async def run_turn(client: ClaudeSDKClient, prompt: str) -> TurnResult:
    """送一輪 prompt、抽乾回應,回 TurnResult(帶結構化失敗訊號)。"""
    await client.query(prompt)
    text, cost, err = "", 0.0, False
    api_status: int | None = None
    rl = None
    usage = model_usage = None
    duration_ms = num_turns = None
    async for m in client.receive_response():
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    text = b.text
                    if contains_async_dispatch(text):
                        raise AsyncDispatchError(text[:200])
        elif isinstance(m, ResultMessage):
            cost = turn_cost(client, m.total_cost_usd)
            err = bool(m.is_error)
            api_status = m.api_error_status
            usage = m.usage
            model_usage = m.model_usage
            duration_ms = m.duration_ms
            num_turns = m.num_turns
        else:
            info = rate_limit_of(m)
            if info is not None:
                rl = info
                log.info(f"rate_limit status={info.status} util={info.utilization} "
                         f"reset={info.resets_at} type={info.rate_limit_type}")
    return TurnResult(text=text, cost=cost, is_error=err,
                      api_error_status=api_status, rate_limit=rl,
                      usage=usage, model_usage=model_usage,
                      duration_ms=duration_ms, num_turns=num_turns)


def delta_text(stream_event) -> str | None:
    """從 StreamEvent 抽純文字 delta(content_block_delta / text_delta);其餘回 None。"""
    ev = getattr(stream_event, "event", None) or {}
    if isinstance(ev, dict) and ev.get("type") == "content_block_delta":
        delta = ev.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text") or None
    return None
