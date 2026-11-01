"""讀取視圖:DB → 領域形狀(純組裝,無 SQL;查詢全在 marrow.repo)。

den 的 API 回領域形狀(story / artifact / job),不回某個前端專用的形狀——翻成畫面要的樣子
是 client 自己的事。
"""
from den import works
from marrow import repo


def _current(art: dict | None) -> dict | None:
    return None if art is None else {"id": art["id"], "created_at": art["created_at"]}


def stories(conn) -> list[dict]:
    """列表。固定 3 次查詢(story / current artifact / latest job 各一次),不隨篇數成長。
    無 current analysis 且無 job 的篇不列。"""
    cur: dict[int, dict] = {}
    for c in repo.current_artifacts(conn):
        cur.setdefault(c["story_id"], {})[c["kind"]] = c["artifact"]
    jobs = repo.latest_jobs(conn)
    out = []
    for st in repo.stories(conn):
        arts = cur.get(st["id"], {})
        ana, job = arts.get("analysis"), jobs.get(st["id"])
        if ana is None and job is None:
            continue
        body = ana["body"] if ana else {}
        out.append({
            "slug": st["slug"],
            "title": body.get("title") or st["title"] or st["slug"],
            "synopsis": body.get("synopsis") or "",
            "nodes": len(body.get("nodes", [])),
            "edges": len(body.get("edges", [])),
            "current": {"analysis": _current(ana), "feedback": _current(arts.get("feedback")),
                        "notes": _current(arts.get("notes"))},
            "latest_job": None if job is None else {
                "id": job["id"], "state": job["state"], "step": job["step"],
                "error_class": job["error_class"], "updated_at": job["updated_at"]},
        })
    return out


def _story(conn, slug: str) -> dict:
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    return st


def conclusion_is_stale(c: dict, current_analysis_id: int | None) -> bool:
    """已作廢,或當時對照的 analysis artifact 未知(NULL)/不是現在的 current。views 與討論素材共用。"""
    return (c["invalidated_at"] is not None or c["analysis_artifact_id"] is None
            or c["analysis_artifact_id"] != current_analysis_id)


def conclusions(conn, slug: str) -> list[dict]:
    """`Conclusion` 形狀。stale = 已作廢,或當時對照的 analysis artifact 未知(NULL)/不是現在的 current。"""
    st = _story(conn, slug)
    ana = repo.current_artifact(conn, st["id"], "analysis")
    cur_id = ana["id"] if ana else None
    return [{
        "id": c["external_id"], "kind": c["kind"], "text": c["text"],
        "refs": c["refs"], "quotes": c["quotes"],
        "stale": conclusion_is_stale(c, cur_id),
    } for c in repo.conclusions(conn, st["id"])]


def transcript(conn, slug: str) -> list[dict]:
    """`Turn` 形狀,依 ts 排;`session` 是討論局的 external_id。"""
    st = _story(conn, slug)
    return [{"ts": u["ts"], "session": u["external_id"], "role": u["role"], "text": u["text"],
             "anchors": u["anchors"]} for u in repo.discussions_with_utterances(conn, st["id"])]


class AmbiguousSession(Exception):
    """同一個 session id 在不只一篇都有局。"""


def _title(conn, story_id: int, slug: str) -> str:
    """與作品清單同口徑:分析標題 > 故事標題 > slug。"""
    ana = repo.current_artifact(conn, story_id, "analysis")
    return (ana or {}).get("body", {}).get("title") or repo.story(conn, story_id)["title"] or slug


class UnknownVersion(Exception):
    """指定的原文版本不存在。"""


def work_detail(conn, slug: str, v: int | None = None) -> dict:
    row = next((w for w in works.rows(conn) if w["slug"] == slug), None)
    if row is None:
        raise LookupError(slug)
    st = repo.story_by_slug(conn, slug)
    notes = repo.current_artifact(conn, st["id"], "notes")
    shown = row if v is None else repo.source_version_by_n(conn, st["id"], v)
    if shown is None:
        raise UnknownVersion(v)
    return {"slug": slug, "title": row["title"], "version": shown["version"] if v is None else shown["n"],
            "text": shown["latest_text"] if v is None else shown["text"],
            "versions": [x["n"] for x in repo.source_versions(conn, st["id"])],
            "state": row["state"], "job_id": row["job_id"],
            "notes_ready": notes is not None and notes["source_version_id"] == row["latest_sv_id"]}


def sessions(conn, slug: str) -> list[dict]:
    """這篇的局,新到舊。version = 最後一則 assistant 發言讀的分析對應的原文版本(analysis_fp 精確對,沒有 → None)。"""
    st = _story(conn, slug)
    versions = repo.analysis_versions(conn, st["id"])
    by: dict[str, list[dict]] = {}
    for u in repo.discussions_with_utterances(conn, st["id"]):
        by.setdefault(u["external_id"], []).append(u)
    out = []
    for sid, us in by.items():
        asst = [u for u in us if u["role"] == "assistant"]
        last = us[-1]
        out.append({"session": sid, "started_at": us[0]["ts"], "last_at": last["ts"],
                    "turns": len(asst), "character": asst[-1]["character"] if asst else None,
                    "mode": asst[-1]["mode"] if asst else None,
                    "preview": asst[-1]["text"][:60] if asst else "",
                    "version": versions.get(asst[-1]["analysis_fp"]) if asst else None})
    out.sort(key=lambda s: s["last_at"], reverse=True)
    return out


def session_turns(conn, session: str) -> dict:
    found = repo.discussions_by_external(conn, session)
    if not found:
        raise LookupError(session)
    if len(found) > 1:
        raise AmbiguousSession(session)
    d = found[0]
    return {"session": session, "slug": d["slug"], "title": _title(conn, d["story_id"], d["slug"]),
            "turns": [{"role": u["role"], "text": u["text"], "ts": u["ts"], "mode": u["mode"],
                       "character": u["character"], "quotes": u["quotes"] or []}
                      for u in repo.utterances(conn, d["id"])]}


def recent_sessions(conn, limit: int) -> list[dict]:
    out = repo.recent_discussions(conn, limit)
    titles = {c["story_id"]: c["artifact"]["body"].get("title")
              for c in repo.current_artifacts(conn) if c["kind"] == "analysis"}
    ids = {st["slug"]: st["id"] for st in repo.stories(conn)}
    for d in out:
        d["title"] = titles.get(ids[d["slug"]]) or d["title"] or d["slug"]
        d["session"] = d.pop("external_id")   # 與 session_rows 同名,前端只認 session
    return out
