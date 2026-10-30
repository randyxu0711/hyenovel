"""stdio MCP 轉接器:五個 tool + 兩個 prompt,薄薄一層翻成 den REST。入口 `python -m den.mcp`。

- stdout 只屬於 MCP 協定:本模組不 print,logging 只准 stderr(main 明確設)。
- den.request 是阻塞的(拉起 den 可能等十幾秒)→ 一律丟 anyio.to_thread。
- REST 4xx/5xx 與 DenUnavailable 一律轉成 ToolError(給人看的中文)。
- 每個回覆(含錯誤)文末附上 den 的提示(取走即清空,只附一次)。
- clientInfo 是提示不是授權:只帶給 den 挑 runner、記錄。
"""
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from den.client import DenClient, DenRejected, DenUnavailable
from den.companion import MODES
from den.config import MAX_CHAT_CHARS, MAX_SOURCE_BYTES
from marrow import db
from marrow.ingest import decode

log = logging.getLogger("hyenovel")

_SUFFIXES = (".md", ".txt")
_CLIENT_MAX = 64   # den 的 ClientIn 上限;超過整個 POST /jobs 會 422

_REASONS = {"usage-limit": "訂閱額度用完", "gate": "引文閘門重試耗盡",
            "overload": "服務過載", "auth": "Claude CLI 未登入或登入失效",
            "crash": "工人失敗", "timeout": "工人失敗(逾時)"}

# ≤4,096 字元(Claude Code 會靜默截斷);最重要的放第一句
INSTRUCTIONS = (
    "talk_to_companion 回傳的是陪讀角色 companion 對作者說的話:請一字不改地轉給作者,"
    "不要改寫、摘要、補充或加上你自己的評論。作者想聊自己寫的作品、想聽讀者感受時用 talk_to_companion。"
    "交稿用 submit_work(只收檔案路徑)、找作品 find_works、作者自己要看原文或分析用 read_work、"
    "停下分析用 cancel_work。作品用標題或關鍵詞指定,不必記編號。")
DESC_TALK = (
    "和陪讀的 companion 說話,回傳它的回覆——請原文轉給作者,不要改寫、摘要或補充。"
    "作者對 companion 說的任何話(包括「好了沒」)都用這個。message 留空 = 讓 companion 先開口。"
    "work = 作品標題或開頭裡的關鍵詞(例「海」);省略則沿用剛聊的那篇,或最近的一篇。"
    "mode = direct(直說)/ slow(慢讀,預設)/ imaginative(想像);"
    "作者說「講重點就好」時用 direct,「慢慢講」用 slow,「陪我想像」用 imaginative,沒提就不要給。")
_TALK_FAILED = "。請照實告訴作者這一輪沒有成功,不要自己代答。"
_NO_SESSION = "這篇沒有這一局"   # den /discuss 的 404 detail(局不見了;拒絕在花錢前)
DESC_FIND = ("列出作者的作品(標題、開頭、分析狀態、最近聊的時間)。作者問「我有哪些作品」「上次那篇海的」時用;"
             "query 給標題或開頭裡的關鍵詞(例「海」),不給就列最近的。")
DESC_READ = ("讀一篇作品的資料給作者看:part = source(原文)/ analysis(客觀結構分析)/ "
             "notes(備課筆記:另一位冷讀者依輕重排好的問題清單,作者說「直接給我問題」「冷一點的版本」時用)/ "
             "feedback(舊版客觀回饋)。給 notes 時要跟作者說明這是另一位冷讀者的筆記,不是 companion 的感受。"
             "只在作者自己要看時用,不要拿來代替 companion 回答。work 同 talk_to_companion。")
DESC_SUBMIT = (
    "交一篇稿子給 hyenovel:只收本機 .md / .txt 檔案路徑(不收貼上的全文、不收 pdf/docx——請作者先存成純文字檔)。"
    "改稿重交請帶 work(作品標題或關鍵詞)。不給 path = 續跑這篇停住的分析(不會重跑已完成的)。"
    "分析在背景跑幾分鐘,回報收到的檔名、修改時間、字數,請作者確認是對的檔。會用作者同一份 Claude 訂閱額度。")
