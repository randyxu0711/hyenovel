"""作品:交稿、列表、詳情、對位、原文與分析、停下、viz、抽字、預估。"""
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from den import pipeline, stories, views, works
from den.config import MAX_SOURCE_BYTES
from den.estimate import estimate
from den.routes.common import ApiError, slug_ok, unknown_work
from marrow import ingest, repo, vizdata

log = logging.getLogger("hyenovel")
router = APIRouter()

_WORKS_MAX = 50
_STORY_ERRORS = {"空白故事": "empty-story", "原文過長": "story-too-long", "bad slug": "bad-slug",
                 "unknown slug": "unknown-slug-ref"}


class StoryIn(BaseModel):
    text: str
    title: str | None = None
    slug: str | None = None


@router.post("/stories", status_code=201)
async def post_story(body: StoryIn, request: Request):
    conn = request.app.state.mgr.conn
    try:
        with conn:
            return stories.ingest(conn, body.text, body.title, body.slug, time.time())
    except ValueError as e:
        log.info("event=reject where=stories reason=%s", e)
        raise ApiError(422, _STORY_ERRORS.get(str(e), "bad-slug"), str(e)) from None


@router.get("/stories")
async def list_stories(request: Request):
    return {"stories": views.stories(request.app.state.mgr.conn)}


@router.get("/works")
async def list_works(request: Request, q: str | None = None, limit: int = 20):
    if not 1 <= limit <= _WORKS_MAX:
        log.info("event=reject where=list-works limit=%s", limit)
        raise HTTPException(422, f"limit 要在 1–{_WORKS_MAX}")
    return {"works": works.listing(request.app.state.mgr.conn, q, limit)}


@router.get("/works/{slug}")
async def work_detail(slug: str, request: Request, v: int | None = Query(None, ge=1)):
    slug_ok(slug, "work-detail")
    try:
        return views.work_detail(request.app.state.mgr.conn, slug, v)
    except LookupError:
        raise unknown_work("work-detail") from None
    except views.UnknownVersion:
        log.info("event=reject where=work-detail reason=unknown-version v=%s", v)
        raise ApiError(404, "unknown-version", "沒有這個版本") from None


@router.get("/works/{slug}/map")
async def work_map(slug: str, request: Request, v: int | None = Query(None, ge=1)):
    slug_ok(slug, "work-map")
    try:
        return views.work_map(request.app.state.mgr.conn, slug, v)
    except LookupError:
        raise unknown_work("work-map") from None
    except views.UnknownVersion:
        log.info("event=reject where=work-map reason=unknown-version v=%s", v)
        raise ApiError(404, "unknown-version", "沒有這個版本") from None


@router.get("/estimate")
async def get_estimate(request: Request, chars: int = Query(ge=0)):
    conn = request.app.state.mgr.conn
    return {"estimate": estimate({s: repo.attempt_history(conn, s) for s in pipeline.CRITIQUE},
                                 chars)}


@router.get("/works/{slug}/{part}")
async def read_work(slug: str, part: str, request: Request):
    slug_ok(slug, "read-work")
    if part not in works.PARTS:
        log.info("event=reject where=read-work reason=bad-part part=%r", part[:32])
        raise ApiError(422, "bad-part", f"part 只能是 {'/'.join(works.PARTS)}")
    try:
        return {"text": works.read_part(request.app.state.mgr.conn, slug, part)}
    except LookupError:
        raise unknown_work("read-work") from None
    except works.Missing as e:
        log.info("event=reject where=read-work reason=%s", e.reason)
        raise ApiError(409, e.reason, e.reason) from None


@router.post("/works/{slug}/cancel")
async def cancel_work(slug: str, request: Request):
    slug_ok(slug, "cancel-work")
    mgr = request.app.state.mgr
    st = repo.story_by_slug(mgr.conn, slug)
    if st is None:
        raise unknown_work("cancel-work")
    done = [j["id"] for j in repo.active_jobs_of_story(mgr.conn, st["id"]) if mgr.cancel(j["id"])]
    if not done:
        log.info("event=reject where=cancel-work reason=nothing-running")
        raise ApiError(409, "nothing-running", "nothing-running")
    return {"cancelled": done}


@router.get("/stories/{slug}/viz")
async def get_viz(slug: str, request: Request):
    slug_ok(slug, "viz")
    conn = request.app.state.mgr.conn
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise unknown_work("viz")
    ana = repo.current_artifact(conn, st["id"], "analysis")
    if ana is None:
        log.info("event=reject where=viz reason=not-analyzed")
        raise ApiError(404, "not-analyzed", "這篇還沒分析完成")
    picked = vizdata.pick_judgment(ana, repo.current_artifact(conn, st["id"], "notes"),
                                   repo.current_artifact(conn, st["id"], "feedback"))
    src = repo.source_version(conn, ana["source_version_id"])["text"]
    return vizdata.viz_payload(slug, ana["body"], vizdata.judgment_for_viz(picked), src)


@router.get("/stories/{slug}/source")
async def get_source(slug: str, request: Request):
    slug_ok(slug, "source")
    conn = request.app.state.mgr.conn
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise unknown_work("source")
    ana = repo.current_artifact(conn, st["id"], "analysis")
    sv = (repo.source_version(conn, ana["source_version_id"]) if ana
          else repo.latest_source_version(conn, st["id"]))
    return PlainTextResponse(sv["text"], media_type="text/plain; charset=utf-8")


@router.get("/stories/{slug}/conclusions")
async def get_conclusions(slug: str, request: Request):
    slug_ok(slug, "conclusions")
    try:
        return {"conclusions": views.conclusions(request.app.state.mgr.conn, slug)}
    except LookupError:
        raise unknown_work("conclusions") from None


@router.get("/stories/{slug}/transcript")
async def get_transcript(slug: str, request: Request):
    slug_ok(slug, "transcript")
    try:
        return {"turns": views.transcript(request.app.state.mgr.conn, slug)}
    except LookupError:
        raise unknown_work("transcript") from None


@router.post("/extract")
async def extract(file: UploadFile):
    data = await file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        log.info("event=reject where=upload bytes=%s", len(data))
        raise ApiError(413, "file-too-large", "檔案太大")
    try:
        text = ingest.extract_text(file.filename or "", data)
    except ValueError as e:   # extract_text 內已記 event=extract-fail
        raise ApiError(400, "extract-failed", str(e)) from None
    return {"filename": file.filename, "text": text, "chars": len(text)}
