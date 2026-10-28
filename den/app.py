"""den 的 HTTP 入口:job API + SSE,本機安全三件套(綁 127.0.0.1、Origin、token)、單一實例鎖。

  POST /stories             {"text","title"?,"slug"?} → 201 {slug, title, version, new_version, reused}
  GET  /stories/{slug}/discussion → 200 討論素材 | 404 | 409 未分析
  GET  /health              → {version, pid, busy}
  POST /jobs                {"kind":"critique","slug","client"?} → 202 {job_id, estimate, runner, note}
  GET  /jobs/{id}           → job 列 + attempts 摘要(不含 raw_output / prompt)
  POST /jobs/{id}/cancel    → 200 {"ok":true} | 409
  POST /jobs/{id}/resume    → 200 {"ok":true} | 409
  GET  /jobs/{id}/events    → SSE,每事件 `data: <json>\\n\\n`;一定會收尾

- 路由一律 async def:sqlite3 連線綁在 lifespan 建立它的事件迴圈執行緒,def 路由會被丟進 threadpool。
- 拒絕都記 INFO `event=reject where=...`(#21);token 與 Origin 原值不進 log。
"""
import asyncio
import functools
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Literal

import filelock
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from den import stories, version
from den.config import HOST, IDLE_CHECK, IDLE_EXIT, PHASE_TIMEOUT, PORT, valid_slug
from den.jobs import JobManager
from den.runner import ClaudePreset, cli_version, find_claude, pick_runner, run_job
from marrow import db, repo

log = logging.getLogger("hyenovel")

_TERMINAL = ("done", "paused", "failed", "cancelled")
_SSE_POLL = 15.0        # SSE 多久沒事件就回頭看 DB(兼 keep-alive)
_RESTART_DELAY = 1.0    # worker 死掉後隔多久重起(別讓壞 DB 變成熱迴圈)
_TOKEN_MIN = 32         # token_urlsafe(32) 是 43 字;短於此一律視為壞檔
_ATTEMPT_KEYS = ("step", "n", "outcome", "model", "duration_ms", "tokens")
_JOB_KEYS = ("id", "kind", "story_id", "source_version_id", "state", "step",
             "error_class", "detail", "params", "created_at", "updated_at")


class ClientIn(BaseModel):
    # 外部自報字串,進 DB 與 log:限長
    name: str = Field(max_length=64)
    version: str | None = Field(default=None, max_length=64)


class JobIn(BaseModel):
    kind: Literal["critique"]
    slug: str
    client: ClientIn | None = None


class StoryIn(BaseModel):
    text: str
    title: str | None = None
    slug: str | None = None


def load_token(data_dir: Path) -> str:
    """`<data_dir>/den.token`;不存在或太短(例:建檔後寫入前被殺 → 空檔)就重產。

    重產 = 暫存檔 O_EXCL + 0600 寫好再 os.replace:token 檔永遠不會是半成品或短暫可讀。
    呼叫者已持單一實例鎖,不會兩個 den 同時重產。
    """
    p = data_dir / "den.token"
    try:
        token = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = ""
    if len(token) >= _TOKEN_MIN:
        return token
    token = secrets.token_urlsafe(32)
    tmp = data_dir / f".den.token.{secrets.token_hex(8)}"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token + "\n")
    os.replace(tmp, p)
    log.info("event=token-created")
    return token


async def _supervise(mgr) -> None:
    """worker 例外死掉不能沉默(否則之後每個 job 永遠 queued):記下、收孤兒、重起。"""
    while True:
        try:
            await mgr.worker()
        except Exception:
            log.exception("event=worker-died")
            await asyncio.sleep(_RESTART_DELAY)
            try:
                mgr.startup()   # 死在半路的 running 已沒人跑,收成 crash 才能續
            except Exception:
                log.exception("event=worker-recover-failed")


