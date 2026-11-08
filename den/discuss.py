"""companion 的對話引擎:多輪歷史的組裝(render_turn)與一輪的執行(run_turn)。

web 與 MCP talk_to_companion 共用,素材見 den.companion。
"""
import logging
import time
import uuid
from collections.abc import Sequence
from contextlib import aclosing

from den import characters, companion, retrieve, spans, stories
from den.config import MAX_QUOTE_CHARS, MAX_QUOTES
from marrow import gate, prompt, repo

log = logging.getLogger("hyenovel")


_ROLE = {"user": "作者", "assistant": "你"}
OPENER = "(作者還沒說話。你先開口。)"
CONTINUE = "(作者這次沒說話,等你接著說。)"
ATTACHED = "(作者丟進來一份稿〈{name}〉。)"


def _quotes_block(quotes) -> list[str]:
    return ["作者指著原文的這幾段:", *[f"「{q}」" for q in quotes]] if quotes else []


def render_turn(history: list[dict], message: str, quotes=(), notes: str = "",
                summary: str | None = None, attached: Sequence[dict] = ()) -> str:
    """一輪的輸入:歷史包進 <history>、新訊息放最後;無歷史只回訊息本身。
    作者帶了原文引文,就在新訊息前加「作者指著原文的這幾段」;歷史裡的舊引文照同格式還原。
    notes 是這輪檢索到的細節,只存在這輪,不進歷史。"""
    block = [*([notes] if notes else []), *_quotes_block(quotes)]
    head = [f"之前的對話摘要:\n<summary>\n{summary}\n</summary>", ""] if summary else []
    if not history:
        if not head:
            return "\n".join([*block, "", "作者這一輪說:", message]) if block else message
        return "\n".join([*head, *block, *([""] if block else []), "作者這一輪說:", message])
    dropped = {a["seq"]: a["name"] for a in attached}
    lines = [x for h in history for x in (
        *([ATTACHED.format(name=dropped[h["seq"]])] if h.get("seq") in dropped else []),
        *_quotes_block(h.get("quotes")), f"{_ROLE[h['role']]}:{h['text']}")]
    return "\n".join([*head, "以下是這一局到目前為止的對話(作者 = 使用者):",
                      "<history>", *lines, "</history>", "", *block, "作者這一輪說:", message])


_TURNS = ("user", "assistant")
_MARKS = ("clear", "compact")


def live_history(utterances: list[dict]) -> tuple[str | None, list[dict]]:
    last = max((i for i, u in enumerate(utterances) if u["role"] in _MARKS), default=None)
    if last is None:
        return None, [u for u in utterances if u["role"] in _TURNS]
    mark = utterances[last]
    return (mark["text"] if mark["role"] == "compact" else None,
            [u for u in utterances[last + 1:] if u["role"] in _TURNS])


def since_clear(utterances: list[dict]) -> list[dict]:
    last = max((i for i, u in enumerate(utterances) if u["role"] == "clear"), default=-1)
    return [u for u in utterances[last + 1:] if u["role"] in _TURNS]


class UnknownSession(Exception):
    """session_id 不是這篇的局。"""


class LegacySession(Exception):
    """改版前的舊局(沒有記 character 的 assistant 發言):只能看,不能續聊。"""


class UnknownTurn(Exception):
    """這一局沒有這則發言。"""


class NotAssistantTurn(Exception):
    """回饋記號只標在 assistant 的回覆上。"""


def reaction_target(conn, slug: str, session: str, seq: int) -> int:
    """回 discussion id。LookupError 無此篇 / UnknownSession / UnknownTurn / NotAssistantTurn。"""
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    d = repo.discussion_by_external(conn, st["id"], session)
    if d is None:
        raise UnknownSession(session)
    u = repo.utterance(conn, d["id"], seq)
    if u is None:
        raise UnknownTurn(seq)
    if u["role"] != "assistant":
        raise NotAssistantTurn(seq)
    return d["id"]


class QuoteNotInSource(Exception):
    """帶的引文在最新版原文找不到(幻覺或過期)。"""


class TooManyQuotes(Exception):
    """一輪帶的引文超過 MAX_QUOTES 段。"""


class QuoteNeedsMessage(Exception):
    """帶了引文卻沒說話:引文不會落檔,存下的逐字會跟陪讀者看到的不一致。"""


class QuoteTooLong(Exception):
    """某段引文超過 MAX_QUOTE_CHARS。"""


_RECOVERABLE = ("usage-limit", "transient", "timeout")


def prepare_turn(conn, slug: str, session_id: str | None, quotes: Sequence[str] = (),
                 message: str = "") -> dict:
    """串流開始前的判斷(狀態碼只能在這時定):LookupError 無此篇 / UnknownSession /
    LegacySession / TooManyQuotes / QuoteNeedsMessage / QuoteTooLong / QuoteNotInSource(引文過引用閘門才送陪讀者,對的是 companion 讀的那份最新版原文)。
    沒分析也能聊(素材分層在 companion_context)。新局只發 id,discussion 列等整輪成功才建。"""
    ctx = stories.companion_context(conn, slug)
    if len(quotes) > MAX_QUOTES:
        raise TooManyQuotes(len(quotes))
    if quotes and not message.strip():
        raise QuoteNeedsMessage()
    for q in quotes:
        if len(q) > MAX_QUOTE_CHARS:
            raise QuoteTooLong(len(q))
        if not q.strip() or gate.locate(q, ctx["source"]) is None:
            raise QuoteNotInSource(q)
    st = repo.story_by_slug(conn, slug)
    d = None
    if session_id is not None:
        row = repo.discussion_by_external(conn, st["id"], session_id)
        if row is None:
            raise UnknownSession(session_id)
        us = repo.utterances(conn, row["id"])
        if us and not any(u["role"] == "assistant" and u["character"] is not None for u in us):
            raise LegacySession(session_id)   # 空局(還沒有逐字)不算舊局
        d = row["id"]
    analysis = repo.current_artifact(conn, st["id"], "analysis")
    return {"slug": slug, "ctx": ctx, "story_id": st["id"], "discussion_id": d,
            "session_id": session_id or uuid.uuid4().hex[:12],
            "analysis_fp": analysis["sha256"] if ctx["analysis"] is not None else None}


