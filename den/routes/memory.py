"""記憶:列、寫入、改、封存、拉回。"""
import logging
import time
from contextlib import contextmanager

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from den import memory, suggest, views
from den.config import MAX_CHAT_CHARS
from den.routes.common import ApiError, Seq, slug_ok
from marrow import repo

log = logging.getLogger("hyenovel")
router = APIRouter()


class MemoryIn(BaseModel):
    scope: str = Field(max_length=32)
    text: str = Field(max_length=MAX_CHAT_CHARS)
    slug: str | None = Field(default=None, max_length=64)
    session: str | None = Field(default=None, max_length=64)
    seq: int | None = Field(default=None, ge=0, le=2**63 - 1)
    quote: str | None = Field(default=None, max_length=MAX_CHAT_CHARS)


class MemoryEditIn(BaseModel):
    text: str = Field(max_length=MAX_CHAT_CHARS)


class CandidateSaveIn(BaseModel):
    scope: str = Field(max_length=32)
    text: str | None = Field(default=None, max_length=MAX_CHAT_CHARS)


class SuggestIn(BaseModel):
    enabled: bool


def _memory_reject(status: int, code: str, detail: str) -> ApiError:
    log.info("event=reject where=memory reason=%s", code)
    return ApiError(status, code, detail)


def _memory_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise _memory_reject(422, "blank-memory", "記憶不能是空白")
    return text


@contextmanager
def _memory_errors():
    try:
        yield
    except LookupError:
        raise _memory_reject(404, "unknown-memory", "沒有這條記憶") from None
    except memory.BadSource as e:
        status = 404 if e.code in ("unknown-session", "unknown-turn") else 422
        raise _memory_reject(status, e.code, "來源對不上") from None
    except memory.MemoryFull:
        raise _memory_reject(422, "memory-full", "超過這層的字數上限") from None
    except memory.NotCurrent:
        raise _memory_reject(409, "memory-not-current", "這條已不是生效中的版本") from None
    except memory.AlreadyCurrent:
        raise _memory_reject(409, "memory-is-current", "這條已經是生效中的版本") from None
    except suggest.UnknownCandidate:
        raise _memory_reject(404, "unknown-memory-candidate", "沒有這條待確認") from None
    except suggest.NotPending:
        raise _memory_reject(409, "memory-candidate-resolved", "這條已經處理過") from None
    except suggest.IsPending:
        raise _memory_reject(409, "memory-candidate-pending", "這條還沒處理") from None


@router.get("/memory")
async def list_memory(request: Request):
    return views.memories(request.app.state.mgr.conn)


@router.post("/memory", status_code=201)
async def add_memory(body: MemoryIn, request: Request):
    if body.scope not in ("author", "work"):
        raise _memory_reject(422, "bad-scope", "沒有這一層")
    text = _memory_text(body.text)
    given = [x is not None for x in (body.session, body.seq, body.quote)]
    if any(given) and not all(given):
        raise _memory_reject(422, "bad-source", "來源要給齊")
    if body.slug is None and body.scope == "work":
        raise _memory_reject(422, "slug-required", "要指定作品")
    conn = request.app.state.mgr.conn
    story_id = None
    if body.slug is not None:
        slug_ok(body.slug, "memory")
        st = repo.story_by_slug(conn, body.slug)
        if st is None:
            raise _memory_reject(404, "unknown-work", "這篇不在 DB")
        story_id = st["id"]
    source = {"session": body.session, "seq": body.seq, "quote": body.quote} if all(given) else None
    with _memory_errors():
        mid = memory.remember(conn, body.scope, text, time.time(), story_id=story_id, source=source)
    return views.memory_row(conn, repo.memory(conn, mid))


@router.patch("/memory/{memory_id}")
async def edit_memory(memory_id: Seq, body: MemoryEditIn, request: Request):
    text = _memory_text(body.text)
    conn = request.app.state.mgr.conn
    with _memory_errors():
        mid = memory.edit(conn, memory_id, text, time.time())
    return views.memory_row(conn, repo.memory(conn, mid))


@router.post("/memory/{memory_id}/archive", status_code=204)
async def archive_memory(memory_id: Seq, request: Request):
    with _memory_errors():
        memory.archive(request.app.state.mgr.conn, memory_id, time.time())


@router.post("/memory/{memory_id}/revert")
async def revert_memory(memory_id: Seq, request: Request):
    conn = request.app.state.mgr.conn
    with _memory_errors():
        mid = memory.revert(conn, memory_id, time.time())
    return views.memory_row(conn, repo.memory(conn, mid))


def candidate_row(conn, c: dict) -> dict:
    return {"id": c["id"], "text": c["text"], "quote": c["quote"], "scope": c["scope"],
            "session": c["session"], "seq": c["seq"], "slug": c["slug"],
            "title": None if c["story_id"] is None else views._title(conn, c["story_id"]), "at": c["created_at"]}


@router.get("/memory/candidates")
async def list_candidates(request: Request):
    conn = request.app.state.mgr.conn
    return {"candidates": [candidate_row(conn, c) for c in suggest.pending(conn, time.time())]}


@router.post("/memory/candidates/{candidate_id}/save", status_code=201)
async def save_candidate(candidate_id: Seq, body: CandidateSaveIn, request: Request):
    if body.scope not in ("author", "work"):
        raise _memory_reject(422, "bad-scope", "沒有這一層")
    text = None if body.text is None else _memory_text(body.text)
    conn = request.app.state.mgr.conn
    c = repo.candidate(conn, candidate_id)
    if c is not None and body.scope == "work" and c["story_id"] is None:
        raise _memory_reject(422, "candidate-needs-work", "這條沒有綁作品")
    with _memory_errors():
        mid = suggest.save(conn, candidate_id, body.scope, text, time.time())
    return views.memory_row(conn, repo.memory(conn, mid))


@router.post("/memory/candidates/{candidate_id}/skip", status_code=204)
async def skip_candidate(candidate_id: Seq, request: Request):
    with _memory_errors():
        suggest.skip(request.app.state.mgr.conn, candidate_id, time.time())


@router.post("/memory/candidates/{candidate_id}/undo", status_code=204)
async def undo_candidate(candidate_id: Seq, request: Request):
    with _memory_errors():
        suggest.undo(request.app.state.mgr.conn, candidate_id, time.time())


@router.put("/settings/suggest", status_code=204)
async def set_suggest(body: SuggestIn, request: Request):
    conn = request.app.state.mgr.conn
    with conn:
        suggest.set_enabled(conn, body.enabled)


@router.get("/settings/suggest")
async def get_suggest(request: Request):
    return {"enabled": suggest.enabled(request.app.state.mgr.conn)}