DESC_CANCEL_WORK = "停下一篇作品正在跑的分析(作者說「先別跑了」)。停下後可用不帶 path 的 submit_work 續跑。"
_PARTS = ("source", "analysis", "notes", "feedback")
_WORK_STATES = {"ready": "分析好了", "running": "分析中", "stale": "改過稿,新版還沒分析", "none": "沒有分析"}
_READONLY = ToolAnnotations(readOnlyHint=True)
# prompts 不收參數:Claude Code 以空白切參數,含空白的路徑會斷(spec §11)
PROMPT_COMPANION = (
    "我想跟 hyenovel 的 companion 聊我的作品。如果我還沒說要聊哪個檔,先問我稿子的檔案路徑(.md / .txt),"
    "或我只是想直接聊最近那篇。拿到路徑就用 submit_work 交稿、把回報給我確認;"
    "然後用 talk_to_companion(message 留空)讓 companion 先開口。companion 的回覆請一字不改地轉給我。")
PROMPT_CONTINUE = ("接著聊我最近那篇:用 talk_to_companion(message 留空、不給 work)讓 companion 先開口,"
                   "回覆一字不改地轉給我。")


def _when(ts: float | None) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else ""


def _work_line(w: dict) -> str:
    st = w["state"]
    if st == "stopped":
        cls = w.get("error_class")
        label = f"分析停住了({_REASONS.get(cls, cls)})" if cls else "分析停住了"
    else:
        label = _WORK_STATES.get(st, st)
    talked = f"最近聊 {_when(w['talked_at'])}" if w.get("talked_at") else "還沒聊過"
    return f"〈{w['title']}〉開頭「{w['opening']}」· {label} · {talked}"


def client_of(ctx: Context) -> dict | None:
    """`{"name","version"}` 或 None(client_params 可能不存在)。外部自報字串,截到 den 的上限。"""
    cp = ctx.session.client_params
    info = cp.client_info if cp else None
    if info is None:
        return None
    ver = info.version[:_CLIENT_MAX] if info.version else None
    return {"name": info.name[:_CLIENT_MAX], "version": ver}


def _reject(reason: str, msg: str) -> ToolError:
    log.info("event=reject where=mcp reason=%s", reason)
    return ToolError(msg)


def _detail(r) -> str:
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        d = None
    return str(d) if d else r.text[:200]


