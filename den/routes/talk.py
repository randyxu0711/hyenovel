"""討論:局清單、逐字稿、回饋記號、一輪對話的 SSE。"""
import asyncio
import logging
import time
from contextlib import aclosing, nullcontext
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from den import characters, compact, discuss, stories, views
from den.config import MAX_ANCHORS, MAX_CHAT_CHARS, MAX_QUOTES, MAX_REACTION_CHARS, REACTION_MARKS, valid_slug
from den.routes.common import ApiError, ClientIn, Seq, slug_ok, sse_line, unknown_work
from marrow import prompt, repo

log = logging.getLogger("hyenovel")
router = APIRouter()


class ReactionIn(BaseModel):
    mark: str = Field(max_length=32)
    comment: str | None = Field(default=None, max_length=MAX_REACTION_CHARS * 8)


class AttachIn(BaseModel):
    name: str = Field(max_length=200)
    text: str


class DiscussIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(default="", max_length=MAX_CHAT_CHARS)   # 空 = companion 先開口
    anchors: list[str] = Field(default_factory=list, max_length=MAX_ANCHORS)
    quotes: list[str] = Field(default_factory=list, max_length=MAX_QUOTES * 8)   # 「帶這段」:原文逐字引文;段數上限由 prepare_turn 回 too-many-quotes,這裡只擋超大 body
    character: str | None = Field(default=None, max_length=32)
    home: Literal["web", "mcp"] = "web"
    client: ClientIn | None = None
    attach: AttachIn | None = None


_BUSY = {"event": "error", "data": {"where": "discuss", "message": "這一局還有一輪在跑",
                                   "recoverable": True, "code": "busy"}}


async def _chat_stream(state, lock: asyncio.Lock | None, events):
    """一輪討論的 SSE 本體:算進開著的串流(閒置退場不砍)、整輪持該局的鎖。

    鎖在這裡拿而非端點:回應若沒開始送,generator 從沒進來,鎖也就不會漏放。
    被斷線關掉時 aclosing 一路關到 chat,工人隨之被殺。
    """
    state.streams += 1
    try:
        if lock is not None and lock.locked():   # 端點判過後、開始前被別人搶先(極窄)
            yield sse_line(_BUSY)
            return
        async with lock or nullcontext(), aclosing(events):
            async for ev in events:
                yield sse_line(ev)
    finally:
        state.streams -= 1


@router.get("/works/{slug}/sessions")
async def work_sessions(slug: str, request: Request, legacy: bool = False):
    slug_ok(slug, "work-sessions")
    try:
        return {"sessions": views.sessions(request.app.state.mgr.conn, slug, legacy)}
    except LookupError:
        raise unknown_work("work-sessions") from None


@router.get("/sessions")
async def recent_sessions(request: Request, limit: int = 20, legacy: bool = False):
    if not 1 <= limit <= 100:
        log.info("event=reject where=recent-sessions limit=%s", limit)
        raise HTTPException(422, "limit 要在 1–100")
    return {"sessions": views.recent_sessions(request.app.state.mgr.conn, limit, legacy)}


@router.get("/sessions/{session}")
async def session_turns(session: str, request: Request, v: int | None = Query(None, ge=1)):
    try:
        return views.session_turns(request.app.state.mgr.conn, session, v)
    except LookupError:
        log.info("event=reject where=session-turns reason=unknown-session-id")
        raise ApiError(404, "unknown-session-id", "沒有這一局") from None
    except views.UnknownVersion:
        log.info("event=reject where=session-turns reason=unknown-version v=%s", v)
        raise ApiError(404, "unknown-version", "沒有這個版本") from None


