"""stdio MCP 轉接器:十個 tool + 兩個 prompt,薄薄一層翻成 den REST。入口 `python -m den.mcp`。

- stdout 只屬於 MCP 協定:本模組不 print,logging 只准 stderr(main 明確設)。
- den.request 是阻塞的(拉起 den 可能等十幾秒)→ 一律丟 anyio.to_thread。
- REST 4xx/5xx 與 DenUnavailable 一律轉成 ToolError(給人看的中文)。
- 每個回覆(含錯誤)文末附上 den 的提示(取走即清空,只附一次)。
- clientInfo 是提示不是授權:只帶給 den 挑 runner、記錄。
"""
import logging
import sys
import time
import unicodedata
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from den import cards
from den.client import DenClient, DenRejected, DenUnavailable
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
    "talk_to_companion 回傳的是陪讀角色 companion 對作者說的話:一字不改地轉給作者,"
    "不改寫、摘要、補充,也不加你自己的評論,因為作者是在跟 companion 對話。"
    "作者想聊自己寫的作品、想聽讀者感受時用 talk_to_companion,不要自己評論作品或讀分析代答。"
    "交稿用 submit_work(只收檔案路徑)、找作品用 find_works、作者自己要看原文或分析用 read_work、"
    "停下分析用 cancel_work。作品用標題或關鍵詞指定,不必記編號。"
    "作者問有哪些陪讀角色、現在是誰時用 list_characters;作者點名要換才用 set_character。"
    "作者要建新角色時先問作者的想像,再用 create_character;選哪個由作者決定,選定後用 save_character。"
    "作者明說要清空、壓縮對話,或把丟進對話的稿開成作品時用 manage_chat。")
DESC_TALK = (
    "和陪讀的 companion 說話,回傳它的回覆。把回覆原文轉給作者,不改寫、摘要或補充。"
    "作者對 companion 說的任何話都用這個,包括「好了沒」。交稿或作者自己要看資料時改用 submit_work、read_work。"
    "message 留空 = 讓 companion 先開口。"
    "work = 作品標題或開頭裡的關鍵詞(例「海」);省略則沿用剛聊的那局,或最近的一局。"
    "new_chat=true 用在作者說想聊別的、不聊作品:開一局不綁作品的新對話。"
    "attach_path 用在不綁作品的對話裡作者給了 .md / .txt 檔、但沒說要交稿分析:把稿丟進對話給 companion 讀;要分析改用 submit_work。")
DESC_MANAGE_CHAT = (
    "作者明說要清空對話、壓縮對話、或把丟進對話的稿開成作品時才用;不要自己判斷該不該清或壓。"
    "作用在剛聊的那局。action:clear(清空對話,稿留著)/ compact(把之前的對話壓成摘要,花一次訂閱額度)/"
    " adopt(把丟進對話的稿開成作品,只存不分析;attachment 是第幾份,只有一份時可省略)。")
DESC_LIST_CHARACTERS = (
    "列出陪讀角色(id、名字、一句話)並標出這篇目前是誰。作者問有哪些角色、現在是誰時用。"
    "work 用法同 talk_to_companion。")
DESC_SET_CHARACTER = (
    "換陪讀角色,下一輪起由這隻接著讀,只影響這篇這一局。character 是 list_characters 給的 id。"
    "只有作者點名要換時才用,因為角色是作者的選擇,不要依語氣或內容自己判斷。")
DESC_CREATE_CHARACTER = (
    "替作者生成三個陪讀角色候選。只有作者要建角色才用;作者想換現有角色時用 set_character。"
    "呼叫前先用開放題問作者的想像,開放題不放例子。作者的話原樣填進參數,沒回答的留空,不要替作者答,因為這個角色是作者的想像。"
    "form:陪作者讀稿的是什麼;wish:作者想要它怎麼讀;lang:zh-Hant 或 en,跟作者用的語言。"
    "會花作者的訂閱額度,可能要幾分鐘。回傳的候選照列給作者,選哪個由作者決定。改候選、複製、編輯角色請作者到網頁做。")
