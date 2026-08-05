"""討論服務治理:長命 ClaudeSDKClient 的 session registry + 逐 token 串流。

每個討論 session = 一個活著的 ClaudeSDKClient(底層一支 claude 行程),跨 HTTP 請求存活。
個人單機:每個 session 一把 lock 序列化輪次;閒置逾時由背景 sweeper 回收。

事件信封:
  token    {text}            逐 token delta(回答本體)
  thinking {text}            推理草稿 delta。**目前休眠**:討論已關 extended thinking
                             (`sdk_runner.discuss_options`),wire 上不再出 thinking_delta。
                             接線留著 —— 那是可逆的實驗,翻回來時這條路自動醒。
                             **不進 transcript 正本**:正本記的是編輯說了什麼,不是它想過什麼。
  message {role, text, session_id}   整輪收尾(存檔 / 非串流 fallback)
  done    {ok, cost_usd, session_id}
  error   {where, message, recoverable}
"""
import asyncio
import time
import uuid

from claude_agent_sdk import (
    ClaudeSDKClient, AssistantMessage, TextBlock, ToolUseBlock, StreamEvent, ResultMessage,
)

import recall

from . import config, ledger, sdk_runner, transcript
from .log import log


class Session:
    def __init__(self, slug: str, client: ClaudeSDKClient):
        self.slug = slug
        self.client = client
        self.sdk_session_id: str | None = None   # SDK 端對話 id(供未來 resume)
        self.last_active = time.time()
        self.lock = asyncio.Lock()


_sessions: dict[str, Session] = {}


def list_sessions(slug: str) -> list[dict]:
    return [{"session_id": sid, "last_active": s.last_active}
            for sid, s in _sessions.items() if s.slug == slug]


async def close_session(session_id: str) -> bool:
    s = _sessions.pop(session_id, None)
    if not s:
        return False
    try:
        await s.client.disconnect()
    except Exception:
        pass
    return True


async def sweep_idle():
    """背景:回收閒置逾時的 session,避免洩漏 claude 行程。"""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        stale = [sid for sid, s in _sessions.items()
                 if now - s.last_active > config.DISCUSS_IDLE_TIMEOUT and not s.lock.locked()]
        for sid in stale:
            await close_session(sid)


def _log_reads(slug, blocks):
    """把這一輪讀了哪些檔記下來(唯讀、不改行為)。

    跨篇是 skill 指示不是程式閘門(sdk_runner 的 _READ_ROOTS 本來就是整個 stories/ 樹),
    擋不住 —— 那至少要看得見。這也是「沒有多載」唯一可行的觀測手段:
    usage.jsonl 是長命 session 的累計值,反推不出單輪讀了什麼。
    """
    for b in blocks:
        if isinstance(b, ToolUseBlock) and b.name == "Read":
            path = (b.input or {}).get("file_path")
            if path:
                log.info(f"event=discuss-read slug={slug} file={path}")