def write_den_json(data_dir: Path, port: int, ver: str) -> None:
    """探索檔 `<data_dir>/den.json`:暫存檔 O_EXCL + 0600 再 os.replace,讀的人不會看到半成品。"""
    tmp = data_dir / f".den.json.{secrets.token_hex(8)}"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid(), "version": ver}, f)
    os.replace(tmp, data_dir / "den.json")


def remove_den_json(data_dir: Path) -> None:
    """只在檔內 pid 是自己時刪:別的 den 若已改寫,不能被我們收尾時誤刪。"""
    p = data_dir / "den.json"
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("pid") == os.getpid():
            p.unlink()
    except (OSError, ValueError, AttributeError):
        pass


async def _watch_idle(app: FastAPI, idle_exit, idle_check, clock, on_idle) -> None:
    while True:
        await asyncio.sleep(idle_check)
        try:   # 例:importer 同時寫 DB 造成 database is locked——這輪放過,別讓監看就此死掉
            if (clock() - app.state.last_seen >= idle_exit and app.state.streams == 0
                    and not repo.has_pending_jobs(app.state.mgr.conn)):
                log.info("event=den-idle-exit")
                on_idle()
                return
        except Exception:
            log.exception("event=idle-check-failed")


def _default_factory():
    exe = find_claude()
    if exe is None:
        raise RuntimeError("找不到 claude CLI(PATH 上沒有):先安裝 Claude Code 並登入再啟動 den")
    preset = ClaudePreset(exe)

    def factory(on_proc):
        return functools.partial(run_job, preset, timeout=PHASE_TIMEOUT, on_proc=on_proc)
    return factory, cli_version(exe)