DESC_SAVE_CHARACTER = (
    "把作者選定的候選存成陪讀角色。number 是 create_character 回傳的編號,只有作者選定後才用。"
    "name 只在作者自己取了名字時給。回覆說有警告時,把警告告訴作者,作者確認要存才帶 confirm=true 再呼叫一次。")
_TALK_FAILED = "。請照實告訴作者這一輪沒有成功,不要自己代答。"
_NO_SESSION = "這篇沒有這一局"   # den /discuss 的 404 detail(局不見了;拒絕在花錢前)
DESC_FIND = ("列出作者的作品(標題、開頭、分析狀態、最近聊的時間)。作者問「我有哪些作品」「上次那篇海的」時用;"
             "query 給標題或開頭裡的關鍵詞(例「海」),不給就列最近的。")
DESC_READ = ("讀一篇作品的資料給作者看:part = source(原文)/ analysis(客觀結構分析)/ "
             "notes(備課筆記:另一位冷讀者依輕重排好的判斷,作者說「直接給我問題」「冷一點的版本」時用)/ "
             "feedback(舊版客觀回饋)。給 notes 時跟作者說明這是另一位冷讀者的筆記,不是 companion 的感受。"
             "只在作者自己要看時用,不要拿來代替 companion 回答,也不要主動把內容放進 talk_to_companion 的 message,"
             "因為 companion 要自己讀。work 同 talk_to_companion。")
DESC_SUBMIT = (
    "交一篇稿子給 hyenovel:作者給了本機 .md / .txt 檔案路徑時用。貼上的全文、pdf、docx 不收,請作者先存成純文字檔。"
    "改稿重交時帶 work(作品標題或關鍵詞)。不給 path = 續跑這篇停住的分析,已完成的不會重跑。"
    "分析在背景跑幾分鐘,會用作者同一份 Claude 訂閱額度。回覆裡有收到的檔名、修改時間、字數,請作者確認是對的檔。")
DESC_CANCEL_WORK = "作者說「先別跑了」時用,停下一篇作品正在跑的分析。停下後可用不帶 path 的 submit_work 續跑。"
_PARTS = ("source", "analysis", "notes", "feedback")
_CANDIDATES = 20   # 作品有歧義時最多列幾篇
_WORK_STATES = {"ready": "分析好了", "running": "分析中", "stale": "改過稿,新版還沒分析", "none": "沒有分析",
                "notes-running": "分析好了,備課筆記還在跑"}
_READONLY = ToolAnnotations(readOnlyHint=True)
_GENERATE_TIMEOUT = 400   # 每次最長 180 秒、含修補兩次
_CANDIDATE_REASONS = {**_REASONS, "gate": "候選沒通過檢查"}
_CARD_WARNINGS = {"looks-like-instructions": "有像指令的文字", "newer-spec": "規格版本比較新",
                  "ignored-fields": "有不會採用的欄位", "bad-colors": "顏色看不清楚"}
# prompts 不收參數:Claude Code 以空白切參數,含空白的路徑會斷(spec §11)
PROMPT_COMPANION = (
    "我想跟 hyenovel 的 companion 聊。我給了稿子的檔案路徑(.md / .txt)就用 submit_work 交稿、把回報給我確認,"
    "再用 talk_to_companion(message 留空)讓 companion 先開口;我沒給路徑也沒指定作品,"
    "就用 talk_to_companion(new_chat=true、message 留空)直接聊。companion 的回覆請一字不改地轉給我。")
PROMPT_CONTINUE = ("接著聊最近那局:用 talk_to_companion(message 留空、不給 work)讓 companion 先開口,"
                   "回覆一字不改地轉給我。")


def _generation_failed(r) -> str:
    reason = r.json().get("params", {}).get("reason")
    return f"候選生成失敗({_CANDIDATE_REASONS.get(reason, reason)})。請照實告訴作者,不要自己替作者寫候選。"


def _card_warnings(warnings: list[str]) -> str:
    return "、".join(_CARD_WARNINGS.get(w, w) for w in warnings)