def _reaction_target(request: Request, slug: str, session: str, seq: int) -> int:
    def reject(status: int, code: str, detail: str) -> ApiError:
        log.info("event=reject where=reaction reason=%s", code)
        return ApiError(status, code, detail)
    slug_ok(slug, "reaction")
    try:
        return discuss.reaction_target(request.app.state.mgr.conn, slug, session, seq)
    except LookupError:
        raise unknown_work("reaction") from None
    except discuss.UnknownSession:
        raise reject(404, "unknown-session", "這篇沒有這一局") from None
    except discuss.UnknownTurn:
        raise reject(404, "unknown-turn", "這一局沒有這則發言") from None
    except discuss.NotAssistantTurn:
        raise reject(422, "not-assistant-turn", "只能標陪讀者的回覆") from None


@router.put("/works/{slug}/sessions/{session}/turns/{seq}/reaction")
async def put_reaction(slug: str, session: str, seq: Seq, body: ReactionIn, request: Request):
    d = _reaction_target(request, slug, session, seq)
    if body.mark not in REACTION_MARKS:
        log.info("event=reject where=reaction reason=bad-mark")
        raise ApiError(422, "bad-mark", "沒有這種記號")
    comment = (body.comment or "").strip() or None
    if comment and len(comment) > MAX_REACTION_CHARS:
        log.info("event=reject where=reaction reason=comment-too-long")
        raise ApiError(422, "comment-too-long", "短評太長")
    conn = request.app.state.mgr.conn
    with conn:
        repo.set_reaction(conn, d, seq, body.mark, comment, time.time())
    return {"mark": body.mark, "comment": comment}


@router.delete("/works/{slug}/sessions/{session}/turns/{seq}/reaction", status_code=204)
async def delete_reaction(slug: str, session: str, seq: Seq, request: Request):
    d = _reaction_target(request, slug, session, seq)
    conn = request.app.state.mgr.conn
    with conn:
        repo.clear_reaction(conn, d, seq)


def _session_or_404(conn, session: str, where: str) -> dict:
    d = repo.discussion_by_session(conn, session)
    if d is None:
        log.info("event=reject where=%s reason=unknown-session", where)
        raise ApiError(404, "unknown-session", "沒有這一局")
    return d


def _free_lock(state, session: str, where: str) -> asyncio.Lock:
    lock = state.chat_locks.setdefault(session, asyncio.Lock())
    if lock.locked():
        log.info("event=reject where=%s reason=busy", where)
        raise ApiError(409, "busy", "這一局還有一輪在跑")
    return lock


@router.post("/sessions/{session}/clear", status_code=201)
async def clear_session(session: str, request: Request):
    conn = request.app.state.mgr.conn
    d = _session_or_404(conn, session, "clear")
    _free_lock(request.app.state, session, "clear")
    us = repo.utterances(conn, d["id"])
    summary, live = discuss.live_history(us)
    if not live and summary is None:
        log.info("event=reject where=clear reason=nothing-to-clear")
        raise ApiError(422, "nothing-to-clear", "這局沒有可以清的對話")
    seq = us[-1]["seq"] + 1
    with conn:
        repo.add_utterance(conn, d["id"], seq, "clear", "", time.time(), "den", [], None)
    return {"seq": seq}


@router.post("/sessions/{session}/compact", status_code=201)
async def compact_session(session: str, request: Request):
    state = request.app.state
    conn = state.mgr.conn
    d = _session_or_404(conn, session, "compact")
    lock = _free_lock(state, session, "compact")
    async with lock:
        us = repo.utterances(conn, d["id"])
        rows = discuss.since_clear(us)
        if not any(u["role"] == "assistant" for u in rows) or us[-1]["role"] == "compact":
            log.info("event=reject where=compact reason=nothing-to-compact")
            raise ApiError(422, "nothing-to-compact", "這局沒有可以壓縮的對話")
        try:
            text, usage = await compact.summarize(state.chat, compact.transcript(rows))
        except Exception:
            log.exception("event=compact-failed session=%s", session)
            raise ApiError(502, "compact-failed", "壓縮失敗,對話沒有改動") from None
        seq = us[-1]["seq"] + 1
        with conn:
            repo.add_utterance(conn, d["id"], seq, "compact", text, time.time(), "den", [], None, usage=usage,
                               recipe=prompt.recipe(compact.system(), compact.COMPACT_RUN.as_dict()))
    return {"seq": seq, "text": text}


