"""FastAPI 入口:把三個職責的 async generator 轉成 SSE 串給瀏覽器。

  POST /api/critique/{slug}              → SSE(phase/done/error)
  POST /api/discuss/{slug}               → SSE(token/thinking/message/done/error)
  GET  /api/discuss/{slug}/sessions      → 列 session
  GET  /api/transcript/{slug}            → 逐字歷史(唯讀)
  DELETE /api/discuss/{slug}/{sid}       → 關 session
  POST /api/stories/extract  (multipart) → {filename, text}  只抽不寫
  POST /api/stories          (json)      → {slug}             落 source.md

跑:  uvicorn server.app:app --host 127.0.0.1 --port 8787   (在專案根)
"""
import asyncio
import json

from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

import recall

from . import align, config, critique, discuss, ingest, ledger, log, settle, transcript
from .log import log as logger

app = FastAPI(title="hyenovel backend")


def _slug(slug: str) -> str:
    """守門:slug 來自 path,拼路徑/餵 argv 前先過白名單,擋路徑穿越與 argv 注入。"""
    if not config.valid_slug(slug):
        # !r 不是排版:被拒的 slug 是原始使用者輸入,可能夾 \n 偽造出一整行假 log。
        logger.info(f"event=reject where=slug slug={slug[:64]!r}")
        raise HTTPException(status_code=400, detail="bad slug")
    return slug


def _anchors(raw) -> list[str]:
    """守門:anchors 來自 HTTP body,會被寫進磁碟上的正本。
    只收字串、夾 16 個上限 —— 不是安全漏洞,是不讓一個手滑的 body 灌爆逐字檔。"""
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, str)][:16]


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
    critique.scan_crashed()     # 同步、便宜:標出無活 Run 卻仍 running 的孤兒
    asyncio.create_task(discuss.sweep_idle())
    asyncio.create_task(critique.sweep_runs())
    asyncio.create_task(settle.sweep_settle())   # 討論結束後自動收束成結論
    asyncio.create_task(align.sweep_align())     # 跨篇概念地圖 stale 就重建


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
    # mode=reanalyze:先守門 + snapshot 到 .prev,再由 attach 接上同一個 Run 的串流。
    s = _slug(slug)
    if body.get("mode") == "reanalyze":
        try:
            critique.reanalyze(s, body.get("title", ""))
        except ValueError as e:
            logger.info(f"event=reject where=reanalyze slug={s} reason={e}")
            raise HTTPException(status_code=409, detail=str(e))
    return _sse(critique.attach(s, body.get("title", ""), fresh=bool(body.get("fresh"))))


@app.delete("/api/critique/{slug}")
async def critique_cancel(slug: str):
    return {"cancelled": await critique.cancel(_slug(slug))}


# ── 3. 討論服務 ──────────────────────────────────────────────────────
@app.post("/api/discuss/{slug}")
async def discuss_turn(slug: str, body: dict = Body(default={})):
    return _sse(discuss.run_discuss(_slug(slug), body.get("session_id"),
                                    body.get("message", ""), _anchors(body.get("anchors"))))


@app.get("/api/discuss/{slug}/sessions")
def discuss_sessions(slug: str):
    return {"sessions": discuss.list_sessions(_slug(slug))}


@app.delete("/api/discuss/{slug}/{session_id}")
async def discuss_close(slug: str, session_id: str):
    return {"closed": await discuss.close_session(session_id)}


@app.get("/api/conclusions/{slug}")
def conclusions_list(slug: str):
    """單篇過去討論結論(唯讀,含 stale 旗標)——前端「喚燼可見」的資料來源。
    完整列舉、不截斷:recall() 的 budget 是給 LLM 注入用的,視覺不能因預算藏掉一顆燼。"""
    return {"conclusions": recall.list_conclusions(_slug(slug))}


@app.get("/api/transcript/{slug}")
def transcript_list(slug: str):
    """單篇討論的逐字歷史(唯讀)——F5 之後畫面接得回來的資料來源。

    正本一直躺在 `transcript.jsonl`(P1 起逐輪寫),前端從沒讀過它:「討論不再蒸發」
    在後端成立、在使用者眼裡沒成立。這支只是把正本原樣露出去。
    **不做摘要、不做過濾**:逐字就是逐字,要挑要分組是前端的事。
    """
    return {"turns": transcript.load(_slug(slug))}


# ── 新故事 ingestion ─────────────────────────────────────────────────
@app.post("/api/stories/extract")
async def stories_extract(file: UploadFile):
    # 只讀到上限 +1:巨檔不會整個進記憶體,超標當場擋(413)。
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        logger.info(f"event=reject where=upload bytes={len(data)}")
        raise HTTPException(status_code=413, detail=f"檔案過大(> {config.MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    try:
        text = ingest.extract_text(file.filename or "", data)
    except ValueError as e:      # 壞檔 / 加密 / 讀不了 → 400,不冒成 500
        # 這條不記 reject:ingest.extract_text 內已 log.exception(event=extract-fail)。
        raise HTTPException(status_code=400, detail=str(e))
    return {"filename": file.filename, "text": text, "chars": len(text)}


@app.post("/api/stories")
def stories_create(body: dict = Body(...)):
    try:
        slug = ingest.create_story(body.get("title", ""), body.get("text", ""))
    except ValueError as e:
        logger.info(f"event=reject where=create reason={e}")
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"slug": slug}


# ── 用量帳本(讀時聚合,不落檔)─────────────────────────────────────
@app.get("/api/usage")
def usage_all():
    return ledger.aggregate_all()


@app.get("/api/usage/{slug}")
def usage_one(slug: str):
    return ledger.aggregate(_slug(slug))
