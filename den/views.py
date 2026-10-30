"""讀取視圖:DB → 領域形狀(純組裝,無 SQL;查詢全在 marrow.repo)。

den 的 API 回領域形狀(story / artifact / job),不回某個前端專用的形狀——翻成畫面要的樣子
是 client 自己的事。
"""
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
