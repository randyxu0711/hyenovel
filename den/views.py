"""讀取視圖:DB → 領域形狀(純組裝,無 SQL;查詢全在 marrow.repo)。

den 的 API 回領域形狀(story / artifact / job),不回某個前端專用的形狀——翻成畫面要的樣子
是 client 自己的事。
"""
import bisect

from den import memory, spans, works
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
    svs = repo.source_versions(conn, st["id"])
    analysed = repo.artifact_versions(conn, st["id"], "analysis")
    noted = repo.artifact_versions(conn, st["id"], "notes")
    return {"slug": slug, "title": row["title"], "version": shown["version"] if v is None else shown["n"],
            "text": shown["latest_text"] if v is None else shown["text"],
            "versions": [x["n"] for x in svs],
            "history": [{"n": x["n"], "at": x["created_at"], "analysed": x["n"] in analysed, "noted": x["n"] in noted}
                        for x in svs],
            "state": row["state"], "job_id": row["job_id"],
            "notes_ready": notes is not None and notes["source_version_id"] == row["latest_sv_id"]}


def _drift(nodes: list[dict], text: str) -> dict:
    """舊分析的引文在 text 裡還站得住幾句:total/lost 為條數,orphaned = 有引文但全找不到的節點。"""
    total = lost = 0
    orphaned = []
    for n in nodes:
        sp = spans.locate_all([e["quote"] for e in n.get("evidence") or []], text)
        miss = sum(1 for s in sp if s["start"] is None)
        total += len(sp)
        lost += miss
        if sp and miss == len(sp):
            orphaned.append({"id": n["id"], "type": n["type"], "label": n["label"]})
    return {"total": total, "lost": lost, "orphaned": orphaned}


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
           "beats": [], "motifs": [], "notes": None, "drift": None}
    ana = repo.current_artifact(conn, st["id"], "analysis")
    if ana is None:
        return out
    out["analysis_version"] = repo.source_version(conn, ana["source_version_id"])["n"]
    nodes = ana["body"].get("nodes") or []
    if out["analysis_version"] != shown["n"]:
        out["drift"] = _drift(nodes, text)

    def spans_of(node):
        return spans.locate_all([e["quote"] for e in node.get("evidence") or []], text)

    beats = []
    for n in nodes:
        if n["type"] == "beat":
            sp = spans_of(n)
            beats.append({"id": n["id"], "label": n["label"], "intensity": n.get("intensity"),
                          "span": sp[0] if sp else None})
    out["beats"] = works.order_beats(beats, ana["body"].get("edges") or [])
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
    made = [sv["created_at"] for sv in repo.source_versions(conn, st["id"])]   # 依 n 升序,與 ts 同為 epoch 秒
    out = []
    for sid, us in by.items():
        asst = [u for u in us if u["role"] == "assistant"]
        last = us[-1]
        is_legacy = not any(u["character"] is not None for u in asst)
        if is_legacy != legacy:
            continue
        out.append({"session": sid, "started_at": us[0]["ts"], "last_at": last["ts"],
                    "turns": len(asst), "character": asst[-1]["character"] if asst else None,
                    "preview": us[0]["text"][:60],   # 這局的第一句話(us 依 ts, seq 排)
                    "version": versions.get(asst[-1]["analysis_fp"]) if asst else None,
                    "legacy": is_legacy, "versions": _span(made, us)})
    out.sort(key=lambda s: s["last_at"], reverse=True)
    return out


def _at(made: list[float], ts: float) -> int:
    """ts 當下的原文版本(made = 各版建立時間,依 n 升序)。"""
    return max(bisect.bisect_right(made, ts), 1)


def _span(made: list[float], us: list[dict]) -> list[int]:
    """這局發言(含作者)當下的原文版本範圍 [lo, hi]。局由發言組成,us 不會空。"""
    vs = [_at(made, u["ts"]) for u in us]
    return [min(vs), max(vs)]


def session_turns(conn, session: str, v: int | None = None) -> dict:
    """單局逐字。每則 turn 帶 spans = 引文在第 v 版(預設最新)原文的位移。
    assistant 的「」只收最新版原文找得到的(其餘是強調或複述,不是引文);再對 v 定位,這版沒有 → None。
    user 用其存下的 quotes。"""
    d = repo.discussion_by_session(conn, session)
    if d is None:
        raise LookupError(session)
    latest = repo.latest_source_version(conn, d["story_id"])
    shown = latest if v is None else repo.source_version_by_n(conn, d["story_id"], v)
    if shown is None:
        raise UnknownVersion(v)
    us = repo.utterances(conn, d["id"])
    made = [sv["created_at"] for sv in repo.source_versions(conn, d["story_id"])]   # 依 n 升序,與 ts 同為 epoch 秒
    marked = repo.reactions(conn, d["id"])
    remembered: dict[int, list[dict]] = {}
    for m in repo.memories_of_discussion(conn, d["id"]):
        remembered.setdefault(m["seq"], []).append({"id": m["id"], "scope": m["scope"]})
    turns = []
    for u in us:
        if u["role"] == "assistant":
            qs = [q for q in spans.quotes_in(u["text"]) if gate.locate(q, latest["text"])]
        else:
            qs = u["quotes"] or []
        turns.append({"seq": u["seq"], "reaction": marked.get(u["seq"]),
                      "memories": remembered.get(u["seq"], []),
                      "role": u["role"], "text": u["text"], "ts": u["ts"],
                      "character": u["character"], "quotes": u["quotes"] or [],
                      "spans": spans.locate_all(qs, shown["text"]),
                      "v": _at(made, u["ts"])})   # 說話當時的版本
    return {"session": session, "slug": d["slug"], "title": _title(conn, d["story_id"], d["slug"]),
            "legacy": not any(u["role"] == "assistant" and u["character"] is not None for u in us),
            "version": shown["n"], "turns": turns}


def memory_row(conn, row: dict) -> dict:
    return {"id": row["id"], "root": row["id"] if row["root_id"] is None else row["root_id"],
            "scope": row["scope"], "slug": row["slug"],
            "title": None if row["work_id"] is None else _title(conn, row["work_id"], row["slug"]),
            "text": row["text"],
            "quote": row["quote"], "session": row["session"], "seq": row["seq"],
            "valid_from": row["valid_from"], "learned_at": row["learned_at"],
            "invalidated_at": row["invalidated_at"]}


def memories(conn) -> dict:
    return {"memories": [memory_row(conn, r) for r in repo.all_memories(conn)],
            "caps": {"author": memory.CAPS["author"], "work": memory.CAPS["work"]}}


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