async def run_discuss(slug: str, session_id: str | None, message: str, anchors=()):
    if not (config.STORIES / slug / "analysis.json").exists():
        yield {"event": "error", "data": {"where": "input",
               "message": f"{slug} 還沒分析,先跑 critique", "recoverable": False}}
        return

    sess = _sessions.get(session_id) if session_id else None
    new = sess is None

    try:
        if new:
            client = ClaudeSDKClient(options=sdk_runner.discuss_options())
            await client.connect()
            sid = uuid.uuid4().hex[:12]
            sess = Session(slug, client)
            _sessions[sid] = sess
            # 新 session 開場:引 story-discuss skill(讀 analysis/feedback/source,提切入點)
            prompt = f"/story-discuss {slug}"
            # 喚燼:注入這篇過去討論的結論(討論走判斷層,看得到 observation+judgment+question)。
            # 只開場注入一次;續局的既有 session 不重注入。recall 為純函式讀檔,失敗回空。
            recalled = recall.format_recall(recall.recall(slug, anchors=anchors, layer="judgment"))
            if recalled:
                prompt += f"\n\n{recalled}"
            if message.strip():
                prompt += f"\n\n{message}"
        else:
            sid = session_id
            prompt = message
    except Exception as e:
        log.exception(f"event=discuss-connect-fail slug={slug}")
        yield {"event": "error", "data": {"where": "connect", "message": str(e), "recoverable": True}}
        return

    async with sess.lock:
        sess.last_active = time.time()
        # 逐輪寫,不等 session 結束 —— sweep_idle 是把它掃掉,沒有結束事件可以掛。
        # 寫 message 而非 prompt:新 session 的 prompt 前面接了 /story-discuss 的引導,
        # 那是系統加的,不是使用者說的話。
        if message.strip():
            transcript.append(slug, sid, "user", message, anchors)
        final_parts, cost = [], 0.0
        res_usage = res_model = res_dur = res_nt = None
        kinds: dict[str, int] = {}   # 這一輪各類 delta 各來幾段(見收尾的 discuss-turn log)
        try:
            await sess.client.query(prompt)
            async for m in sess.client.receive_response():
                if isinstance(m, StreamEvent):
                    d = sdk_runner.delta_of(m)
                    if d:
                        kinds[d[0]] = kinds.get(d[0], 0) + 1
                        yield {"event": "thinking" if d[0] == "thinking" else "token",
                               "data": {"text": d[1]}}
                elif isinstance(m, AssistantMessage):
                    _log_reads(slug, m.content)
                    # 收集全部 TextBlock 再串接 —— 一輪可能有超過一個 AssistantMessage
                    # (討論 client 是 allowed_tools=["Read"],開場的 /story-discuss skill
                    # 會先讀 analysis/feedback/source,讀檔前後常各自帶一段文字)。
                    # 只留最後一個會讓「逐字捕獲」名不符實:使用者透過 token 串流全看到了,
                    # 正本卻悄悄丟掉前面幾句。
                    for b in m.content:
                        if isinstance(b, TextBlock):
                            final_parts.append(b.text)
                elif isinstance(m, ResultMessage):
                    cost = sdk_runner.turn_cost(sess.client, m.total_cost_usd)
                    res_usage, res_model = m.usage, m.model_usage
                    res_dur, res_nt = m.duration_ms, m.num_turns
                    if m.session_id:
                        sess.sdk_session_id = m.session_id
                else:
                    info = sdk_runner.rate_limit_of(m)
                    if info is not None:
                        log.info(f"event=rate-limit ctx=discuss status={info.status} "
                                 f"reset={info.resets_at} type={info.rate_limit_type}")
        except Exception as e:
            log.exception(f"event=discuss-turn-fail slug={slug}")
            yield {"event": "error", "data": {"where": "discuss", "message": str(e), "recoverable": True}}
            return
        sess.last_active = time.time()
        # 這一輪 wire 上到底出了哪幾類 delta。「是不是 thinking」從此讀 log 回答,不靠推論或臨時插樁。
        # 討論已關 thinking(2026-07-27),故預期只剩 `text:N`。**這行同時是那次改動的驗收**:
        # 真出現 thinking:N 就代表 `thinking={"type":"disabled"}` 沒吃到,別當它關成功了。
        # 配 usage.jsonl 的秒數看延遲有沒有真的降(關前基準:單輪 28–96 秒)。
        tally = ",".join(f"{k}:{v}" for k, v in sorted(kinds.items())) or "none"
        log.info(f"event=discuss-turn slug={slug} deltas={tally}")
        final = "".join(final_parts)
        transcript.append(slug, sid, "assistant", final, anchors)
        ledger.append(slug, "discuss", 0, sdk_runner.TurnResult(
            text=final, cost=cost, is_error=False, usage=res_usage,
            model_usage=res_model, duration_ms=res_dur, num_turns=res_nt))
        yield {"event": "message", "data": {"role": "assistant", "text": final, "session_id": sid}}
        yield {"event": "done", "data": {"ok": True, "cost_usd": round(cost, 4), "session_id": sid}}


# 收束(蒸餾成 conclusions.jsonl)已搬到 server/settle.py:它不再借用這裡的 client,
# 而是在這一局被 sweep_idle 回收之後,自己開一個專用 client 從 transcript.jsonl 煉。
# 理由見 settle.py 的 docstring。
