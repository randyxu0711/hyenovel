"""收原文與討論素材(純 DB 邏輯,路由在 app.py)。呼叫 ingest 的人包 `with conn:`。"""
from den import config, memory
from marrow import ingest as marrow_ingest
from marrow import compare, repo


class BoundSession(Exception):
    pass


class UnknownAttachment(Exception):
    pass


class AlreadyAdopted(Exception):
    pass


class UnknownVersion(Exception):
    pass


def adopt(conn, discussion: dict, n: int, now: float) -> dict:
    att = next((a for a in repo.attachments(conn, discussion["id"]) if a["n"] == n), None)
    if att is None:
        raise UnknownAttachment(n)
    if att["source_version_id"] is not None:
        raise AlreadyAdopted(n)
    if discussion["story_id"] is not None:
        raise BoundSession(discussion["external_id"])
    out = ingest(conn, att["text"], att["name"], None, now)
    st = repo.story_by_slug(conn, out["slug"])
    repo.bind_discussion(conn, discussion["id"], st["id"])
    repo.adopt_attachment(conn, discussion["id"], n, repo.latest_source_version(conn, st["id"])["id"])
    return {"slug": out["slug"], "title": out["title"], "version": out["version"], "reused": out["reused"]}


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
    repo.unarchive_story(conn, sid)
    st = repo.story(conn, sid)
    return {"slug": slug, "title": st["title"],
            "version": repo.latest_source_version(conn, sid)["n"],
            "new_version": new, "reused": reused}


def companion_context(conn, slug: str | None, discussion_id: int | None = None, cmp: int | None = None) -> dict:
    """companion 素材:最新版原文、只在對應最新版時才給的分析與話題種子、最新版的進度。

    判斷層只給種子的種類和引文,不帶內文、opinion、feedback、結論(spec §7.4:判斷層的產物進 companion 會被當成自己的閱讀照念)。
    分析與筆記對應舊版時不給:引文會對不上新稿。
    """
    attachments = [{k: a[k] for k in ("n", "seq", "name", "text")}
                   for a in (repo.attachments(conn, discussion_id) if discussion_id is not None else ())
                   if a["source_version_id"] is None]
    if slug is None:
        return {"seeds": [], "slug": None, "title": None, "source": "", "analysis": None,
                "progress": "none", "memory": memory.load(conn, None), "attachments": attachments,
                "version": None, "versions": [], "compare": None, "old_sources": []}
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    latest = repo.latest_source_version(conn, st["id"])
    analysis = repo.current_artifact(conn, st["id"], "analysis")
    job = repo.latest_job(conn, st["id"], latest["id"])
    notes = repo.current_artifact(conn, st["id"], "notes")
    versions = repo.source_versions(conn, st["id"])
    if notes and notes["source_version_id"] == latest["id"]:
        seeds = [{"kind": p["kind"], "quotes": p["quotes"]} for p in notes["body"]["points"] if p["kind"] != "opinion"]
    else:
        seeds = _interim_seeds(conn, st["id"], versions, latest)
    old = None
    if cmp is not None:
        old = next((sv for sv in versions if sv["n"] == cmp and sv["n"] < latest["n"]), None)
        if old is None:
            raise UnknownVersion(cmp)
    return {
        "seeds": seeds,
        "version": latest["n"],
        "versions": [{"n": sv["n"], "text": sv["text"], "created_at": sv["created_at"]} for sv in versions],
        "compare": _compare(conn, st["id"], old, latest) if old else None,
        "old_sources": [old["text"]] if old else [],
        "slug": slug, "title": st["custom_title"] or st["title"], "source": latest["text"],
        "analysis": analysis["body"] if analysis and analysis["source_version_id"] == latest["id"] else None,
        "progress": job["state"] if job else "none",
        "memory": memory.load(conn, st["id"]),
        "attachments": attachments,
    }


def sources(ctx: dict) -> list[str]:
    return [*([ctx["source"]] if ctx["source"].strip() else []), *(a["text"] for a in ctx["attachments"]),
            *ctx["old_sources"]]


def _points_at(conn, story_id: int, sv: dict) -> list[dict]:
    notes = repo.artifact_at(conn, story_id, "notes", sv["id"])
    return [p for p in (notes["body"].get("points") or []) if p["kind"] != "opinion"] if notes else []


def _interim_seeds(conn, story_id: int, versions: list[dict], latest: dict) -> list[dict]:
    noted = repo.artifact_versions(conn, story_id, "notes")
    src = next((sv for sv in reversed(versions) if sv["n"] < latest["n"] and sv["n"] in noted), None)
    if src is None:
        return []
    d = compare.diff(src["text"], latest["text"])
    seeds = []
    for p in compare.trace(_points_at(conn, story_id, src), src["text"], latest["text"], d):
        qs = [latest["text"][q["new"]["start"]:q["new"]["end"]] for q in p["quotes"] if q["fate"] == "kept"]
        if qs:
            seeds.append({"kind": p["kind"], "quotes": qs})
    return seeds


def _compare(conn, story_id: int, old: dict, latest: dict) -> dict:
    d = compare.diff(old["text"], latest["text"])
    points = compare.trace(_points_at(conn, story_id, old), old["text"], latest["text"], d)
    return {"old": old["n"], "new": latest["n"],
            "changes": compare.changes(old["text"], latest["text"]),
            "hunks": len(d["hunks"]),
            "dels": sum(r["chars"] for r in d["runs"] if r["op"] == "del"),
            "inss": sum(r["end"] - r["start"] for r in d["runs"] if r["op"] == "ins"),
            "heavy": compare.rewrite_share(old["text"], latest["text"]) > 0.5,
            "fates": [{"kind": p["kind"], "quote": q["quote"], "fate": q["fate"]}
                      for p in points for q in p["quotes"] if q["fate"] != "lost"]}
