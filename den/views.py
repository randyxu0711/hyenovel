"""讀取視圖:DB → 領域形狀(純組裝,無 SQL;查詢全在 marrow.repo)。

den 的 API 回領域形狀(story / artifact / job),不回某個前端專用的形狀——翻成畫面要的樣子
是 client 自己的事。
"""
from den import spans, works
from marrow import gate, repo, vizdata


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


def _order_beats(beats: list[dict], edges: list[dict]) -> list[dict]:
    """沿 precedes 邊排成一條鏈;沒邊、斷鏈、分岔、有環 → 退回依 span.start(找不到位置的放最後,同位置保持原序)。"""
    ids = {b["id"] for b in beats}
    nxt = {e["from"]: e["to"] for e in edges
           if e["type"] == "precedes" and e["from"] in ids and e["to"] in ids}
    heads = [b for b in beats if b["id"] not in nxt.values()]
    if len(heads) == 1:
        by_id = {b["id"]: b for b in beats}
        chain, cur = [], heads[0]["id"]
        while cur in by_id and by_id[cur] not in chain:
            chain.append(by_id[cur])
            cur = nxt.get(cur)
        if len(chain) == len(beats):
            return chain
    def key(b):
        start = (b["span"] or {}).get("start")
        return (start is None, start or 0)
    return sorted(beats, key=key)


def work_map(conn, slug: str, v: int | None = None) -> dict:
    """對位資料:分析的 beat/motif 與同版同 job 的筆記,引文一律定位到第 v 版(預設最新)原文。
    分析屬較舊版時照給(analysis_version 老實標),定位不到的 start/end 為 None。"""
    st = repo.story_by_slug(conn, slug)
    if st is None:
        raise LookupError(slug)
    shown = repo.latest_source_version(conn, st["id"]) if v is None \
        else repo.source_version_by_n(conn, st["id"], v)
    if shown is None:
        raise UnknownVersion(v)
    text = shown["text"]
    out = {"version": shown["n"], "analysis_version": None, "notes_version": None,
           "beats": [], "motifs": [], "notes": None}
    ana = repo.current_artifact(conn, st["id"], "analysis")
    if ana is None:
        return out
    out["analysis_version"] = repo.source_version(conn, ana["source_version_id"])["n"]
    nodes = ana["body"].get("nodes") or []

    def spans_of(node):
        return spans.locate_all([e["quote"] for e in node.get("evidence") or []], text)

    beats = []
    for n in nodes:
        if n["type"] == "beat":
            sp = spans_of(n)
            beats.append({"id": n["id"], "label": n["label"], "intensity": n.get("intensity"),
                          "span": sp[0] if sp else None})
    out["beats"] = _order_beats(beats, ana["body"].get("edges") or [])
    out["motifs"] = [{"id": n["id"], "label": n["label"], "spans": spans_of(n)}
                     for n in nodes if n["type"] == "motif"]
    picked = vizdata.pick_judgment(ana, repo.current_artifact(conn, st["id"], "notes"), None)
    if picked is not None:
        body = picked[1]
        out["notes_version"] = out["analysis_version"]    # 配對要求同版,所以就是分析那一版
        out["notes"] = {"read": body.get("read"), "one_line": body.get("one_line"),
                        "points": [{"kind": p["kind"], "title": p["title"], "body": p.get("body"),
                                    "question": p.get("question"),
                                    "spans": spans.locate_all(p.get("quotes") or [], text)}
                                   for p in body.get("points") or []]}
    return out


def sessions(conn, slug: str, legacy: bool = False) -> list[dict]:
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
        is_legacy = not any(u["mode"] is not None for u in asst)
        if is_legacy != legacy:
            continue
        out.append({"session": sid, "started_at": us[0]["ts"], "last_at": last["ts"],
                    "turns": len(asst), "character": asst[-1]["character"] if asst else None,
                    "mode": asst[-1]["mode"] if asst else None,
                    "preview": asst[-1]["text"][:60] if asst else "",
                    "version": versions.get(asst[-1]["analysis_fp"]) if asst else None,
                    "legacy": is_legacy})
    out.sort(key=lambda s: s["last_at"], reverse=True)
    return out


def session_turns(conn, session: str, v: int | None = None) -> dict:
    """單局逐字。每則 turn 帶 spans = 引文在第 v 版(預設最新)原文的位移。
    assistant 的「」只收最新版原文找得到的(其餘是強調或複述,不是引文);再對 v 定位,這版沒有 → None。
    user 用其存下的 quotes。"""
    found = repo.discussions_by_external(conn, session)
    if not found:
        raise LookupError(session)
    if len(found) > 1:
        raise AmbiguousSession(session)
    d = found[0]
    latest = repo.latest_source_version(conn, d["story_id"])
    shown = latest if v is None else repo.source_version_by_n(conn, d["story_id"], v)
    if shown is None:
        raise UnknownVersion(v)
    us = repo.utterances(conn, d["id"])
    turns = []
    for u in us:
        if u["role"] == "assistant":
            qs = [q for q in spans.quotes_in(u["text"]) if gate.locate(q, latest["text"])]
        else:
            qs = u["quotes"] or []
        turns.append({"role": u["role"], "text": u["text"], "ts": u["ts"], "mode": u["mode"],
                      "character": u["character"], "quotes": u["quotes"] or [],
                      "spans": spans.locate_all(qs, shown["text"])})
    return {"session": session, "slug": d["slug"], "title": _title(conn, d["story_id"], d["slug"]),
            "legacy": not any(u["role"] == "assistant" and u["mode"] is not None for u in us),
            "version": shown["n"], "turns": turns}


def recent_sessions(conn, limit: int, legacy: bool = False) -> list[dict]:
    out = repo.recent_discussions(conn, limit, legacy)
    titles = {c["story_id"]: c["artifact"]["body"].get("title")
              for c in repo.current_artifacts(conn) if c["kind"] == "analysis"}
    ids = {st["slug"]: st["id"] for st in repo.stories(conn)}
    for d in out:
        d["title"] = titles.get(ids[d["slug"]]) or d["title"] or d["slug"]
        d["session"] = d.pop("external_id")   # 與 session_rows 同名,前端只認 session
        d["legacy"] = legacy
    return out
