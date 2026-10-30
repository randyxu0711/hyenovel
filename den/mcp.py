"""stdio MCP 轉接器:六個 tool,薄薄一層翻成 den REST。入口 `python -m den.mcp`。

- stdout 只屬於 MCP 協定:本模組不 print,logging 只准 stderr(main 明確設)。
- den.request 是阻塞的(拉起 den 可能等十幾秒)→ 一律丟 anyio.to_thread。
- REST 4xx/5xx 與 DenUnavailable 一律轉成 ToolError(給人看的中文)。
- 每個回覆(含錯誤)文末附上 den 的提示(取走即清空,只附一次)。
- clientInfo 是提示不是授權:只帶給 den 挑 runner、記錄。
"""
import logging
import sys
from pathlib import Path

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from den.client import DenClient, DenRejected, DenUnavailable
from den.companion import MODES
from den.config import MAX_SOURCE_BYTES, valid_slug
from den.discuss import render_discussion
from marrow import db
from marrow.ingest import decode

log = logging.getLogger("hyenovel")

_SUFFIXES = (".md", ".txt")
_CLIENT_MAX = 64   # den 的 ClientIn 上限;超過整個 POST /jobs 會 422

_STATES = {"queued": "排隊中", "done": "完成", "paused": "已暫停",
           "failed": "失敗", "cancelled": "已取消"}
_STEPS = {"analyst": "分析中", "criticizer": "評論中"}
_REASONS = {"usage-limit": "訂閱額度用完", "gate": "引文閘門重試耗盡",
            "overload": "服務過載", "auth": "Claude CLI 未登入或登入失效",
            "crash": "工人失敗", "timeout": "工人失敗(逾時)"}
_RESUMABLE = ("paused", "failed", "cancelled")
_STALE = "舊版原文,不能續跑——改稿後請用 start_critique 跑新版"

DESC_START = (
    "把一篇純文學短篇送去分析+編輯評論。只收本機 .md / .txt 檔案路徑(不收全文、不收 pdf/docx——"
    "請使用者先轉成純文字檢查過)。這是分鐘級的非同步背景工作:立刻回 slug 與 job id,"
    "之後用 critique_status 查進度。改稿重跑請帶上次回的 slug;同一份原文不帶 slug 重送會沿用那篇。"
    "會用使用者同一份 Claude 訂閱額度。")
DESC_STATUS = ("查詢 start_critique 回的 job 進度(排隊/分析/評論/完成/暫停/失敗/取消)與停住的原因。"
               "不帶 job_id 會列出最近的 job,新對話找不到編號時用。")
DESC_CANCEL = "取消一個排隊中或執行中的評論 job。取消後可用 resume_critique 續跑。"
DESC_RESUME = "續跑一個已暫停(例:額度用完)、失敗或已取消的評論 job;已完成的步驟不重跑。"
# ≤4,096 字元(Claude Code 會靜默截斷);最重要的放第一句
INSTRUCTIONS = (
    "talk_to_companion 回傳的是陪讀角色 companion 對作者說的話:請一字不改地轉給作者,"
    "不要改寫、摘要、補充或加上你自己的評論。作者想聊自己寫的作品、想聽讀者感受時用 talk_to_companion。"
    "送新稿分析用 start_critique、查進度用 critique_status。")
DESC_TALK = (
    "和陪讀的 companion 說話,回傳它的回覆——請原文轉給作者,不要改寫、摘要或補充。"
    "作者對 companion 說的任何話(包括「好了沒」)都用這個。message 留空 = 讓 companion 先開口。"
    "work = 作品 slug(省略則沿用這段對話剛聊的那篇)。"
    "mode = direct(直說)/ slow(慢讀,預設)/ imaginative(想像);"
    "作者說「講重點就好」時用 direct,「慢慢講」用 slow,「陪我想像」用 imaginative,沒提就不要給。")
_TALK_FAILED = "。請照實告訴作者這一輪沒有成功,不要自己代答。"
_NO_SESSION = "這篇沒有這一局"   # den /discuss 的 404 detail(局不見了;拒絕在花錢前)
DESC_OPEN = (
    "取得一篇已分析完成的故事的討論素材:編輯人格指示、原文全文、精簡版分析與回饋、已留下的結論。"
    "拿到後由你自己扮演出版編輯與使用者來回討論,全程唯讀:不寫任何檔案、不改分析。")


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


