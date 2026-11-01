"""den.views 的 dashboard 讀取視圖:作品詳情、局列表、單局逐字、最近的局。"""
import pytest

from den import views
from marrow import db, repo


@pytest.fixture
def c():
    conn = db.connect("sqlite:///:memory:")
    db.migrate(conn, None)
    yield conn
    conn.close()


def _story(c, slug="x1", title="標", text="原文"):
    sid = repo.ensure_story(c, slug, title, 0)
    vid, _ = repo.add_source_version(c, sid, text, 1.0)
    return sid, vid


def test_work_detail_notes_ready_only_for_latest_version(c):
    sid, v1 = _story(c)
    nid, _ = repo.add_artifact(c, sid, v1, "notes", 1, {"n": 1}, {}, 2.0)
    repo.set_current(c, sid, "notes", nid)
    assert views.work_detail(c, "x1")["notes_ready"] is True
    repo.add_source_version(c, sid, "新版原文", 3.0)
    d = views.work_detail(c, "x1")
    assert d == {"slug": "x1", "title": "標", "version": 2, "text": "新版原文", "state": "none",
                 "job_id": None, "notes_ready": False, "versions": [1, 2]}


def test_work_detail_without_notes_and_unknown(c):
    _story(c)
    assert views.work_detail(c, "x1")["notes_ready"] is False
    with pytest.raises(LookupError):
        views.work_detail(c, "nope")


def test_work_detail_versions(c):
    sid, v1 = _story(c)
    repo.add_source_version(c, sid, "新版原文", 3.0)
    d = views.work_detail(c, "x1")
    assert d["versions"] == [1, 2] and d["version"] == 2 and d["text"] == "新版原文"
    old = views.work_detail(c, "x1", v=1)
    assert old["version"] == 1 and old["text"] == "原文" and old["versions"] == [1, 2]
    assert old["state"] == d["state"] and old["notes_ready"] == d["notes_ready"]


def test_work_detail_unknown_version(c):
    _story(c)
    with pytest.raises(views.UnknownVersion):
        views.work_detail(c, "x1", v=9)


def _say(c, d, seq, role, text, ts, analysis_fp=None, **kw):
    repo.add_utterance(c, d, seq, role, text, ts, "den", [], analysis_fp, **kw)


def test_sessions_preview_mode_and_turns(c):
    sid, v1 = _story(c)
    a1, _ = repo.add_artifact(c, sid, v1, "analysis", 1, {"t": 1}, {}, 1.5)
    fp1 = repo.artifact(c, a1)["sha256"]
    old = repo.ensure_discussion(c, sid, "old", "web", None, 2.0)
    _say(c, old, 0, "user", "問", 2.0)
    _say(c, old, 1, "assistant", "舊答", 3.0, mode="direct", character="buffalo", analysis_fp=fp1)
    v2, _ = repo.add_source_version(c, sid, "二版", 10.0)
    a2, _ = repo.add_artifact(c, sid, v2, "analysis", 1, {"t": 2}, {}, 10.5)
    fp2 = repo.artifact(c, a2)["sha256"]
    new = repo.ensure_discussion(c, sid, "new", "web", None, 11.0)
    _say(c, new, 0, "user", "問", 11.0)
    _say(c, new, 1, "assistant", "一" * 70, 12.0, mode="slow", character="hyena", analysis_fp=fp2)
    _say(c, new, 2, "user", "追問", 13.0)
    mid = repo.ensure_discussion(c, sid, "mid", "web", None, 9.0)         # 聊到一半交了新版:仍是讀 v1 的分析
    _say(c, mid, 0, "user", "問", 9.0)
    _say(c, mid, 1, "assistant", "答", 9.5, analysis_fp=fp1, mode="slow")
    _say(c, mid, 2, "user", "再問", 13.5)
    pre = repo.ensure_discussion(c, sid, "early", "web", None, 0.5)       # 分析前的聊天:fp 為 NULL
    _say(c, pre, 0, "user", "先問", 0.5)
    _say(c, pre, 1, "assistant", "答", 0.6, mode="slow")
    got = {s["session"]: s for s in views.sessions(c, "x1")}
    assert [s["session"] for s in views.sessions(c, "x1")] == ["mid", "new", "old", "early"]
    assert got["new"] == {"session": "new", "started_at": 11.0, "last_at": 13.0, "turns": 1,
                          "character": "hyena", "mode": "slow", "preview": "一" * 60, "version": 2,
                          "legacy": False}
    assert got["old"]["version"] == 1 and got["old"]["character"] == "buffalo"
    assert got["mid"]["version"] == 1
    assert got["early"]["version"] is None
    with pytest.raises(LookupError):
        views.sessions(c, "nope")