def pick_character(conn, turn: dict, character: str | None) -> None:
    """定這輪的角色(寫進 turn["character"]);characters.UnknownCharacter 要在串流開始前炸。
    角色 > 該局上一位 > 預設。"""
    d = turn["discussion_id"]
    last = repo.last_character(conn, d) if d is not None else None
    turn["character"] = characters.resolve(conn, character, last)


async def run_turn(conn, chat, turn: dict, message: str, anchors: list[str],
                   home: str = "web", client: dict | None = None, now=time.time,
                   quotes: Sequence[str] = ()):
    """一輪:重組歷史 → 轉發 delta 為 token → 整輪成功才在同一個 transaction 落 user+assistant。

    角色(與其模式)由 pick_character 定好放在 turn。message 空 = companion 先開口:工人收到 OPENER,只落 assistant 一筆。

    失敗 / 斷線 = 這輪沒發生過。被 aclose 時一併關掉 chat(工人隨之被殺)。
    歷史在這裡(呼叫者已持該局的鎖)才讀,不在 prepare_turn 讀,免得拿到過期的。
    """
    d = turn["discussion_id"]
    history = repo.utterances(conn, d) if d is not None else []
    seq = history[-1]["seq"] + 1 if history else 0
    character = turn["character"]
    user_ts = now()
    result = None
    slug = turn["slug"]
    failed = False
    system = companion.assemble(turn["ctx"], character)
    analysis = turn["ctx"]["analysis"]
    last = history[-1] if history and history[-1]["role"] == "assistant" else {"text": "", "recipe": None}
    picked = retrieve.pick(analysis, turn["ctx"]["source"], quotes=quotes, message=message, last_reply=last["text"],
                           previous=(last["recipe"] or {}).get("retrieved", ()))
    try:
        async with aclosing(chat(system.text,
                                 render_turn(history, message or (CONTINUE if history else OPENER), quotes,
                                             retrieve.render(analysis, picked)),
                                 config=companion.CHAT_RUN)) as stream:
            async for kind, val in stream:
                if kind == "delta":
                    yield {"event": "token", "data": {"text": val}}
                else:
                    result = val
    except Exception:   # 不抓 BaseException:CancelledError / GeneratorExit 要原樣穿過
        log.exception("event=discuss-turn-failed slug=%s stage=chat", slug)
        failed = True
    except BaseException:
        log.info("event=discuss-turn slug=%s outcome=aborted ms=-", slug)
        raise
    if failed or result is None:
        if not failed:
            log.error("event=discuss-turn-failed slug=%s stage=no-result", slug)
        yield {"event": "error", "data": {"where": "discuss", "message": "討論工人沒有回應,這輪沒有存下",
                                          "recoverable": False, "code": "no-response"}}
        return
    sid = turn["session_id"]
    if result.outcome != "ok":
        log.info("event=discuss-turn slug=%s outcome=%s ms=%s", slug, result.outcome, result.duration_ms)
        yield {"event": "error", "data": {"where": "discuss", "message": result.message,
                                          "recoverable": result.outcome in _RECOVERABLE,
                                          "code": "usage-limit" if result.outcome == "usage-limit" else "chat-failed"}}
        return
    end = now()
    usage = {**(result.tokens or {}), "duration_ms": result.duration_ms, "model": result.model}
    fp = turn["analysis_fp"]
    try:
        with conn:   # 不可在這裡 await:同一條連線 job worker 也在寫
            if d is None:
                d = repo.ensure_discussion(conn, turn["story_id"], sid, home,
                                           (client or {}).get("name") or home, user_ts)
            if message:
                repo.add_utterance(conn, d, seq, "user", message, user_ts, "den", anchors, fp, quotes=quotes)
                seq += 1
            repo.add_utterance(conn, d, seq, "assistant", result.text, end, "den", anchors, fp,
                               usage=usage, character=character["id"],
                               recipe={**prompt.recipe(system, companion.CHAT_RUN.as_dict()),
                                       "character_v": character["version"],
                                       "retrieved": [n["id"] for n in picked]})
            repo.close_discussion(conn, d, end)   # ended_at = 最後活動時間
            v = repo.latest_source_version(conn, turn["story_id"])["n"]   # 這輪(問與答)算在存下當時的最新版
    except Exception:
        log.exception("event=discuss-turn-failed slug=%s stage=commit", slug)
        yield {"event": "error", "data": {"where": "discuss", "message": "存檔失敗,這輪沒有存下",
                                          "recoverable": False, "code": "commit-failed"}}
        return
    log.info("event=discuss-turn slug=%s outcome=ok ms=%s", slug, result.duration_ms)
    yield {"event": "message", "data": {"role": "assistant", "text": result.text,
                                        "session_id": sid, "seq": seq,
                                        "character": character["id"], "v": v,
                                        "spans": spans.locate_all(
                                            [q for q in spans.quotes_in(result.text)
                                             if gate.locate(q, turn["ctx"]["source"])],
                                            turn["ctx"]["source"])}}
    yield {"event": "done", "data": {"ok": True, "session_id": sid}}