def _label(j: dict) -> str:
    st = j["state"]
    return _STEPS.get(j.get("step"), "分析中") if st == "running" else _STATES.get(st, st)


def _status_text(j: dict) -> str:
    st = j["state"]
    lines = [f"job {j['id']}:{_label(j)}"]
    if j.get("error_class"):
        lines.append(f"原因:{_REASONS.get(j['error_class'], j['error_class'])}")
    if st in _RESUMABLE:
        lines.append(f"可用 resume_critique(job_id={j['id']}) 續跑;已完成的步驟不重跑。")
    elif st == "done":
        lines.append(f"可用 open_discussion(slug=\"{j['slug']}\") 開始討論這篇。")
    elif st in ("queued", "running"):
        lines.append("還在跑,晚點再問我進度。")
    return "\n".join(lines)


def _list_text(jobs: list[dict]) -> str:
    """三組:進行中 / 可續跑(附原因)/ 最近完成;空的組不出。"""
    if not jobs:
        return "目前沒有任何分析紀錄。"
    groups = (("進行中", ("queued", "running")), ("可續跑", _RESUMABLE), ("最近完成", ("done",)))
    out = []
    for head, states in groups:
        rows = [j for j in jobs if j["state"] in states]
        if not rows:
            continue
        out.append(f"## {head}")
        for j in rows:
            why = (f"({_REASONS.get(j['error_class'], j['error_class'])})"
                   if j.get("error_class") else "")
            stale = head == "可續跑" and not j.get("is_latest_version", True)
            out.append(f"job {j['id']} ·〈{j['title'] or j['slug']}〉({j['slug']}) · {_label(j)}{why}"
                       + (f" · {_STALE}" if stale else ""))
        if head == "可續跑" and any(j.get("is_latest_version", True) for j in rows):
            out.append("用 resume_critique(job_id=N) 續跑(N 換成上面的編號);已完成的步驟不重跑。")
        out.append("")
    return "\n".join(out).rstrip()