@router.post("/sessions/{session}/attachments/{n}/adopt", status_code=201)
async def adopt_attachment(session: str, n: int, request: Request):
    def reject(status: int, code: str, detail: str) -> ApiError:
        log.info("event=reject where=adopt reason=%s", code)
        return ApiError(status, code, detail)
    conn = request.app.state.mgr.conn
    d = _session_or_404(conn, session, "adopt")
    _free_lock(request.app.state, session, "adopt")
    try:
        with conn:
            return stories.adopt(conn, d, n, time.time())
    except stories.UnknownAttachment:
        raise reject(404, "unknown-attachment", "這局沒有這份附件") from None
    except stories.AlreadyAdopted:
        raise reject(409, "already-adopted", "這份附件已經開成作品") from None
    except stories.BoundSession:
        raise reject(422, "bound-session", "這局已經綁了作品") from None
    except ValueError:
        raise reject(422, "bad-source", "這份稿收不成作品") from None


@router.post("/discuss")
async def discuss_free(body: DiscussIn, request: Request):
    return _discuss(None, body, request)


@router.post("/discuss/{slug}")
async def discuss_turn(slug: str, body: DiscussIn, request: Request):
    if not valid_slug(slug):
        log.info("event=reject where=discuss reason=bad-slug")
        raise ApiError(422, "bad-slug", "bad slug")
    return _discuss(slug, body, request)


def _discuss(slug: str | None, body: DiscussIn, request: Request):
    def reject(status: int, reason: str, detail: str) -> ApiError:
        log.info("event=reject where=discuss reason=%s", reason)
        return ApiError(status, "unknown-work" if reason == "unknown-slug" else reason, detail)
    state = request.app.state
    try:
        turn = discuss.prepare_turn(state.mgr.conn, slug, body.session_id, body.quotes, body.message,
                                    body.attach.model_dump() if body.attach else None)
    except LookupError:
        raise reject(404, "unknown-slug", "這篇不在 DB") from None
    except discuss.UnknownSession:
        raise reject(404, "unknown-session", "這篇沒有這一局") from None
    except discuss.LegacySession:
        raise reject(409, "legacy-session", "這是改版前的舊討論,只能看不能續聊") from None
    except discuss.TooManyQuotes:
        raise reject(422, "too-many-quotes", "一輪帶的引文太多段") from None
    except discuss.QuoteNeedsMessage:
        raise reject(422, "quote-needs-message", "帶引文要同時說點什麼") from None
    except discuss.QuoteTooLong:
        raise reject(422, "quote-too-long", "引文太長") from None
    except discuss.QuoteNotInSource:
        raise reject(422, "quote-not-in-source", "引文不在原文裡") from None
    except stories.BoundSession:
        raise reject(422, "bound-session", "這局已經綁了作品,交新版請用交稿") from None
    except discuss.TooManyAttachments:
        raise reject(422, "too-many-attachments", "這局的附件太多份") from None
    except discuss.EmptyAttachment:
        raise reject(422, "empty-attachment", "附件是空的") from None
    except discuss.AttachmentTooLong:
        raise reject(422, "attachment-too-long", "附件太長") from None
    lock = None
    if body.session_id is not None:   # 新局不會撞:id 這輪才發
        lock = state.chat_locks.setdefault(body.session_id, asyncio.Lock())
        if lock.locked():
            raise reject(409, "busy", "這一局還有一輪在跑")
    client = body.client.model_dump() if body.client else None
    try:
        discuss.pick_character(state.mgr.conn, turn, body.character)
    except characters.UnknownCharacter:
        raise reject(422, "unknown-character", "沒有這隻角色") from None
    events = discuss.run_turn(state.mgr.conn, state.chat, turn, body.message, body.anchors,
                              body.home, client, quotes=body.quotes)
    return StreamingResponse(_chat_stream(state, lock, events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
