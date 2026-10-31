"""作品視圖:作者用標題/關鍵詞找作品、看分析狀態(純組裝,查詢在 marrow.repo)。

比對刻意只看標題與開頭:單字查詢(「海」)若比全文,幾乎每篇都中(spec §11 第 2 批)。
"""
import render   # 根層函式庫(den 的 cwd 是 repo 根)
from marrow import repo

OPENING_CHARS = 200   # 比對看的開頭長度
_SHOWN = 30           # 清單裡顯示的開頭長度

_ACTIVE = ("queued", "running")
_STOPPED = ("paused", "failed", "cancelled")


def _norm(s: str | None) -> str:
    return "".join((s or "").split()).casefold()


def match(rows: list[dict], query: str | None) -> list[dict]:
    q = _norm(query)
    if not q:
        return list(rows)
    # 分層、取第一層有中的:否則標題「海」永遠被「海-v2」「海邊…」擠成多候選、選不到
    tiers = (lambda r: r["slug"] == q,
             lambda r: _norm(r["title"]) == q,
             lambda r: q in _norm(r["title"]),
             lambda r: q in _norm(r["latest_text"][:OPENING_CHARS]))
    for hit in tiers:
        found = [r for r in rows if hit(r)]
        if found:
            return found
    return []


def state(row: dict, analysis: dict | None, job: dict | None) -> str:
    """ready / notes-running / notes-stopped / running / stopped / stale / none。不是最新版的 job 當作沒有。
    分析在 analyst 成功時就換上,所以「最新版有分析」時 job 可能還在跑 / 停在 reviewer(notes-*)。"""
    latest = row["latest_sv_id"]
    st = job["state"] if job is not None and job["source_version_id"] == latest else None
    active, stopped = st in _ACTIVE, st in _STOPPED
    if analysis is not None and analysis["source_version_id"] == latest:
        return "notes-running" if active else "notes-stopped" if stopped else "ready"
    if active:
        return "running"
    if stopped:
        return "stopped"
    return "stale" if analysis is not None else "none"


def _opening(text: str) -> str:
    flat = "".join(text.split())
    return flat[:_SHOWN] + ("…" if len(flat) > _SHOWN else "")


def rows(conn) -> list[dict]:
    """每篇一列(含最新版全文與 latest_sv_id)。固定 3 次查詢。"""
    cur: dict[int, dict] = {}
    for c in repo.current_artifacts(conn):
        if c["kind"] == "analysis":
            cur[c["story_id"]] = c["artifact"]
    jobs = repo.latest_jobs(conn)
    out = []
    for r in repo.works(conn):
        ana, job = cur.get(r["id"]), jobs.get(r["id"])
        r["title"] = (ana or {}).get("body", {}).get("title") or r["title"] or r["slug"]
        st = state(r, ana, job)
        live = st in ("running", "stopped", "notes-running", "notes-stopped")
        out.append({"slug": r["slug"], "title": r["title"], "latest_text": r["latest_text"],
                    "latest_sv_id": r["latest_sv_id"],
                    "version": r["latest_n"], "chars": len(r["latest_text"]),
                    "opening": _opening(r["latest_text"]), "submitted_at": r["submitted_at"],
                    "talked_at": r["talked_at"], "state": st,
                    "job_id": job["id"] if live else None,
                    "error_class": job["error_class"] if live else None})
    return out


def listing(conn, query: str | None, limit: int = 20) -> list[dict]:
    """依最近活動(聊過或交稿,取晚的)排序。固定 3 次查詢。"""
    hits = match(rows(conn), query)
    hits.sort(key=lambda w: max(w["talked_at"] or 0, w["submitted_at"]), reverse=True)
    for w in hits:
        del w["latest_text"], w["latest_sv_id"]
    return hits[:limit]


PARTS = ("source", "analysis", "notes", "feedback")
_LEGACY = "(舊版客觀回饋:舊的編輯評論流程產生,之後會由備課筆記取代。)"


class Missing(Exception):
    """這篇沒有這個 part。reason:not-analyzed / no-notes / no-feedback。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def read_part(conn, slug: str, part: str) -> str:
    """作者自己要看的資料(markdown)。LookupError 無此篇;Missing 沒有這個 part。"""
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    latest = repo.latest_source_version(conn, st["id"])
    ana = repo.current_artifact(conn, st["id"], "analysis")
    title = (ana or {}).get("body", {}).get("title") or st["title"] or slug
    if part == "source":
        return f"〈{title}〉第 {latest['n']} 版原文:\n\n{latest['text']}"
    if part == "analysis":
        if ana is None:
            raise Missing("not-analyzed")
        art, what, body = ana, "分析", render.render_analysis(ana["body"], front_matter=False)
        head = []
    elif part == "notes":
        art = repo.current_artifact(conn, st["id"], "notes")
        if art is None:
            raise Missing("no-notes")
        what, body = "筆記", render.render_notes(art["body"], title, front_matter=False)
        head = []
    else:
        fb = repo.current_artifact(conn, st["id"], "feedback")
        if fb is None:
            raise Missing("no-feedback")
        art, what, body = fb, "回饋", render.render_feedback(fb["body"], title, front_matter=False)
        head = [_LEGACY]
    if art["source_version_id"] != latest["id"]:
        n = repo.source_version(conn, art["source_version_id"])["n"]
        tail = {"analysis": ",新版還沒有分析結果", "notes": ",新版還沒有筆記"}.get(part, "")
        head.append(f"(這是第 {n} 版的{what};最新是第 {latest['n']} 版{tail}。)")
    return "\n".join(head + ([""] if head else []) + [body])
