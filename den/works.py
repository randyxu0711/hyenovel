"""作品視圖:作者用標題/關鍵詞找作品、看分析狀態(純組裝,查詢在 marrow.repo)。

比對刻意只看標題與開頭:單字查詢(「海」)若比全文,幾乎每篇都中(spec §11 第 2 批)。
"""
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
    exact = [r for r in rows if r["slug"] == q]
    if exact:
        return exact
    return [r for r in rows
            if q in _norm(r["title"]) or q in _norm(r["latest_text"][:OPENING_CHARS])]


def state(row: dict, analysis: dict | None, job: dict | None) -> str:
    """ready / running / stopped / stale / none。不是最新版的 job 當作沒有。"""
    latest = row["latest_sv_id"]
    if analysis is not None and analysis["source_version_id"] == latest:
        return "ready"
    if job is not None and job["source_version_id"] == latest:
        if job["state"] in _ACTIVE:
            return "running"
        if job["state"] in _STOPPED:
            return "stopped"
    return "stale" if analysis is not None else "none"


def _opening(text: str) -> str:
    flat = "".join(text.split())
    return flat[:_SHOWN] + ("…" if len(flat) > _SHOWN else "")


def listing(conn, query: str | None, limit: int = 20) -> list[dict]:
    """依最近活動(聊過或交稿,取晚的)排序。固定 3 次查詢。"""
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
        live = st in ("running", "stopped")
        out.append({"slug": r["slug"], "title": r["title"], "latest_text": r["latest_text"],
                    "opening": _opening(r["latest_text"]), "submitted_at": r["submitted_at"],
                    "talked_at": r["talked_at"], "state": st,
                    "job_id": job["id"] if live else None,
                    "error_class": job["error_class"] if live else None})
    hits = match(out, query)
    hits.sort(key=lambda w: max(w["talked_at"] or 0, w["submitted_at"]), reverse=True)
    for w in hits:
        del w["latest_text"]
    return hits[:limit]