def test_sessions_without_assistant_turn(c):
    sid, _ = _story(c)
    d = repo.ensure_discussion(c, sid, "q", "web", None, 1.0)
    _say(c, d, 0, "user", "先問", 1.0)
    [s] = views.sessions(c, "x1", legacy=True)   # 沒有 assistant 發言 = 沒有 mode = 舊局
    assert (s["turns"], s["character"], s["mode"], s["preview"], s["version"]) == (0, None, None, "", None)
    assert s["legacy"] is True


def test_session_turns_unknown_and_ambiguous(c):
    sid, _ = _story(c)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "user", "問", 1.0, quotes=["原"])
    _say(c, d, 1, "assistant", "答", 2.0, mode="slow", character="hyena")
    got = views.session_turns(c, "s")
    assert got == {"session": "s", "slug": "x1", "title": "標", "legacy": False, "version": 1, "turns": [
        {"role": "user", "text": "問", "ts": 1.0, "mode": None, "character": None, "quotes": ["原"],
         "spans": [{"quote": "原", "start": 0, "end": 1}]},
        {"role": "assistant", "text": "答", "ts": 2.0, "mode": "slow", "character": "hyena",
         "quotes": [], "spans": []}]}
    with pytest.raises(LookupError):
        views.session_turns(c, "nope")
    sid2, _ = _story(c, "x2")
    repo.ensure_discussion(c, sid2, "s", "web", None, 1.0)
    with pytest.raises(views.AmbiguousSession):
        views.session_turns(c, "s")


def test_session_title_prefers_analysis_title(c):
    sid, vid = _story(c)
    aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, {"title": "分析標題"}, {}, 2.0)
    repo.set_current(c, sid, "analysis", aid)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "assistant", "答", 1.0, mode="slow", character="hyena")
    assert views.session_turns(c, "s")["title"] == "分析標題"
    assert views.recent_sessions(c, 5)[0]["title"] == "分析標題"
    assert views.recent_sessions(c, 5)[0]["session"] == "s"


def test_recent_sessions_falls_back_to_story_title_then_slug(c):
    sid, _ = _story(c, "x1", None)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "assistant", "答", 1.0, mode="slow", character="hyena")
    assert views.recent_sessions(c, 5)[0]["title"] == "x1"
    assert views.session_turns(c, "s")["title"] == "x1"


def _legacy_pair(c, sid):
    new = repo.ensure_discussion(c, sid, "new", "web", None, 1.0)
    _say(c, new, 0, "user", "問", 1.0)
    _say(c, new, 1, "assistant", "答", 2.0, mode="slow", character="hyena")
    old = repo.ensure_discussion(c, sid, "old", "web", None, 3.0)
    _say(c, old, 0, "user", "問", 3.0)
    _say(c, old, 1, "assistant", "舊答", 4.0)


def test_sessions_legacy_flag_and_filter(c):
    sid, _ = _story(c)
    _legacy_pair(c, sid)
    assert [(s["session"], s["legacy"]) for s in views.sessions(c, "x1")] == [("new", False)]
    assert [(s["session"], s["legacy"]) for s in views.sessions(c, "x1", legacy=True)] == [("old", True)]


