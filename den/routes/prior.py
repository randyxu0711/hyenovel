"""前次對話摘要:準備、讀、編輯、話題狀態、開關。"""
import logging
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from den import prior, suggest
from den.config import DIGEST_MAX_CHARS
from den.routes.common import ApiError, slug_ok, unknown_work
from marrow import repo

log = logging.getLogger("hyenovel")
router = APIRouter()


class DigestIn(BaseModel):
    text: str = Field(max_length=DIGEST_MAX_CHARS)


class EndedIn(BaseModel):
    ended: bool


class TalkedIn(BaseModel):
    talked: bool


class EnabledIn(BaseModel):
    enabled: bool


def _reject(status: int, code: str, detail: str) -> ApiError:
    log.info("event=reject where=prior reason=%s", code)
    return ApiError(status, code, detail)


def _story(conn, slug: str, where: str) -> dict:
    slug_ok(slug, where)
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise unknown_work(where)
    return st


def _thread(conn, thread_id: int) -> dict:
    t = repo.thread_by_id(conn, thread_id)
    if t is None:
        raise _reject(404, "unknown-thread", "沒有這條話題")
    return t


@router.post("/works/{slug}/prior/prepare", status_code=202)
async def prepare(slug: str, request: Request):
    state = request.app.state
    st = _story(state.mgr.conn, slug, "prior")
    if not prior.enabled(state.mgr.conn) and not suggest.enabled(state.mgr.conn):
        return Response(status_code=204)
    state.prior.ensure(st["id"])
    return {}


@router.get("/works/{slug}/prior")
async def read(slug: str, request: Request):
    conn = request.app.state.mgr.conn
    st = _story(conn, slug, "prior")
    latest = repo.latest_source_version(conn, st["id"])
    return {"enabled": prior.enabled(conn), **prior.gather(conn, st["id"], None, latest["text"] if latest else "")}


@router.put("/digests/{digest_id}", status_code=201)
async def edit_digest(digest_id: int, body: DigestIn, request: Request):
    conn = request.app.state.mgr.conn
    d = repo.digest_by_id(conn, digest_id)
    if d is None:
        raise _reject(404, "unknown-digest", "沒有這份摘要")
    text = body.text.strip()
    if not text:
        raise _reject(422, "blank-digest", "摘要不能是空白")
    if repo.current_digest(conn, d["discussion_id"])["id"] != digest_id:
        raise _reject(409, "stale-digest", "這份摘要已經更新過")
    with conn:
        new = repo.add_digest(conn, d["discussion_id"], text, d["through_seq"], time.time(),
                              root_id=d["root_id"], edited=True)
    return {"id": new}


@router.put("/threads/{thread_id}", status_code=204)
async def set_ended(thread_id: int, body: EndedIn, request: Request):
    conn = request.app.state.mgr.conn
    _thread(conn, thread_id)
    with conn:
        prior.end_thread(conn, thread_id, time.time() if body.ended else None)


@router.put("/sessions/{session}/threads/{thread_id}/talked", status_code=204)
async def set_talked(session: str, thread_id: int, body: TalkedIn, request: Request):
    conn = request.app.state.mgr.conn
    d = repo.discussion_by_session(conn, session)
    if d is None:
        raise _reject(404, "unknown-session", "沒有這一局")
    _thread(conn, thread_id)
    with conn:
        (repo.mark_talked if body.talked else repo.unmark_talked)(conn, thread_id, d["id"])


@router.put("/settings/prior", status_code=204)
async def set_prior(body: EnabledIn, request: Request):
    conn = request.app.state.mgr.conn
    with conn:
        prior.set_enabled(conn, body.enabled)


@router.get("/settings/prior")
async def get_prior(request: Request):
    return {"enabled": prior.enabled(request.app.state.mgr.conn)}