def _shown(text: str, hidden: str) -> str:
    flat = " ".join(text.split())
    return hidden if cards._INSTRUCTIONS.search(unicodedata.normalize("NFKC", flat)) else flat


def _candidate_lines(n: int, c: dict, lang: str) -> list[str]:
    name, form = _shown(c["name"][lang], "這個名字沒顯示"), _shown(c["form"][lang], "這個形體沒顯示")
    lines = [f"{n}. {name}({form}):{_shown(c['line'][lang], '這句介紹沒顯示')}"]
    if c["sample"]:
        lines.append(f"   試讀:{_shown(c['sample'], '這句試讀沒顯示')}")
    if c["warnings"]:
        lines.append(f"   注意:{_card_warnings(c['warnings'])}")
    return lines


def _when(ts: float | None) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else ""


def _work_line(w: dict) -> str:
    st = w["state"]
    if st in ("stopped", "notes-stopped"):
        cls = w.get("error_class")
        what = "分析好了,備課筆記停住了" if st == "notes-stopped" else "分析停住了"
        label = f"{what}({_REASONS.get(cls, cls)})" if cls else what
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
                   on_status: dict | None = None,
                   on_detail: dict[str, str] | None = None,
                   ok_details: tuple[str, ...] = (),
                   timeout: float | None = None) -> dict:
        try:
            r = await anyio.to_thread.run_sync(lambda: den.request(method, path, json=json, timeout=timeout))
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}") from None
        if r.status_code >= 400:
            if _detail(r) in ok_details:   # 呼叫者要自己分流的拒絕:回 {"detail": …},不當錯誤
                return {"detail": _detail(r)}
            msg = (on_detail or {}).get(_detail(r)) or (on_status or {}).get(r.status_code)
            if callable(msg):
                msg = msg(r)
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

    sessions: dict[str, str] = {}   # 這個 shim 行程(= 一個宿主 session)裡:slug(純聊天 = "")→ 對話 id
    current: list[str] = []         # 最近一次聊的那局(slug 或 "")
    picked: dict[str, str] = {}     # 作者點名、還沒講過話的角色:局 key → 角色 id

    async def _works(**params) -> list[dict]:
        return (await call("GET", "/api/works?" + urlencode({k: v for k, v in params.items() if v is not None})))["works"]

    async def resolve_work(work: str | None) -> dict:
        """作者的說法 → 一篇作品(`GET /works` 的一筆)。slug / 標題關鍵詞 / 剛聊的 / 最近的。"""
        if work is None:
            hits = await _works(q=current[0]) if current else []
            hits = hits or await _works(limit=1)
            if not hits:
                raise _reject("no-work", "還沒有任何作品。請給我稿子的檔案路徑(.md / .txt)。")
            return hits[0]
        hits = await _works(q=work, limit=_CANDIDATES + 1)   # 多拿一筆才知道有沒有超過
        if not hits:
            raise _reject("work-not-found", f"找不到「{work}」這篇。可以用 find_works 看有哪些作品。")
        if len(hits) > 1:
            many = f"超過 {_CANDIDATES}" if len(hits) > _CANDIDATES else f"有 {len(hits)}"
            raise _reject("work-ambiguous", "\n".join(
                [f"{many} 篇符合「{work}」,請問作者是哪一篇:"] + [_work_line(w) for w in hits[:_CANDIDATES]]
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
        out = await call("GET", f"/api/works/{w['slug']}/{part}", on_status={404: f"找不到{name}。"},
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
        s = await call("POST", "/api/stories", {"text": text, "title": sent_title, "slug": slug})
        current[:] = [s["slug"]]   # 交完稿,「這篇」就是它(否則下一句不帶 work 會聊回上一篇)
        job = {"kind": "critique", "slug": s["slug"], "client": client}
        # 稿子沒改:只續跑;這版已分析好就不重跑(重送同一個檔不該再花一次錢)。從沒跑過才開新的
        j = (await call("POST", "/api/jobs", {**job, "resume_only": True}, ok_details=("done", "never"))
             if not s["new_version"] else None)
        if j is not None and j.get("detail") == "never":
            j = None
        if j is None:
            j = await call("POST", "/api/jobs", job)
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
        j = await call("POST", "/api/jobs", {"kind": "critique", "slug": w["slug"], "client": client,
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
        await call("POST", f"/api/works/{w['slug']}/cancel", on_status={409: f"{name}現在沒有在分析。"})
        return f"{name}的分析已停下;之後不帶路徑呼叫 submit_work 可以接著跑。"

    @server.tool(description=DESC_CANCEL_WORK)
    async def cancel_work(work: str | None = None) -> str:
        return await guarded(_cancel_work(work))

    @server.tool(description=DESC_READ, annotations=_READONLY)
    async def read_work(part: str, work: str | None = None) -> str:
        return await guarded(_read(part, work))
    in_flight: set[str] = set()     # 正在跑一輪的篇:首輪還沒局 id、den 的鎖擋不到,由這裡擋(免得付兩次錢)

    def _turn(key: str, body: dict) -> dict:
        """收齊一輪 SSE,回 message 事件的 data;error 事件 → ToolError。"""
        for ev in den.stream("POST", f"/api/discuss/{key}" if key else "/api/discuss", body):
            if ev["event"] == "message":
                return ev["data"]
            if ev["event"] == "error":
                raise ToolError(ev["data"]["message"] + _TALK_FAILED)
        raise ToolError("companion 沒有回應" + _TALK_FAILED)

    async def resolve_key(work: str | None) -> str:
        """作者的說法 → 局 key(slug,純聊天 = "")。指定作品 / 剛聊的那局 / den 最近那局 / 新的純聊天。"""
        if work is not None:
            return (await resolve_work(work))["slug"]
        if current:
            return current[0]
        rows = (await call("GET", "/api/sessions?limit=1"))["sessions"]
        if not rows:
            return ""
        key = rows[0]["slug"] or ""
        sessions[key] = rows[0]["session"]
        return key

    async def _talk(message: str, work: str | None, new_chat: bool, attach_path: str | None, client) -> str:
        if len(message) > MAX_CHAT_CHARS:   # 本地擋:den 的 422 會把整段原文回吐給宿主
            raise _reject("too-long", f"這段話超過 {MAX_CHAT_CHARS} 字,請分段說。")
        try:
            key = "" if new_chat else await resolve_key(work)
        except ToolError as e:
            raise ToolError(str(e) + _TALK_FAILED) from None
        attach = None
        if attach_path is not None:
            if key:
                raise _reject("bound-session", "這局是作品的局,不能把稿丟進對話;要交新版請用 submit_work。" + _TALK_FAILED)
            attach = {"name": Path(attach_path).expanduser().stem, "text": _read_source(attach_path)}
        if key in in_flight:
            raise _reject("busy", "上一輪還在跑,等它回來再說" + _TALK_FAILED)
        in_flight.add(key)
        try:
            if new_chat:
                sessions.pop("", None)
            return await _talk_once(key, message, client, attach)
        finally:
            in_flight.discard(key)

    async def _talk_once(key: str, message: str, client, attach: dict | None = None) -> str:
        if key in picked:
            cs = (await call("GET", "/api/characters"))["characters"]
            if not any(c["id"] == picked[key] and not c["archived"] for c in cs):
                picked.pop(key, None)
        body = {"session_id": sessions.get(key), "message": message, "anchors": [],
                "character": picked.get(key), "home": "mcp", "client": client}
        if attach is not None:
            body["attach"] = attach
        try:
            try:
                data = await anyio.to_thread.run_sync(lambda: _turn(key, body))
            except DenRejected as e:
                if not (e.status == 404 and e.detail == _NO_SESSION and body["session_id"]):
                    raise
                sessions.pop(key, None)      # 局不見了(DB 重建):開新局,拒絕發生在花錢前
                body["session_id"] = None
                data = await anyio.to_thread.run_sync(lambda: _turn(key, body))
        except DenRejected as e:
            if e.status == 404:
                raise ToolError(f"找不到這篇:{key}" + _TALK_FAILED) from None
            if e.status == 409:
                raise ToolError("上一輪還在跑,等它回來再說" + _TALK_FAILED) from None
            if e.status == 422 and attach is not None:
                raise ToolError(f"這份稿丟不進對話:{e.detail}" + _TALK_FAILED) from None
            raise ToolError(f"den 回應 {e.status}" + _TALK_FAILED) from None
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}{_TALK_FAILED}") from None
        sessions[key] = data["session_id"]
        current[:] = [key]
        if picked.get(key) == body["character"]:
            picked.pop(key, None)
        if attach is not None and data.get("attachment"):
            return data["text"] + f"\n\n(附件第 {data['attachment']} 份已給讀伴看。作者想把它開成作品時用 manage_chat。)"
        return data["text"]

    @server.tool(description=DESC_TALK)
    async def talk_to_companion(ctx: Context, message: str = "", work: str | None = None,
                                new_chat: bool = False, attach_path: str | None = None) -> str:
        return await guarded(_talk(message, work, new_chat, attach_path, client_of(ctx)))

    async def _character_now(key: str, default: str) -> str:
        if key in picked:
            return picked[key]
        if key not in sessions:
            return default
        data = await call("GET", f"/api/sessions/{sessions[key]}", ok_details=("沒有這一局",))
        said = [t["character"] for t in data.get("turns", ()) if t["role"] == "assistant"]
        return said[-1] if said else default

    async def _list_characters(work: str | None) -> str:
        data = await call("GET", "/api/characters")
        active = [c for c in data["characters"] if not c["archived"]]
        now = data["default"]
        if work is not None or current:
            now = await _character_now(await resolve_key(work), now)
        if not any(c["id"] == now for c in active):
            now = data["default"]
        return "\n".join(f"{c['id']}:{_shown(c['name']['zh-Hant'], '這個名字沒顯示')},{_shown(c['line']['zh-Hant'], '這句介紹沒顯示')}"
                         + ("(目前)" if c["id"] == now else "") for c in active)

    async def _set_character(character: str, work: str | None) -> str:
        cs = {c["id"]: c for c in (await call("GET", "/api/characters"))["characters"] if not c["archived"]}
        if character not in cs:
            raise _reject("character", f"沒有這隻角色。可選:{'、'.join(cs)}。")
        if work is None and current and not current[0]:
            picked[""] = character
            return f"這局對話下一輪由{_shown(cs[character]['name']['zh-Hant'], '這隻角色')}接著讀。"
        w = await resolve_work(work)
        picked[w["slug"]] = character
        current[:] = [w["slug"]]
        return f"〈{w['title']}〉下一輪由{_shown(cs[character]['name']['zh-Hant'], '這隻角色')}接著讀。"

    async def _manage(action: str, attachment: int | None) -> str:
        sid = sessions.get(current[0]) if current else None
        if sid is None:
            raise _reject("no-chat", "還沒有在聊的局。先用 talk_to_companion 聊一輪。")
        key = current[0]
        base = f"/api/sessions/{sid}"
        if action == "clear":
            await call("POST", f"{base}/clear", on_status={409: "上一輪還在跑,等它回來再清。",
                                                           422: "這局已經是空的,沒有可以清的對話。"})
            return "這局的對話已清空,丟進來的稿和作品原文都還在。"
        if action == "compact":
            r = await call("POST", f"{base}/compact", on_status={
                409: "上一輪還在跑,等它回來再壓縮。", 422: "這局沒有新的對話可以壓縮。",
                502: "壓縮沒有成功,對話沒有改動。請照實告訴作者。"})
            return f"這局之前的對話已壓縮成摘要(花了一次訂閱額度):\n{r['text']}"
        if key:
            raise _reject("bound-session", "這局已經是作品的局,不能再開成作品。")
        if attachment is None:
            left = [a for a in (await call("GET", base))["attachments"] if not a["adopted"]]
            if not left:
                raise _reject("no-attachment", "這局沒有丟進來的稿。")
            if len(left) > 1:
                raise _reject("which-attachment", "\n".join(
                    [f"這局有 {len(left)} 份稿,請問作者要開哪一份(用 attachment 帶編號):"]
                    + [f"{a['n']}. 〈{a['name']}〉" for a in left]))
            attachment = left[0]["n"]
        r = await call("POST", f"{base}/attachments/{attachment}/adopt", on_status={
            404: "這局沒有這份稿。", 409: "這份稿已經開成作品了,或上一輪還在跑。", 422: "這份稿收不成作品。"})
        sessions[r["slug"]] = sid
        sessions.pop("", None)
        if "" in picked:
            picked[r["slug"]] = picked.pop("")
        current[:] = [r["slug"]]
        same = "這份稿和既有作品一樣,沿用那篇。" if r["reused"] else ""
        return (f"已把〈{r['title']}〉開成作品,這局之後就是這篇的對話。{same}"
                "還沒有分析;作者要分析時用 submit_work 交這份檔,或到網頁按「分析這版」。")

    @server.tool(description=DESC_MANAGE_CHAT)
    async def manage_chat(action: Literal["clear", "compact", "adopt"], attachment: int | None = None) -> str:
        return await guarded(_manage(action, attachment))

    @server.tool(description=DESC_LIST_CHARACTERS, annotations=_READONLY)
    async def list_characters(work: str | None = None) -> str:
        return await guarded(_list_characters(work))

    @server.tool(description=DESC_SET_CHARACTER)
    async def set_character(character: str, work: str | None = None) -> str:
        return await guarded(_set_character(character, work))

    drafts: dict = {}               # 最後一批候選:{"items": [...], "lang": ..., "saved": {編號}}
    held: set[tuple] = set()        # 已回過警告的 (編號, 名字):第一次帶 confirm 也要先讓作者看到警告

    async def _create_character(answers: dict, lang: str) -> str:
        drafts.clear()
        held.clear()
        out = await call("POST", "/api/characters/candidates", {"answers": answers, "lang": lang},
                         timeout=_GENERATE_TIMEOUT,
                         on_status={409: "上一批候選還在生成,等它回來再說。",
                                    422: "答案太長(form 80 字、wish 300 字),或 lang 不是 zh-Hant / en。",
                                    502: _generation_failed})
        drafts.update(items=out["candidates"], lang=lang, saved=set())
        lines = [ln for n, c in enumerate(out["candidates"], 1) for ln in _candidate_lines(n, c, lang)]
        return "\n".join(lines + ["把候選照列給作者,由作者選;作者選定後用 save_character。"])

    @server.tool(description=DESC_CREATE_CHARACTER)
    async def create_character(form: str = "", wish: str = "", lang: str = "zh-Hant") -> str:
        return await guarded(_create_character({"form": form, "wish": wish}, lang))

    async def _save_character(number: int, name: str | None, confirm: bool) -> str:
        items = drafts.get("items")
        if not items:
            raise _reject("no-candidates", "這個連線還沒有候選。作者要建角色時先用 create_character。")
        if not 1 <= number <= len(items):
            raise _reject("candidate-number", f"number 只能是 1 到 {len(items)}。")
        if number in drafts["saved"]:
            raise _reject("candidate-saved", "這個候選已經存過了。")
        candidate = items[number - 1]
        lang = drafts["lang"]
        if name and name.strip():
            candidate = {**candidate, "name": {**candidate["name"], lang: name.strip()}}
        key = (number, candidate["name"][lang])
        out = await call("POST", "/api/characters", {"candidate": candidate, "confirm": confirm and key in held},
                         on_status={422: "這個候選存不下來:名字太長或空白。"})
        if not out["created"]:
            held.add(key)
            return (f"還沒存。這個候選{_card_warnings(out['warnings'])}。"
                    "請告訴作者,作者確認要存才帶 confirm=true 再呼叫一次。")
        drafts["saved"].add(number)
        c = out["character"]
        return f"已存成{_shown(c['name'][lang], '新角色')}(id:{c['id']})。作者要它陪讀時用 set_character。"

    @server.tool(description=DESC_SAVE_CHARACTER)
    async def save_character(number: int, name: str | None = None, confirm: bool = False) -> str:
        return await guarded(_save_character(number, name, confirm))

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
