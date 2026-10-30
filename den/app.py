"""den 的 HTTP 入口:job API + SSE,本機安全三件套(綁 127.0.0.1、Origin、token)、單一實例鎖。

  POST /stories             {"text","title"?,"slug"?} → 201 {slug, title, version, new_version, reused}
  GET  /stories             → {"stories": [...]}(領域形狀,見 den.views)
  GET  /stories/{slug}/viz  → VizData | 404 無 current analysis(feedback 欄 = 同版備課筆記,否則同版舊回饋)
  GET  /stories/{slug}/source → text/plain,current analysis 所對照那一版的原文(無則最新版)
  GET  /stories/{slug}/conclusions → {"conclusions": [...]}
  GET  /stories/{slug}/transcript  → {"turns": [...]}
                            ({slug} 讀取路由:不合 slug → 400,不存在 → 404,皆記 reject)
  POST /extract             multipart `file` → {filename, text, chars} | 413 超限 | 400 抽字失敗
  GET  /stories/{slug}/discussion → 200 討論素材 | 404 | 409 未分析
  POST /discuss/{slug}      {"session_id"?, "message", "anchors"} → SSE token* → message + done | error
                            (串流前判:422 slug/body、404 無此篇/非此篇的局、409 未分析/該局有一輪在跑)
  GET  /works?q=&limit=N    → {"works": [...]}(標題/開頭比對,最近活動在前;limit 預設 20,1–50)
  GET  /works/{slug}/{part} → {"text"}(part = source/analysis/notes/feedback;422 part 不對、404 無此篇、
                            409 not-analyzed / no-notes / no-feedback)
  POST /works/{slug}/cancel → {"cancelled": [job_id...]} | 409 nothing-running
  GET  /health              → {version, pid, busy}
  POST /jobs                {"kind":"critique","slug","client"?} → 202 {job_id, estimate, existing, resumed, runner, note}
                            (同篇同版已在排隊/執行 → 回那個 job,existing=true,不建新的;
                             同版停在暫停/失敗/取消 → 接續最新那個,resumed=true)
  GET  /jobs?limit=N        → {"jobs": [{id, slug, title, state, step, error_class, updated_at,
                                       is_latest_version}]}
                            (最近更新的在前;limit 預設 20,1–100,超出 422)
  GET  /jobs/{id}           → job 列 + slug + attempts 摘要(不含 raw_output / prompt)
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
from contextlib import aclosing, asynccontextmanager, nullcontext
from pathlib import Path
from typing import Callable, Literal

import filelock
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from den import discuss, stories, version, views, works
from den.config import (CHAT_TIMEOUT, HOST, IDLE_CHECK, IDLE_EXIT, MAX_ANCHORS, MAX_CHAT_CHARS,
                        MAX_SOURCE_BYTES, PHASE_TIMEOUT, PORT, valid_slug)
from den.jobs import JobManager, NothingToResume
from den.runner import (ClaudePreset, cli_version, find_claude, pick_runner, run_job,
                        stream_chat)
from marrow import db, ingest, repo, vizdata

log = logging.getLogger("hyenovel")

_TERMINAL = ("done", "paused", "failed", "cancelled")
_SSE_POLL = 15.0        # SSE 多久沒事件就回頭看 DB(兼 keep-alive)
_RESTART_DELAY = 1.0    # worker 死掉後隔多久重起(別讓壞 DB 變成熱迴圈)
_TOKEN_MIN = 32         # token_urlsafe(32) 是 43 字;短於此一律視為壞檔
_ATTEMPT_KEYS = ("step", "n", "outcome", "model", "duration_ms", "tokens")
_LIST_KEYS = ("id", "slug", "title", "state", "step", "error_class", "updated_at",
              "is_latest_version")
_LIST_MAX = 100
_WORKS_MAX = 50
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
    resume_only: bool = False   # 不帶稿的交稿:只續跑,不開新的一次分析


class StoryIn(BaseModel):
    text: str
    title: str | None = None
    slug: str | None = None


class DiscussIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(default="", max_length=MAX_CHAT_CHARS)   # 空 = companion 先開口
    anchors: list[str] = Field(default_factory=list, max_length=MAX_ANCHORS)
    mode: Literal["direct", "slow", "imaginative"] | None = None   # 同 companion.MODES
    home: Literal["web", "mcp"] = "web"
    client: ClientIn | None = None


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
    """claude 只找一次;回 (job 的 run_factory, 討論的 chat_factory, CLI 版本)。"""
    exe = find_claude()
    if exe is None:
        raise RuntimeError("找不到 claude CLI(PATH 上沒有):先安裝 Claude Code 並登入再啟動 den")
    preset = ClaudePreset(exe)

    def factory(on_proc):
        return functools.partial(run_job, preset, timeout=PHASE_TIMEOUT, on_proc=on_proc)

    def chat_factory():
        return functools.partial(stream_chat, preset, timeout=CHAT_TIMEOUT)
    return factory, chat_factory, cli_version(exe)


def _sse_line(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


_BUSY = {"event": "error", "data": {"where": "discuss", "message": "這一局還有一輪在跑",
                                   "recoverable": True}}


async def _chat_stream(state, lock: asyncio.Lock | None, events):
    """一輪討論的 SSE 本體:算進開著的串流(閒置退場不砍)、整輪持該局的鎖。

    鎖在這裡拿而非端點:回應若沒開始送,generator 從沒進來,鎖也就不會漏放。
    被斷線關掉時 aclosing 一路關到 chat,工人隨之被殺。
    """
    state.streams += 1
    try:
        if lock is not None and lock.locked():   # 端點判過後、開始前被別人搶先(極窄)
            yield _sse_line(_BUSY)
            return
        async with lock or nullcontext(), aclosing(events):
            async for ev in events:
                yield _sse_line(ev)
    finally:
        state.streams -= 1


def _state_event(job: dict) -> dict:
    return {"event": "state", "data": {k: job[k] for k in ("state", "step", "error_class", "detail")}}


def create_app(conn_url: str, data_dir: Path, *, run_factory=None, chat_factory=None,
               port: int = PORT,
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
            if run_factory:   # 只有測試注入;沒注入 chat_factory 時討論端點不可用
                factory, default_chat, ver = run_factory, None, None
            else:
                factory, default_chat, ver = _default_factory()
            chat_f = chat_factory or default_chat
            app.state.chat = chat_f() if chat_f else None
            app.state.chat_locks = {}                   # f"{slug}/{session_id}" → 該局的鎖
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
            out = request.app.state.mgr.submit(body.slug, client, runner, resume_only=body.resume_only)
        except LookupError:
            raise HTTPException(404, "這篇不在 DB:先執行 python -m marrow.importer") from None
        except NothingToResume as e:
            raise HTTPException(409, e.reason) from None
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

    def _slug_ok(slug: str, where: str) -> None:
        if not valid_slug(slug):
            log.info("event=reject where=%s reason=bad-slug slug=%r", where, slug[:64])
            raise HTTPException(400, "bad slug")

    def _unknown(where: str) -> HTTPException:
        log.info("event=reject where=%s reason=unknown-slug", where)
        return HTTPException(404, "這篇不在 DB")

    @app.get("/stories")
    async def list_stories(request: Request):
        return {"stories": views.stories(request.app.state.mgr.conn)}

    @app.get("/works")
    async def list_works(request: Request, q: str | None = None, limit: int = 20):
        if not 1 <= limit <= _WORKS_MAX:
            log.info("event=reject where=list-works limit=%s", limit)
            raise HTTPException(422, f"limit 要在 1–{_WORKS_MAX}")
        return {"works": works.listing(request.app.state.mgr.conn, q, limit)}

    @app.get("/works/{slug}/{part}")
    async def read_work(slug: str, part: str, request: Request):
        _slug_ok(slug, "read-work")
        if part not in works.PARTS:
            log.info("event=reject where=read-work reason=bad-part part=%r", part[:32])
            raise HTTPException(422, f"part 只能是 {'/'.join(works.PARTS)}")
        try:
            return {"text": works.read_part(request.app.state.mgr.conn, slug, part)}
        except LookupError:
            raise _unknown("read-work") from None
        except works.Missing as e:
            log.info("event=reject where=read-work reason=%s", e.reason)
            raise HTTPException(409, e.reason) from None

    @app.post("/works/{slug}/cancel")
    async def cancel_work(slug: str, request: Request):
        _slug_ok(slug, "cancel-work")
        mgr = request.app.state.mgr
        st = repo.story_by_slug(mgr.conn, slug)
        if st is None:
            raise _unknown("cancel-work")
        done = [j["id"] for j in repo.active_jobs_of_story(mgr.conn, st["id"]) if mgr.cancel(j["id"])]
        if not done:
            log.info("event=reject where=cancel-work reason=nothing-running")
            raise HTTPException(409, "nothing-running")
        return {"cancelled": done}

    @app.get("/stories/{slug}/viz")
    async def get_viz(slug: str, request: Request):
        _slug_ok(slug, "viz")
        conn = request.app.state.mgr.conn
        st = repo.story_by_slug(conn, slug)
        if st is None:
            raise _unknown("viz")
        ana = repo.current_artifact(conn, st["id"], "analysis")
        if ana is None:
            log.info("event=reject where=viz reason=not-analyzed")
            raise HTTPException(404, "這篇還沒分析完成")
        picked = vizdata.pick_judgment(ana, repo.current_artifact(conn, st["id"], "notes"),
                                       repo.current_artifact(conn, st["id"], "feedback"))
        src = repo.source_version(conn, ana["source_version_id"])["text"]
        return vizdata.viz_payload(slug, ana["body"], vizdata.judgment_for_viz(picked), src)

    @app.get("/stories/{slug}/source")
    async def get_source(slug: str, request: Request):
        _slug_ok(slug, "source")
        conn = request.app.state.mgr.conn
        st = repo.story_by_slug(conn, slug)
        if st is None:
            raise _unknown("source")
        ana = repo.current_artifact(conn, st["id"], "analysis")
        sv = (repo.source_version(conn, ana["source_version_id"]) if ana
              else repo.latest_source_version(conn, st["id"]))
        return PlainTextResponse(sv["text"], media_type="text/plain; charset=utf-8")

    @app.get("/stories/{slug}/conclusions")
    async def get_conclusions(slug: str, request: Request):
        _slug_ok(slug, "conclusions")
        try:
            return {"conclusions": views.conclusions(request.app.state.mgr.conn, slug)}
        except LookupError:
            raise _unknown("conclusions") from None

    @app.get("/stories/{slug}/transcript")
    async def get_transcript(slug: str, request: Request):
        _slug_ok(slug, "transcript")
        try:
            return {"turns": views.transcript(request.app.state.mgr.conn, slug)}
        except LookupError:
            raise _unknown("transcript") from None

    @app.post("/extract")
    async def extract(file: UploadFile):
        data = await file.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            log.info("event=reject where=upload bytes=%s", len(data))
            raise HTTPException(413, "檔案太大")
        try:
            text = ingest.extract_text(file.filename or "", data)
        except ValueError as e:   # extract_text 內已記 event=extract-fail
            raise HTTPException(400, str(e)) from None
        return {"filename": file.filename, "text": text, "chars": len(text)}

    @app.post("/discuss/{slug}")
    async def discuss_turn(slug: str, body: DiscussIn, request: Request):
        def reject(code: int, reason: str, detail: str) -> HTTPException:
            log.info("event=reject where=discuss reason=%s", reason)
            return HTTPException(code, detail)
        if not valid_slug(slug):
            raise reject(422, "bad-slug", "bad slug")
        state = request.app.state
        try:
            turn = discuss.prepare_turn(state.mgr.conn, slug, body.session_id)
        except LookupError:
            raise reject(404, "unknown-slug", "這篇不在 DB") from None
        except discuss.UnknownSession:
            raise reject(404, "unknown-session", "這篇沒有這一局") from None
        lock = None
        if body.session_id is not None:   # 新局不會撞:id 這輪才發
            lock = state.chat_locks.setdefault(f"{slug}/{body.session_id}", asyncio.Lock())
            if lock.locked():
                raise reject(409, "busy", "這一局還有一輪在跑")
        client = body.client.model_dump() if body.client else None
        events = discuss.run_turn(state.mgr.conn, state.chat, turn, body.message, body.anchors,
                                  body.mode, body.home, client)
        return StreamingResponse(_chat_stream(state, lock, events), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/jobs")
    async def list_jobs(request: Request, limit: int = 20):
        if not 1 <= limit <= _LIST_MAX:
            log.info("event=reject where=list-jobs limit=%s", limit)
            raise HTTPException(422, f"limit 要在 1–{_LIST_MAX}")
        rows = repo.list_jobs(request.app.state.mgr.conn, limit)
        return {"jobs": [{k: r[k] for k in _LIST_KEYS} for r in rows]}

    @app.get("/jobs/{job_id}")
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
