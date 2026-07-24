"""討論服務治理:長命 ClaudeSDKClient 的 session registry + 逐 token 串流。

每個討論 session = 一個活著的 ClaudeSDKClient(底層一支 claude 行程),跨 HTTP 請求存活。
個人單機:每個 session 一把 lock 序列化輪次;閒置逾時由背景 sweeper 回收。

事件信封:
  token   {text}             逐 token delta
  message {role, text, session_id}   整輪收尾(存檔 / 非串流 fallback)
  done    {ok, cost_usd, session_id}
  error   {where, message, recoverable}
"""
import asyncio
import time
import uuid

from claude_agent_sdk import (
    ClaudeSDKClient, AssistantMessage, TextBlock, StreamEvent, ResultMessage,
)

import conclusions
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
        try:
            await sess.client.query(prompt)
            async for m in sess.client.receive_response():
                if isinstance(m, StreamEvent):
                    txt = sdk_runner.delta_text(m)
                    if txt:
                        yield {"event": "token", "data": {"text": txt}}
                elif isinstance(m, AssistantMessage):
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
        final = "".join(final_parts)
        transcript.append(slug, sid, "assistant", final, anchors)
        ledger.append(slug, "discuss", 0, sdk_runner.TurnResult(
            text=final, cost=cost, is_error=False, usage=res_usage,
            model_usage=res_model, duration_ms=res_dur, num_turns=res_nt))
        yield {"event": "message", "data": {"role": "assistant", "text": final, "session_id": sid}}
        yield {"event": "done", "data": {"ok": True, "cost_usd": round(cost, 4), "session_id": sid}}


_DISTILL_PROMPT = """把我們這輪討論收束成結論,輸出**單一 JSON 陣列**,不要任何其他文字。

每個元素只有四個欄位:
  kind    observation(對文本的觀察)/ judgment(編輯判斷)/ question(仍未解的提問)
  text    一句話講完這條結論,且**能獨立成立** —— 日後它會在沒有這段對話的情況下被撈出來
  refs    相關的 analysis node id 陣列(如 ["t3","m1"]);**必須是圖裡真有的 id**,
          編一個不存在的會被閘門擋掉。不確定就給 []
  quotes  支撐這條結論的**逐字原文**陣列;一字不改,改了會被閘門擋掉。沒有就給 []

只收真的有結論的東西 —— 沒有就回 []。不要複述剛才說過的話,不要客套。"""


async def distill(slug: str, session_id: str):
    """把一局討論收束成 conclusions.jsonl。回 {"written", "errors"}。

    只在**活著的** session 裡收束:那裡的語境最完整,而我們沒有 resume。
    session 被 sweep_idle 收掉就收束不了 —— 誠實回報,不假裝能從 transcript 重建當時的思路。

    LLM 全程碰不到檔案(討論 client 是 allowed_tools=["Read"]):
    它把 JSON 當文字吐出來,由 conclusions.py 解析、驗證、寫入。
    """
    sess = _sessions.get(session_id)
    if not sess or sess.slug != slug:
        return {"written": 0, "reason": "session_gone",
                "errors": ["session 不存在或已被回收 —— 結論只能在活著的討論裡收束"]}

    async with sess.lock:
        sess.last_active = time.time()
        try:
            r = await sdk_runner.run_turn(sess.client, _DISTILL_PROMPT)
        except Exception as e:
            log.exception(f"event=distill-turn-fail slug={slug}")
            return {"written": 0, "errors": [str(e)]}
        sess.last_active = time.time()
    ledger.append(slug, "distill", 0, r)

    drafts, err = conclusions.parse_drafts(r.text)
    if err:
        log.warning(f"event=distill-parse-fail slug={slug}")
        return {"written": 0, "errors": [err]}
    turns = transcript.session_range(transcript.load(slug), session_id)
    written, errors = conclusions.append(slug, drafts, session_id, turns)
    log.info(f"event=distill slug={slug} written={written} errors={len(errors)}")
    return {"written": written, "errors": errors}