def test_recent_sessions_excludes_legacy(c):
    sid, _ = _story(c)
    for i in range(3):
        d = repo.ensure_discussion(c, sid, f"n{i}", "web", None, float(i))
        _say(c, d, 0, "assistant", "答", float(i), mode="slow", character="hyena")
    old = repo.ensure_discussion(c, sid, "old", "web", None, 9.0)
    _say(c, old, 0, "assistant", "舊答", 9.0)
    got = views.recent_sessions(c, 2)
    assert [(s["session"], s["legacy"]) for s in got] == [("n2", False), ("n1", False)]
    assert [(s["session"], s["legacy"]) for s in views.recent_sessions(c, 5, legacy=True)] == [("old", True)]


def test_session_turns_spans(c):
    sid, v1 = _story(c, text="海很深。山很高。")
    repo.add_source_version(c, sid, "海很深。浪很大。山很高。", 5.0)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "user", "問", 1.0, quotes=["山很高"])
    _say(c, d, 1, "assistant", "「海很深」、「浪很大」、「不存在的話」、「山很高」。", 2.0,
         mode="slow", character="hyena")
    latest = views.session_turns(c, "s")
    assert latest["version"] == 2 and latest["legacy"] is False
    user, asst = latest["turns"]
    assert user["spans"] == [{"quote": "山很高", "start": 8, "end": 11}]
    assert asst["spans"] == [{"quote": "海很深", "start": 0, "end": 3},
                             {"quote": "浪很大", "start": 4, "end": 7},
                             {"quote": "山很高", "start": 8, "end": 11}]   # 不存在的話不在
    old = views.session_turns(c, "s", v=1)
    assert old["version"] == 1
    assert old["turns"][0]["spans"] == [{"quote": "山很高", "start": 4, "end": 7}]
    assert old["turns"][1]["spans"] == [{"quote": "海很深", "start": 0, "end": 3},
                                        {"quote": "浪很大", "start": None, "end": None},
                                        {"quote": "山很高", "start": 4, "end": 7}]


def test_session_turns_unknown_version_and_legacy(c):
    sid, _ = _story(c)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "assistant", "舊答", 2.0)
    assert views.session_turns(c, "s")["legacy"] is True
    with pytest.raises(views.UnknownVersion):
        views.session_turns(c, "s", v=9)


TEXT = "他進了門。窗外下雨。她沒說話。雨停了。"


def _ana(c, sid, vid, job=None, nodes=None, edges=None, now=2.0):
    nodes = nodes if nodes is not None else [
        {"id": "b2", "type": "beat", "label": "雨", "intensity": 0.7, "evidence": [{"quote": "窗外下雨", "note": ""}]},
        {"id": "b1", "type": "beat", "label": "門", "intensity": 0.3, "evidence": [{"quote": "他進了門", "note": ""}]},
        {"id": "b3", "type": "beat", "label": "靜", "intensity": 0.5, "evidence": [{"quote": "她沒說話", "note": ""}]},
        {"id": "m1", "type": "motif", "label": "雨", "intensity": None,
         "evidence": [{"quote": "窗外下雨", "note": ""}, {"quote": "雨停了", "note": ""}]},
        {"id": "t1", "type": "theme", "label": "主題", "evidence": []}]
    edges = edges if edges is not None else [
        {"type": "precedes", "from": "b1", "to": "b2", "note": ""},
        {"type": "precedes", "from": "b2", "to": "b3", "note": ""}]
    aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, {"title": "t", "nodes": nodes, "edges": edges},
                               {"job": job} if job else {}, now)
    repo.set_current(c, sid, "analysis", aid)


def _notes(c, sid, vid, job=None):
    body = {"read": "讀", "one_line": "一句", "points": [
        {"kind": "strength", "title": "標", "quotes": ["雨停了", "不存在的句子"], "refs": ["m1"],
         "body": "內文", "question": "問?"}]}
    nid, _ = repo.add_artifact(c, sid, vid, "notes", 1, body, {"job": job} if job else {}, 3.0)
    repo.set_current(c, sid, "notes", nid)


