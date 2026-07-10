"""FastAPI 入口:把三個職責的 async generator 轉成 SSE 串給瀏覽器。

  POST /api/critique/{slug}              → SSE(phase/done/error)
  POST /api/discuss/{slug}               → SSE(token/message/done/error)
  GET  /api/discuss/{slug}/sessions      → 列 session
  DELETE /api/discuss/{slug}/{sid}       → 關 session
  POST /api/stories/extract  (multipart) → {filename, text}  只抽不寫
  POST /api/stories          (json)      → {slug}             落 source.md

跑:  uvicorn server.app:app --host 127.0.0.1 --port 8787   (在專案根)
"""
import asyncio
import json

from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from . import config, critique, discuss, ingest, log

app = FastAPI(title="hyenovel backend")


def _slug(slug: str) -> str:
    """守門:slug 來自 path,拼路徑/餵 argv 前先過白名單,擋路徑穿越與 argv 注入。"""
    if not config.valid_slug(slug):
        raise HTTPException(status_code=400, detail="bad slug")
    return slug


def _sse(gen):
    """把 {event,data} 的 async generator 轉成 text/event-stream。"""
    async def stream():
        async for ev in gen:
            data = json.dumps(ev["data"], ensure_ascii=False)
            yield f"event: {ev['event']}\ndata: {data}\n\n"
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.on_event("startup")
async def _startup():
    log.setup()
    asyncio.create_task(discuss.sweep_idle())
    asyncio.create_task(critique.sweep_runs())


@app.get("/api/health")
def health():
    return {"ok": True}


# ── 1. 觸發分析(背景 Run,可重接、可取消)────────────────────────────
@app.get("/api/critique/running")
def critique_running():
    return {"running": critique.list_running()}


@app.post("/api/critique/{slug}")
async def critique_start(slug: str, body: dict = Body(default={})):
    # 開始-或-接上:同一 slug 已在跑就補播+續播,不會重複派工。
    # fresh=新孕育(取消可清孤兒);既有故事再評論預設非 fresh → 取消絕不刪 source.md。
    return _sse(critique.attach(_slug(slug), body.get("title", ""), fresh=bool(body.get("fresh"))))


@app.delete("/api/critique/{slug}")
async def critique_cancel(slug: str):
    return {"cancelled": await critique.cancel(_slug(slug))}


# ── 3. 討論服務 ──────────────────────────────────────────────────────
@app.post("/api/discuss/{slug}")
async def discuss_turn(slug: str, body: dict = Body(default={})):
    return _sse(discuss.run_discuss(_slug(slug), body.get("session_id"), body.get("message", "")))


@app.get("/api/discuss/{slug}/sessions")
def discuss_sessions(slug: str):
    return {"sessions": discuss.list_sessions(_slug(slug))}


@app.delete("/api/discuss/{slug}/{session_id}")
async def discuss_close(slug: str, session_id: str):
    return {"closed": await discuss.close_session(session_id)}


# ── 新故事 ingestion ─────────────────────────────────────────────────
@app.post("/api/stories/extract")
async def stories_extract(file: UploadFile):
    # 只讀到上限 +1:巨檔不會整個進記憶體,超標當場擋(413)。
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        text = ingest.extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    return {"filename": file.filename, "text": text, "chars": len(text)}


@app.post("/api/stories")
def stories_create(body: dict = Body(...)):
    try:
        slug = ingest.create_story(body.get("title", ""), body.get("text", ""))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"slug": slug}
