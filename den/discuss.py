"""討論素材:從 den 的 discuss 端點拿到的 ctx 渲染成給模型讀的純文字,以及多輪歷史的組裝。

render_discussion 給 MCP open_discussion 用(原樣搬自 den/mcp.py);render_turn / run_turn 給 web 討論。
"""
import logging
import time
import uuid
from contextlib import aclosing
from functools import cache
from pathlib import Path

from den import stories
from marrow import repo

log = logging.getLogger("hyenovel")

_STALE_CONCLUSION = "(舊版分析時留下的,可能已不適用)"
_PROMPT = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "discuss.md"


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
        mark = f"{_STALE_CONCLUSION} " if c.get("stale") else ""
        out.append(f"{mark}({c['kind']}) {c['text']}{refs}")
    return "\n".join(out) + "\n"


_ROLE = {"user": "作者", "assistant": "編輯"}


def render_turn(history: list[dict], message: str) -> str:
    """一輪的輸入:歷史包進 <history>、新訊息放最後;無歷史只回訊息本身。"""
    if not history:
        return message
    lines = [f"{_ROLE[h['role']]}:{h['text']}" for h in history]
    return "\n".join(["以下是這一局到目前為止的對話(作者 = 使用者):",
                      "<history>", *lines, "</history>", "", "作者這一輪說:", message])


class UnknownSession(Exception):
    """session_id 不是這篇的局。"""


_RECOVERABLE = ("usage-limit", "transient", "timeout")


def prepare_turn(conn, slug: str, session_id: str | None) -> dict:
    """串流開始前的判斷(狀態碼只能在這時定):LookupError 無此篇 / ValueError 未分析 /
    UnknownSession。新局只發 id,discussion 列等整輪成功才建。"""
    ctx = stories.discussion_context(conn, slug)
    st = repo.story_by_slug(conn, slug)
    d = None
    if session_id is not None:
        row = repo.discussion_by_external(conn, st["id"], session_id)
        if row is None:
            raise UnknownSession(session_id)
        d = row["id"]
    return {"slug": slug, "ctx": ctx, "story_id": st["id"], "discussion_id": d,
            "session_id": session_id or uuid.uuid4().hex[:12],
            "analysis_fp": repo.current_artifact(conn, st["id"], "analysis")["sha256"]}


async def run_turn(conn, chat, turn: dict, message: str, anchors: list[str], now=time.time):
    """一輪:重組歷史 → 轉發 delta 為 token → 整輪成功才在同一個 transaction 落 user+assistant。

    失敗 / 斷線 = 這輪沒發生過。被 aclose 時一併關掉 chat(工人隨之被殺)。
    歷史在這裡(呼叫者已持該局的鎖)才讀,不在 prepare_turn 讀,免得拿到過期的。
    """
    d = turn["discussion_id"]
    history = repo.utterances(conn, d) if d is not None else []
    seq = history[-1]["seq"] + 1 if history else 0
    user_ts = now()
    result = None
    try:
        async with aclosing(chat(render_discussion(turn["ctx"]),
                                 render_turn(history, message))) as stream:
            async for kind, val in stream:
                if kind == "delta":
                    yield {"event": "token", "data": {"text": val}}
                else:
                    result = val
    finally:
        log.info("event=discuss-turn slug=%s outcome=%s ms=%s", turn["slug"],
                 result.outcome if result else "aborted", result.duration_ms if result else "-")
    sid = turn["session_id"]
    if result.outcome != "ok":
        yield {"event": "error", "data": {"where": "discuss", "message": result.message,
                                          "recoverable": result.outcome in _RECOVERABLE}}
        return
    end = now()
    usage = {**(result.tokens or {}), "duration_ms": result.duration_ms, "model": result.model}
    fp = turn["analysis_fp"]
    with conn:   # 不可在這裡 await:同一條連線 job worker 也在寫
        if d is None:
            d = repo.ensure_discussion(conn, turn["story_id"], sid, "web", "web", user_ts)
        repo.add_utterance(conn, d, seq, "user", message, user_ts, "den", anchors, fp)
        repo.add_utterance(conn, d, seq + 1, "assistant", result.text, end, "den", anchors, fp,
                           usage=usage)
        repo.close_discussion(conn, d, end)   # ended_at = 最後活動時間
    yield {"event": "message", "data": {"role": "assistant", "text": result.text,
                                        "session_id": sid}}
    yield {"event": "done", "data": {"ok": True, "session_id": sid}}
