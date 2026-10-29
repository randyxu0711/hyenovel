"""stdio MCP 轉接器:五個 tool,薄薄一層翻成 den REST。入口 `python -m den.mcp`。

- stdout 只屬於 MCP 協定:本模組不 print,logging 只准 stderr(main 明確設)。
- den.request 是阻塞的(拉起 den 可能等十幾秒)→ 一律丟 anyio.to_thread。
- REST 4xx/5xx 與 DenUnavailable 一律轉成 ToolError(給人看的中文)。
- 每個回覆(含錯誤)文末附上 den 的提示(取走即清空,只附一次)。
- clientInfo 是提示不是授權:只帶給 den 挑 runner、記錄。
"""
import logging
import sys
from functools import cache
from pathlib import Path

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from den.client import DenClient, DenUnavailable
from den.config import MAX_SOURCE_BYTES, valid_slug
from marrow import db
from marrow.ingest import decode

log = logging.getLogger("hyenovel")

_PROMPT = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "discuss.md"
_SUFFIXES = (".md", ".txt")
_CLIENT_MAX = 64   # den 的 ClientIn 上限;超過整個 POST /jobs 會 422

_STATES = {"queued": "排隊中", "done": "完成", "paused": "已暫停",
           "failed": "失敗", "cancelled": "已取消"}
_STEPS = {"analyst": "分析中", "criticizer": "評論中"}
_REASONS = {"usage-limit": "訂閱額度用完", "gate": "引文閘門重試耗盡",
            "overload": "服務過載", "auth": "Claude CLI 未登入或登入失效",
            "crash": "工人失敗", "timeout": "工人失敗(逾時)"}
_RESUMABLE = ("paused", "failed", "cancelled")

DESC_START = (
    "把一篇純文學短篇送去分析+編輯評論。只收本機 .md / .txt 檔案路徑(不收全文、不收 pdf/docx——"
    "請使用者先轉成純文字檢查過)。這是分鐘級的非同步背景工作:立刻回 slug 與 job id,"
    "之後用 critique_status 查進度。改稿重跑請帶上次回的 slug;同一份原文不帶 slug 重送會沿用那篇。"
    "會用使用者同一份 Claude 訂閱額度。")
DESC_STATUS = ("查詢 start_critique 回的 job 進度(排隊/分析/評論/完成/暫停/失敗/取消)與停住的原因。"
               "不帶 job_id 會列出最近的 job,新對話找不到編號時用。")
DESC_CANCEL = "取消一個排隊中或執行中的評論 job。取消後可用 resume_critique 續跑。"
DESC_RESUME = "續跑一個已暫停(例:額度用完)、失敗或已取消的評論 job;已完成的步驟不重跑。"
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


@cache
def _persona() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def _refs(refs) -> str:
    return ", ".join(refs or ())


def render_discussion(ctx: dict) -> str:
    """討論素材:不送 raw JSON,也不送 evidence / quotes 引文(原文已在裡面,引文是它的子字串)。"""
    out = [_persona().rstrip(), "", "---", f"# 《{ctx['title'] or ctx['slug']}》(slug: {ctx['slug']})"]
    if ctx["stale"]:
        out.append("注意:原文已改稿、分析是舊版的——以下原文是當時分析的那一版;"
                   "討論時要明說,新稿得重跑 start_critique。")
    out += ["", "## 原文", "<source>", ctx["source"].rstrip(), "</source>", "", "## 分析(精簡)"]
    a = ctx["analysis"]
    if a.get("synopsis"):
        out.append(f"梗概:{a['synopsis']}")
    out.append("### 節點")
    for n in a.get("nodes") or ():
        note = f":{n['note']}" if n.get("note") else ""
        out.append(f"[{n['id']}] {n['type']} {n['label']}{note}")
    out.append("### 關係")
    out += [f"{e['from']} -{e['type']}-> {e['to']}" for e in a.get("edges") or ()]
    fb = ctx["feedback"]
    out += ["", "## 編輯回饋"]
    if fb is None:
        out.append("(還沒有)")
    else:
        out.append(f"讀法:{fb.get('read', '')}")
        for key, head in (("strengths", "有效之處"), ("key_points", "關鍵")):
            out.append(f"### {head}")
            for p in fb.get(key) or ():
                refs = f" / refs: {_refs(p['refs'])}" if p.get("refs") else ""
                out.append(f"- {p['title']} / {p['body']}{refs}")
                if p.get("question"):     # schema:提問是討論的開場
                    out.append(f"  提問:{p['question']}")
                if p.get("experiment"):
                    out.append(f"  實驗:{p['experiment']}")
        if fb.get("minor"):
            out.append("### 枝節")
            out += [f"- {m}" for m in fb["minor"]]
        out.append(f"如果只改一件事:{fb.get('one_line', '')}")
    out += ["", "## 已留下的結論"]
    if not ctx["conclusions"]:
        out.append("(還沒有)")
    for c in ctx["conclusions"]:
        refs = f" [{_refs(c['refs'])}]" if c.get("refs") else ""
        out.append(f"({c['kind']}) {c['text']}{refs}")
    return "\n".join(out) + "\n"


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
            out.append(f"job {j['id']} ·〈{j['title'] or j['slug']}〉({j['slug']}) · {_label(j)}{why}")
        if head == "可續跑":
            out.append("用 resume_critique(job_id=N) 續跑(N 換成上面的編號);已完成的步驟不重跑。")
        out.append("")
    return "\n".join(out).rstrip()


def build_server(den: DenClient) -> MCPServer:
    server = MCPServer("hyenovel")

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
            lines += [f"這篇這一版之前跑到一半(job {j['job_id']}),已接續:已完成的步驟不重跑。",
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
        return await guarded(_act(job_id, "resume", "這個 job 目前不能續跑(只有暫停/失敗/取消的可以)。",
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

    return server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    build_server(DenClient(db.data_dir())).run("stdio")


if __name__ == "__main__":
    main()