def _read_source(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        raise _reject("missing", f"找不到檔案:{p}")
    if not p.is_file():
        raise _reject("not-file", f"{p} 不是檔案(是資料夾或特殊檔)。")
    if p.suffix.lower() not in _SUFFIXES:
        raise _reject("suffix", "只收 .md / .txt。PDF / Word 抽字會弄壞引文比對,"
                                "請先轉成純文字、檢查過再給我路徑。")
    try:
        size = p.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise _reject("oversize", f"檔案 {size} bytes,超過 {MAX_SOURCE_BYTES // (1024 * 1024)} MB 上限。")
        text = decode(p.read_bytes())
    except OSError as e:
        raise _reject("unreadable", f"讀不了檔案:{e.strerror or e}") from None
    if not text.strip():
        raise _reject("empty", "檔案是空的。")
    return text


def _minutes(est: dict | None) -> str:
    if not est:
        return "第一次跑,約 1–3 分鐘"
    return f"預估約 {max(1, round(est['seconds'] / 60))} 分鐘(依過去 {est['basis']} 次紀錄)"


def build_server(den: DenClient) -> MCPServer:
    server = MCPServer("hyenovel", instructions=INSTRUCTIONS)

    async def call(method: str, path: str, json: dict | None = None, *,
                   on_status: dict[int, str] | None = None,
                   on_detail: dict[str, str] | None = None,
                   ok_details: tuple[str, ...] = ()) -> dict:
        try:
            r = await anyio.to_thread.run_sync(lambda: den.request(method, path, json=json))
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}") from None
        if r.status_code >= 400:
            if _detail(r) in ok_details:   # 呼叫者要自己分流的拒絕:回 {"detail": …},不當錯誤
                return {"detail": _detail(r)}
            msg = (on_detail or {}).get(_detail(r)) or (on_status or {}).get(r.status_code)
            raise ToolError(msg or f"den 回應 {r.status_code}:{_detail(r)}")
        return r.json()

    def tail(text: str) -> str:
        notes = den.take_notices()
        return text + ("\n\n" + "\n".join(notes) if notes else "")

    async def guarded(work) -> str:
        try:
            text = await work
        except ToolError as e:
            raise ToolError(tail(str(e))) from None
        return tail(text)

    sessions: dict[str, str] = {}   # 這個 shim 行程(= 一個宿主 session)裡:slug → 對話 id
    current: list[str] = []         # 最近一次聊的那篇

    async def _works(**params) -> list[dict]:
        return (await call("GET", "/works?" + urlencode({k: v for k, v in params.items() if v is not None})))["works"]

    async def resolve_work(work: str | None) -> dict:
        """作者的說法 → 一篇作品(`GET /works` 的一筆)。slug / 標題關鍵詞 / 剛聊的 / 最近的。"""
        if work is None:
            hits = await _works(q=current[0]) if current else []
            hits = hits or await _works(limit=1)
            if not hits:
                raise _reject("no-work", "還沒有任何作品。請給我稿子的檔案路徑(.md / .txt)。")
            return hits[0]
        hits = await _works(q=work)
        if not hits:
            raise _reject("work-not-found", f"找不到「{work}」這篇。可以用 find_works 看有哪些作品。")
        if len(hits) > 1:
            raise _reject("work-ambiguous", "\n".join(
                [f"有 {len(hits)} 篇符合「{work}」,請問作者是哪一篇:"] + [_work_line(w) for w in hits]
                + ["請用標題裡更完整的字再試一次。"]))
        return hits[0]

    async def _find(query: str | None) -> str:
        hits = await _works(q=query)
        if not hits:
            return f"沒有符合「{query}」的作品。" if query and query.strip() else "目前沒有任何作品。"
        return "\n".join(_work_line(w) for w in hits)

    @server.tool(description=DESC_FIND, annotations=_READONLY)
    async def find_works(query: str | None = None) -> str:
        return await guarded(_find(query))

    async def _read(part: str, work: str | None) -> str:
        if part not in _PARTS:
            raise _reject("part", "part 只能是 source(原文)/ analysis(分析)/ notes(備課筆記)/ feedback(舊版客觀回饋)。")
        w = await resolve_work(work)
        name = f"〈{w['title']}〉"
        out = await call("GET", f"/works/{w['slug']}/{part}", on_status={404: f"找不到{name}。"},
                         on_detail={"not-analyzed": f"{name}還沒有分析。",
                                    "no-notes": f"{name}還沒有備課筆記。",
                                    "no-feedback": f"{name}沒有舊版客觀回饋。"})
        return out["text"]

    def _stopped_why(j: dict) -> str:
        cls = j.get("previous_error_class")
        if cls:
            return f"上次停在:{_REASONS.get(cls, cls)}"
        return "上次是你取消的。" if j.get("previous_state") == "cancelled" else "上次沒有跑完。"

    async def _submit_file(path: str, work: str | None, title: str | None, client) -> str:
        text = _read_source(path)
        p = Path(path).expanduser()
        slug = (await resolve_work(work))["slug"] if work else None
        sent_title = title if title is not None else (None if work else p.stem)
        s = await call("POST", "/stories", {"text": text, "title": sent_title, "slug": slug})
        current[:] = [s["slug"]]   # 交完稿,「這篇」就是它(否則下一句不帶 work 會聊回上一篇)
        job = {"kind": "critique", "slug": s["slug"], "client": client}
        # 稿子沒改:只續跑;這版已分析好就不重跑(重送同一個檔不該再花一次錢)。從沒跑過才開新的
        j = (await call("POST", "/jobs", {**job, "resume_only": True}, ok_details=("done", "never"))
             if not s["new_version"] else None)
        if j is not None and j.get("detail") == "never":
            j = None
        if j is None:
            j = await call("POST", "/jobs", job)
        name = (await _works(q=s["slug"]))[0]["title"]   # 跟 find_works 同源:分析抽出的標題優先於檔名
        chars = sum(not ch.isspace() for ch in text)
        lines = [f"收到 {p.name}({_when(p.stat().st_mtime)} 修改,{chars:,} 字),作品〈{name}〉。"]
        if s["reused"]:
            lines.append(f"這份稿子和〈{name}〉最新一版一樣,沿用那篇。")
        if j.get("detail") == "done":
            lines.append("這一版已經分析好了,沒有重跑。要聊就讓 companion 開口;改了稿再交新檔。")
        elif j.get("resumed"):
            lines += ["這一版之前跑到一半,已接續(已完成的步驟不重跑)。", _stopped_why(j)]
        elif j["existing"]:
            lines.append("這一版已經在分析中,沒有再開一次。")
        else:
            lines.append(f"分析已開始,{_minutes(j['estimate'])}。會用你同一份訂閱額度。")
        if j.get("detail") != "done":
            lines.append("分析在背景跑,不用等;現在就可以用 talk_to_companion 讓 companion 先開口。")
        return "\n".join(lines)

    async def _resume(work: str | None, client) -> str:
        w = await resolve_work(work)
        current[:] = [w["slug"]]
        name = f"〈{w['title']}〉"
        j = await call("POST", "/jobs", {"kind": "critique", "slug": w["slug"], "client": client,
                                         "resume_only": True}, on_detail={
            "done": f"{name}最新一版已經分析好了,不用再跑。改了稿請給我新檔的路徑。",
            "never": f"{name}最新一版還沒開始分析,請再給我一次檔案路徑交稿。"})
        if j.get("resumed"):
            return f"{name}已接著上次停下的地方續跑。{_stopped_why(j)}"
        return f"{name}已經在分析中。"

    @server.tool(description=DESC_SUBMIT)
    async def submit_work(ctx: Context, path: str | None = None, work: str | None = None,
                          title: str | None = None) -> str:
        if path is None:
            return await guarded(_resume(work, client_of(ctx)))
        return await guarded(_submit_file(path, work, title, client_of(ctx)))

    async def _cancel_work(work: str | None) -> str:
        w = await resolve_work(work)
        name = f"〈{w['title']}〉"
        await call("POST", f"/works/{w['slug']}/cancel", on_status={409: f"{name}現在沒有在分析。"})
        return f"{name}的分析已停下;之後不帶路徑呼叫 submit_work 可以接著跑。"

    @server.tool(description=DESC_CANCEL_WORK)
    async def cancel_work(work: str | None = None) -> str:
        return await guarded(_cancel_work(work))

    @server.tool(description=DESC_READ, annotations=_READONLY)
    async def read_work(part: str, work: str | None = None) -> str:
        return await guarded(_read(part, work))
    in_flight: set[str] = set()     # 正在跑一輪的篇:首輪還沒局 id、den 的鎖擋不到,由這裡擋(免得付兩次錢)

    def _turn(slug: str, body: dict) -> dict:
        """收齊一輪 SSE,回 message 事件的 data;error 事件 → ToolError。"""
        for ev in den.stream("POST", f"/discuss/{slug}", body):
            if ev["event"] == "message":
                return ev["data"]
            if ev["event"] == "error":
                raise ToolError(ev["data"]["message"] + _TALK_FAILED)
        raise ToolError("companion 沒有回應" + _TALK_FAILED)

    async def _talk(message: str, work: str | None, mode: str | None, client) -> str:
        if mode is not None and mode not in MODES:
            raise _reject("mode", "模式只有 direct(直說)/ slow(慢讀)/ imaginative(想像)。")
        if len(message) > MAX_CHAT_CHARS:   # 本地擋:den 的 422 會把整段原文回吐給宿主
            raise _reject("too-long", f"這段話超過 {MAX_CHAT_CHARS} 字,請分段說。")
        try:
            slug = (await resolve_work(work))["slug"]
        except ToolError as e:
            raise ToolError(str(e) + _TALK_FAILED) from None
        if slug in in_flight:
            raise _reject("busy", "上一輪還在跑,等它回來再說" + _TALK_FAILED)
        in_flight.add(slug)
        try:
            return await _talk_once(slug, message, mode, client)
        finally:
            in_flight.discard(slug)

    async def _talk_once(slug: str, message: str, mode: str | None, client) -> str:
        body = {"session_id": sessions.get(slug), "message": message, "anchors": [],
                "mode": mode, "home": "mcp", "client": client}
        try:
            try:
                data = await anyio.to_thread.run_sync(lambda: _turn(slug, body))
            except DenRejected as e:
                if not (e.status == 404 and e.detail == _NO_SESSION and body["session_id"]):
                    raise
                sessions.pop(slug, None)      # 局不見了(DB 重建):開新局,拒絕發生在花錢前
                body["session_id"] = None
                data = await anyio.to_thread.run_sync(lambda: _turn(slug, body))
        except DenRejected as e:
            if e.status == 404:
                raise ToolError(f"找不到這篇:{slug}" + _TALK_FAILED) from None
            if e.status == 409:
                raise ToolError("上一輪還在跑,等它回來再說" + _TALK_FAILED) from None
            raise ToolError(f"den 回應 {e.status}" + _TALK_FAILED) from None
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}{_TALK_FAILED}") from None
        sessions[slug] = data["session_id"]
        current[:] = [slug]
        return data["text"]

    @server.tool(description=DESC_TALK)
    async def talk_to_companion(ctx: Context, message: str = "", work: str | None = None,
                                mode: str | None = None) -> str:
        return await guarded(_talk(message, work, mode, client_of(ctx)))

    @server.prompt(description="開始陪讀:交一篇稿子(或直接聊最近那篇),讓 companion 先開口。")
    def companion() -> str:
        return PROMPT_COMPANION

    @server.prompt(name="continue", description="接著聊最近那篇,companion 先開口。")
    def continue_() -> str:
        return PROMPT_CONTINUE

    return server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    build_server(DenClient(db.data_dir())).run("stdio")


if __name__ == "__main__":
    main()
