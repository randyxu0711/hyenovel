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
        # 明確 slug 只可能是 den 先前回的那個;替任意 slug 建新篇會重開 sNN 命名空間撞號
        if repo.story_by_slug(conn, slug) is None:
            raise ValueError("unknown slug")
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


def companion_context(conn, slug: str) -> dict:
    """companion 素材:最新版原文、只在對應最新版時才給的分析、最新版的進度。

    刻意不帶 feedback / 結論(spec §7.4:判斷層的產物進 companion 會被當成自己的閱讀照念)。
    分析對應舊版時不給:引文會對不上新稿。
    """
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    latest = repo.latest_source_version(conn, st["id"])
    analysis = repo.current_artifact(conn, st["id"], "analysis")
    job = repo.latest_job(conn, st["id"], latest["id"])
    return {
        "slug": slug, "title": st["title"], "source": latest["text"],
        "analysis": analysis["body"] if analysis and analysis["source_version_id"] == latest["id"] else None,
        "progress": job["state"] if job else "none",
    }