def build_server(den: DenClient) -> MCPServer:
    server = MCPServer("hyenovel", instructions=INSTRUCTIONS)

    async def call(method: str, path: str, json: dict | None = None, *,
                   on_status: dict[int, str] | None = None) -> dict:
        try:
            r = await anyio.to_thread.run_sync(lambda: den.request(method, path, json=json))
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}") from None
        if r.status_code >= 400:
            msg = (on_status or {}).get(r.status_code)
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

    async def _start(path, title, slug, client) -> str:
        text = _read_source(path)
        s = await call("POST", "/stories", {"text": text, "title": title, "slug": slug})
        j = await call("POST", "/jobs", {"kind": "critique", "slug": s["slug"], "client": client})
        lines = []
        if s["reused"]:
            lines.append(f"這份原文和 {s['slug']} 的最新版相同,沿用那篇。")
        if j.get("resumed"):
            cls = j.get("previous_error_class")
            if cls:
                why = f"上次停在:{_REASONS.get(cls, cls)}"
            elif j.get("previous_state") == "cancelled":
                why = "上次是你取消的。"
            else:
                why = "上次沒有跑完。"
            lines += [f"這篇這一版之前跑到一半(job {j['job_id']}),已接續:已完成的步驟不重跑。", why,
                      f"好了問我進度(critique_status job_id={j['job_id']})。"]
            return "\n".join(lines)
        if j["existing"]:
            lines += [f"{s['slug']} 這一版已在分析中:job {j['job_id']}(沒有開新的 job,不會再花額度)。",
                      f"好了問我進度(critique_status job_id={j['job_id']})。"]
            return "\n".join(lines)
        lines += [f"已送出:slug {s['slug']}(第 {s['version']} 版)、job {j['job_id']}(runner:{j['runner']})。",
                  f"{_minutes(j['estimate'])}。{j['note']}。",
                  f"這是背景工作,好了問我進度(critique_status job_id={j['job_id']})。",
                  f"改稿重跑請帶這個 slug:start_critique(path, slug=\"{s['slug']}\")。"]
        return "\n".join(lines)

    @server.tool(description=DESC_START)
    async def start_critique(path: str, ctx: Context, title: str | None = None,
                             slug: str | None = None) -> str:
        return await guarded(_start(path, title, slug, client_of(ctx)))

    async def _status(job_id: int | None) -> str:
        if job_id is None:
            return _list_text((await call("GET", "/jobs"))["jobs"])
        return _status_text(await call("GET", f"/jobs/{job_id}",
                                       on_status={404: f"找不到 job {job_id}。"}))

    @server.tool(description=DESC_STATUS)
    async def critique_status(job_id: int | None = None) -> str:
        return await guarded(_status(job_id))

    async def _act(job_id: int, verb: str, conflict: str, done: str) -> str:
        await call("POST", f"/jobs/{job_id}/{verb}",
                   on_status={404: f"找不到 job {job_id}。", 409: conflict})
        return done

    @server.tool(description=DESC_CANCEL)
    async def cancel_critique(job_id: int) -> str:
        return await guarded(_act(job_id, "cancel", "這個 job 目前不能取消(可能已結束)。",
                                  f"job {job_id} 已取消;要再跑用 resume_critique。"))

    @server.tool(description=DESC_RESUME)
    async def resume_critique(job_id: int) -> str:
        return await guarded(_act(job_id, "resume", ("這個 job 目前不能續跑。可能是:已結束(只有暫停/失敗/取消的可以續);"
                                  "舊版原文(改稿後請用 start_critique 跑新版);"
                                  "同一版已有別的 job 在跑,或之後已有一次跑完。"),
                                  f"job {job_id} 已重新排入;用 critique_status 查進度。"))

    async def _open(slug: str) -> str:
        if not valid_slug(slug):   # 會拼進 URL 路徑:本地先擋
            raise _reject("slug", f"slug 格式不對:{slug[:64]!r}(只能英數、底線、連字號,例:d01)。")
        return render_discussion(await call(
            "GET", f"/stories/{slug}/discussion",
            on_status={404: f"找不到這篇:{slug}。",
                       409: "這篇還沒分析完成,先 start_critique(或等它跑完)。"}))

    @server.tool(description=DESC_OPEN)
    async def open_discussion(slug: str) -> str:
        return await guarded(_open(slug))

    sessions: dict[str, str] = {}   # 這個 shim 行程(= 一個宿主 session)裡:slug → 對話 id
    current: list[str] = []         # 最近一次聊的那篇

    def _turn(slug: str, body: dict) -> dict:
        """收齊一輪 SSE,回 message 事件的 data;error 事件 → ToolError。"""
        for ev in den.stream("POST", f"/discuss/{slug}", body):
            if ev["event"] == "message":
                return ev["data"]
            if ev["event"] == "error":
                raise ToolError(ev["data"]["message"] + _TALK_FAILED)
        raise ToolError("companion 沒有回應" + _TALK_FAILED)

    async def _talk(message: str, work: str | None, mode: str | None, client) -> str:
        slug = work or (current[0] if current else None)
        if slug is None:
            raise _reject("no-work", "還不知道要聊哪一篇:請給我它的 slug(例:d01)。")
        if not valid_slug(slug):
            raise _reject("slug", f"slug 格式不對:{slug[:64]!r}(只能英數、底線、連字號,例:d01)。")
        if mode is not None and mode not in MODES:
            raise _reject("mode", "模式只有 direct(直說)/ slow(慢讀)/ imaginative(想像)。")
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
                raise ToolError(f"找不到這篇:{slug}。") from None
            if e.status == 409:
                raise ToolError("上一輪還在跑,等它回來再說。") from None
            raise ToolError(f"den 回應 {e.status}:{e.detail}") from None
        except DenUnavailable as e:
            raise ToolError(f"連不上 hyenovel den:{e}{_TALK_FAILED}") from None
        sessions[slug] = data["session_id"]
        current[:] = [slug]
        return data["text"]

    @server.tool(description=DESC_TALK)
    async def talk_to_companion(ctx: Context, message: str = "", work: str | None = None,
                                mode: str | None = None) -> str:
        return await guarded(_talk(message, work, mode, client_of(ctx)))

    return server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    build_server(DenClient(db.data_dir())).run("stdio")


if __name__ == "__main__":
    main()
