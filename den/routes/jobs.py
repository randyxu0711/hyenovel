"""分析 job:交辦、列表、狀態、停下、續跑、事件串流。"""
import asyncio
import logging

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from den.config import valid_slug
from den.jobs import NothingToResume
from den.routes.common import ApiError, ClientIn, sse_line
from den.runner import pick_runner
from marrow import repo

log = logging.getLogger("hyenovel")
router = APIRouter()

_TERMINAL = ("done", "paused", "failed", "cancelled")
_SSE_POLL = 15.0        # SSE 多久沒事件就回頭看 DB(兼 keep-alive)
_ATTEMPT_KEYS = ("step", "n", "outcome", "model", "duration_ms", "tokens")
_LIST_KEYS = ("id", "slug", "title", "state", "step", "error_class", "updated_at",
              "is_latest_version")
_LIST_MAX = 100
_JOB_KEYS = ("id", "kind", "story_id", "source_version_id", "state", "step",
             "error_class", "detail", "params", "created_at", "updated_at")


class JobIn(BaseModel):
    kind: Literal["critique"]
    slug: str
    client: ClientIn | None = None
    resume_only: bool = False   # 不帶稿的交稿:只續跑,不開新的一次分析


def _state_event(job: dict) -> dict:
    return {"event": "state", "data": {k: job[k] for k in ("state", "step", "error_class", "detail")}}


def _job(request: Request, job_id: int) -> dict:
    job = repo.get_job(request.app.state.mgr.conn, job_id)
    if job is None:
        raise HTTPException(404, "job 不存在")
    return job


@router.post("/jobs", status_code=202)
async def post_job(body: JobIn, request: Request):
    if not valid_slug(body.slug):
        log.info("event=reject where=slug slug=%r", body.slug[:64])
        raise ApiError(422, "bad-slug", "bad slug")
    client = body.client.model_dump() if body.client else None
    runner = pick_runner(client["name"] if client else None, request.app.state.available)
    if runner is None:
        log.info("event=reject where=runner client=%r", client and client["name"][:64])
        raise ApiError(503, "no-runner", "沒有可用的 runner：目前只支援 Claude CLI")
    try:
        out = request.app.state.mgr.submit(body.slug, client, runner, resume_only=body.resume_only)
    except LookupError:
        raise ApiError(404, "unknown-work", "這篇不在 DB:先執行 python -m marrow.importer") from None
    except NothingToResume as e:
        raise ApiError(409, "nothing-to-resume", e.reason) from None
    return {**out, "runner": runner, "note": "會用你同一份訂閱額度"}


@router.get("/jobs")
async def list_jobs(request: Request, limit: int = 20):
    if not 1 <= limit <= _LIST_MAX:
        log.info("event=reject where=list-jobs limit=%s", limit)
        raise HTTPException(422, f"limit 要在 1–{_LIST_MAX}")
    rows = repo.list_jobs(request.app.state.mgr.conn, limit)
    return {"jobs": [{k: r[k] for k in _LIST_KEYS} for r in rows]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, request: Request):
    job = _job(request, job_id)
    conn = request.app.state.mgr.conn
    atts = repo.attempts(conn, job_id)
    return {**{k: job[k] for k in _JOB_KEYS}, "slug": repo.story(conn, job["story_id"])["slug"],
            "attempts": [{k: a[k] for k in _ATTEMPT_KEYS} for a in atts]}


async def _act(request: Request, job_id: int, verb: str):
    _job(request, job_id)
    if not getattr(request.app.state.mgr, verb)(job_id):
        log.info("event=reject where=%s job=%s", verb, job_id)
        raise HTTPException(409, f"目前狀態不能 {verb}")
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: int, request: Request):
    return await _act(request, job_id, "cancel")


@router.post("/jobs/{job_id}/resume")
async def resume(job_id: int, request: Request):
    return await _act(request, job_id, "resume")


@router.get("/jobs/{job_id}/events")
async def events(job_id: int, request: Request):
    _job(request, job_id)
    mgr = request.app.state.mgr

    async def stream():
        q = mgr.bus.subscribe(job_id)
        request.app.state.streams += 1
        try:
            if q.empty():   # 沒得補播:已結束(TTL 過了 / 上個行程跑的)就送現況收尾
                job = repo.get_job(mgr.conn, job_id)
                if job["state"] in _TERMINAL:
                    yield sse_line(_state_event(job))
                    return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), _SSE_POLL)
                except asyncio.TimeoutError:
                    # bus 不保證發收尾(worker 死在半路之類):DB 已結束就據實收尾
                    job = repo.get_job(mgr.conn, job_id)
                    if job["state"] in _TERMINAL and q.empty():
                        yield sse_line(_state_event(job))
                        return
                    yield ": ping\n\n"
                    continue
                yield sse_line(ev)
                if ev.get("event") in ("done", "error"):
                    return
        finally:
            request.app.state.streams -= 1
            mgr.bus.unsubscribe(job_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