def _sse_line(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


def _state_event(job: dict) -> dict:
    return {"event": "state", "data": {k: job[k] for k in ("state", "step", "error_class", "detail")}}


def create_app(conn_url: str, data_dir: Path, *, run_factory=None, port: int = PORT,
               idle_exit: float = IDLE_EXIT, idle_check: float = IDLE_CHECK,
               on_idle: Callable[[], None] | None = None, clock=time.monotonic) -> FastAPI:
    origins = {f"http://{HOST}:{port}", f"http://localhost:{port}"}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = filelock.FileLock(data_dir / "den.lock")
        try:
            lock.acquire(timeout=0)
        except filelock.Timeout:
            raise RuntimeError(f"den 已在執行(鎖在 {data_dir / 'den.lock'})") from None
        conn = None
        try:
            factory, ver = (run_factory, None) if run_factory else _default_factory()
            app.state.token = load_token(data_dir)
            app.state.version = version.fingerprint()   # 啟動時算一次;磁碟上現在的值由呼叫者現算比對
            app.state.available = ("claude",)           # 目前唯一 preset;其他家在 backlog
            app.state.last_seen = clock()
            app.state.streams = 0                       # 開著的 SSE 數;閒置退場不能砍到它
            conn = db.connect(conn_url)
            db.migrate(conn, db.sqlite_path(conn_url))
            mgr = JobManager(conn, factory, runner_name=ClaudePreset.runner_name, cli_version=ver)
            mgr.startup()
            app.state.mgr = mgr
            write_den_json(data_dir, port, app.state.version)
            worker = asyncio.create_task(_supervise(mgr))
            watcher = (asyncio.create_task(_watch_idle(app, idle_exit, idle_check, clock, on_idle))
                       if on_idle else None)
            log.info("event=den-start port=%s", port)
            try:
                yield
            finally:
                remove_den_json(data_dir)
                tasks = [t for t in (worker, watcher) if t]
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                log.info("event=den-stop")
        finally:
            if conn is not None:
                conn.close()
            lock.release()

    app = FastAPI(title="hyenovel den", lifespan=lifespan)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            # !r 且截斷:Origin 是外部輸入,可能夾換行偽造 log 行
            log.info("event=reject where=origin origin=%r", origin[:64])
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        auth = request.headers.get("authorization", "")
        token = request.app.state.token
        # token 為空時 want 會變成 "Bearer ",一律拒絕而非 fail-open
        if not token or not secrets.compare_digest(auth.encode(), f"Bearer {token}".encode()):
            log.info("event=reject where=token")
            return JSONResponse({"detail": "bad token"}, status_code=401)
        request.app.state.last_seen = clock()   # 通過 guard 才算活動:被拒的探測不續命
        return await call_next(request)

    def _job(request: Request, job_id: int) -> dict:
        job = repo.get_job(request.app.state.mgr.conn, job_id)
        if job is None:
            raise HTTPException(404, "job 不存在")
        return job

    @app.post("/jobs", status_code=202)
    async def post_job(body: JobIn, request: Request):
        if not valid_slug(body.slug):
            log.info("event=reject where=slug slug=%r", body.slug[:64])
            raise HTTPException(422, "bad slug")
        client = body.client.model_dump() if body.client else None
        runner = pick_runner(client["name"] if client else None, request.app.state.available)
        if runner is None:
            log.info("event=reject where=runner client=%r", client and client["name"][:64])
            raise HTTPException(503, "沒有可用的 runner：目前只支援 Claude CLI")
        try:
            out = request.app.state.mgr.submit(body.slug, client, runner)
        except LookupError:
            raise HTTPException(404, "這篇不在 DB:先執行 python -m marrow.importer") from None
        return {**out, "runner": runner, "note": "會用你同一份訂閱額度"}

    @app.get("/health")
    async def health(request: Request):
        return {"version": request.app.state.version, "pid": os.getpid(),
                "busy": repo.has_pending_jobs(request.app.state.mgr.conn)}

    @app.post("/stories", status_code=201)
    async def post_story(body: StoryIn, request: Request):
        conn = request.app.state.mgr.conn
        try:
            with conn:
                return stories.ingest(conn, body.text, body.title, body.slug, time.time())
        except ValueError as e:
            log.info("event=reject where=stories reason=%s", e)
            raise HTTPException(422, str(e)) from None

    @app.get("/stories/{slug}/discussion")
    async def get_discussion(slug: str, request: Request):
        if not valid_slug(slug):
            log.info("event=reject where=slug slug=%r", slug[:64])
            raise HTTPException(422, "bad slug")
        try:
            return stories.discussion_context(request.app.state.mgr.conn, slug)
        except LookupError:
            log.info("event=reject where=discussion reason=unknown-slug")
            raise HTTPException(404, "這篇不在 DB") from None
        except ValueError:
            log.info("event=reject where=discussion reason=not-analyzed")
            raise HTTPException(409, "這篇還沒分析完成") from None

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: int, request: Request):
        job = _job(request, job_id)
        atts = repo.attempts(request.app.state.mgr.conn, job_id)
        return {**{k: job[k] for k in _JOB_KEYS},
                "attempts": [{k: a[k] for k in _ATTEMPT_KEYS} for a in atts]}

    async def _act(request: Request, job_id: int, verb: str):
        _job(request, job_id)
        if not getattr(request.app.state.mgr, verb)(job_id):
            log.info("event=reject where=%s job=%s", verb, job_id)
            raise HTTPException(409, f"目前狀態不能 {verb}")
        return {"ok": True}

    @app.post("/jobs/{job_id}/cancel")
    async def cancel(job_id: int, request: Request):
        return await _act(request, job_id, "cancel")

    @app.post("/jobs/{job_id}/resume")
    async def resume(job_id: int, request: Request):
        return await _act(request, job_id, "resume")

    @app.get("/jobs/{job_id}/events")
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
                        yield _sse_line(_state_event(job))
                        return
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), _SSE_POLL)
                    except asyncio.TimeoutError:
                        # bus 不保證發收尾(worker 死在半路之類):DB 已結束就據實收尾
                        job = repo.get_job(mgr.conn, job_id)
                        if job["state"] in _TERMINAL and q.empty():
                            yield _sse_line(_state_event(job))
                            return
                        yield ": ping\n\n"
                        continue
                    yield _sse_line(ev)
                    if ev.get("event") in ("done", "error"):
                        return
            finally:
                request.app.state.streams -= 1
                mgr.bus.unsubscribe(job_id, q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