def test_map_full(c):
    sid, vid = _story(c, text=TEXT)
    _ana(c, sid, vid)
    _notes(c, sid, vid)
    m = views.work_map(c, "x1")
    assert (m["version"], m["analysis_version"], m["notes_version"]) == (1, 1, 1)
    assert [b["id"] for b in m["beats"]] == ["b1", "b2", "b3"]          # 依 precedes,不是陣列順序
    assert m["beats"][0] == {"id": "b1", "label": "門", "intensity": 0.3,
                             "span": {"quote": "他進了門", "start": 0, "end": 4}}
    [mo] = m["motifs"]
    assert mo["id"] == "m1" and [(s["start"], s["end"]) for s in mo["spans"]] == [(5, 9), (15, 18)]
    n = m["notes"]
    assert (n["read"], n["one_line"]) == ("讀", "一句")
    [p] = n["points"]
    assert (p["kind"], p["title"], p["body"], p["question"]) == ("strength", "標", "內文", "問?")
    assert p["spans"] == [{"quote": "雨停了", "start": 15, "end": 18},
                          {"quote": "不存在的句子", "start": None, "end": None}]


def test_map_beats_without_edges_sort_by_span_unlocated_last(c):
    sid, vid = _story(c, text=TEXT)
    nodes = [
        {"id": "b1", "type": "beat", "label": "x", "intensity": 0.1, "evidence": [{"quote": "不存在", "note": ""}]},
        {"id": "b2", "type": "beat", "label": "y", "intensity": 0.1, "evidence": [{"quote": "雨停了", "note": ""}]},
        {"id": "b3", "type": "beat", "label": "z", "intensity": 0.1, "evidence": [{"quote": "他進了門", "note": ""}]},
        {"id": "b4", "type": "beat", "label": "w", "intensity": 0.1, "evidence": None}]
    _ana(c, sid, vid, nodes=nodes, edges=[])
    m = views.work_map(c, "x1")
    assert [b["id"] for b in m["beats"]] == ["b3", "b2", "b1", "b4"]
    assert m["beats"][3]["span"] is None


def test_map_no_analysis(c):
    _story(c)
    assert views.work_map(c, "x1") == {"version": 1, "analysis_version": None, "notes_version": None,
                                       "beats": [], "motifs": [], "notes": None}


def test_map_stale_analysis(c):
    sid, v1 = _story(c, text=TEXT)
    _ana(c, sid, v1)
    repo.add_source_version(c, sid, "他進了門。完全改寫。", 3.0)
    m = views.work_map(c, "x1")
    assert m["version"] == 2 and m["analysis_version"] == 1
    b = {x["id"]: x for x in m["beats"]}
    assert b["b1"]["span"]["start"] == 0 and b["b2"]["span"]["start"] is None
    old = views.work_map(c, "x1", v=1)
    assert old["version"] == 1 and old["analysis_version"] == 1
    assert old["beats"][1]["span"]["start"] == 5


def test_map_notes_missing(c):
    sid, vid = _story(c, text=TEXT)
    _ana(c, sid, vid)
    m = views.work_map(c, "x1")
    assert m["beats"] and m["notes"] is None and m["notes_version"] is None


def test_map_notes_from_other_job_not_paired(c):
    sid, vid = _story(c, text=TEXT)
    _ana(c, sid, vid, job=2)
    _notes(c, sid, vid, job=1)
    m = views.work_map(c, "x1")
    assert m["notes"] is None and m["notes_version"] is None


def test_map_unknown_version_and_work(c):
    _story(c)
    with pytest.raises(views.UnknownVersion):
        views.work_map(c, "x1", v=9)
    with pytest.raises(LookupError):
        views.work_map(c, "nope")
