"""收原文與討論素材(純 DB 邏輯,路由在 app.py)。呼叫 ingest 的人包 `with conn:`。"""
from den import config
from marrow import ingest as marrow_ingest
from marrow import repo


def ingest(conn, text: str, title: str | None, slug: str | None, now: float) -> dict:
    text = marrow_ingest.normalize(text)
    if not text.strip():
        raise ValueError("空白故事")
    if len(text.encode("utf-8")) > config.MAX_SOURCE_BYTES:
        raise ValueError("原文過長")
    if slug is not None:
        if not config.valid_slug(slug):
            raise ValueError("bad slug")
        sid = repo.ensure_story(conn, slug, title, now)
        _, new = repo.add_source_version(conn, sid, text, now)
        reused = False
    else:
        hit = repo.story_by_latest_sha(conn, repo.sha256_text(text))
        if hit is not None:
            slug, sid, new, reused = hit["slug"], hit["id"], False, True
        else:
            slug = repo.next_den_slug(conn)
            sid = repo.ensure_story(conn, slug, title, now)
            _, new = repo.add_source_version(conn, sid, text, now)
            reused = False
    st = repo.story(conn, sid)
    return {"slug": slug, "title": st["title"],
            "version": repo.latest_source_version(conn, sid)["n"],
            "new_version": new, "reused": reused}


def discussion_context(conn, slug: str) -> dict:
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    analysis = repo.current_artifact(conn, st["id"], "analysis")
    if analysis is None:
        raise ValueError("not-analyzed")
    feedback = repo.current_artifact(conn, st["id"], "feedback")
    latest = repo.latest_source_version(conn, st["id"])
    return {
        "slug": slug, "title": st["title"],
        "source": repo.source_version(conn, analysis["source_version_id"])["text"],
        "stale": latest["id"] != analysis["source_version_id"],
        "analysis": analysis["body"],
        "feedback": feedback["body"] if feedback else None,
        "conclusions": [{k: c[k] for k in ("kind", "text", "refs", "quotes")}
                        for c in repo.conclusions(conn, st["id"]) if c["invalidated_at"] is None],
    }
