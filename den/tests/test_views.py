"""den.views:DB → 領域形狀。用 repo 函式在 in-memory DB 造資料。"""
import pytest

from den import views
from marrow import db, repo


@pytest.fixture
def c():
    conn = db.connect("sqlite:///:memory:")
    db.migrate(conn, None)
    yield conn
    conn.close()


def _story(c, slug="x1", title="標", body=None, feedback=False):
    sid = repo.ensure_story(c, slug, title, 0)
    vid, _ = repo.add_source_version(c, sid, f"原文{slug}", 0)
    aid = None
    if body is not None:
        aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, body, {}, 5.0)
        repo.set_current(c, sid, "analysis", aid)
    fid = None
    if feedback:
        fid, _ = repo.add_artifact(c, sid, vid, "feedback", 1, {"f": slug}, {}, 6.0)
        repo.set_current(c, sid, "feedback", fid)
    return sid, vid, aid, fid


BODY = {"title": "分析標題", "synopsis": "梗概", "nodes": [{"id": "t1"}, {"id": "m1"}],
        "edges": [{"from": "t1", "to": "m1"}]}


def _job(c, sid, vid, state, step=None, error_class=None, now=1.0):
    jid = repo.create_job(c, "critique", sid, vid, {}, now)
    repo.set_job_state(c, jid, state, now + 1, step=step, error_class=error_class)
    return jid


def test_stories_done(c):
    sid, vid, aid, fid = _story(c, body=BODY, feedback=True)
    jid = _job(c, sid, vid, "done", step="render")
    [s] = views.stories(c)
    assert s["slug"] == "x1" and s["title"] == "分析標題" and s["synopsis"] == "梗概"
    assert s["current"]["analysis"] == {"id": aid, "created_at": 5.0}
    assert s["current"]["feedback"] == {"id": fid, "created_at": 6.0}
    assert s["latest_job"] == {"id": jid, "state": "done", "step": "render",
                               "error_class": None, "updated_at": 2.0}
    assert s["nodes"] == len(BODY["nodes"]) and s["edges"] == 1


def test_stories_analysis_kept_when_rerun_failed(c):
    sid, vid, aid, _ = _story(c, body=BODY)
    _job(c, sid, vid, "done")
    jid = _job(c, sid, vid, "failed", error_class="timeout", now=10.0)
    [s] = views.stories(c)
    assert s["current"]["analysis"]["id"] == aid
    assert s["latest_job"]["id"] == jid and s["latest_job"]["state"] == "failed"
    assert s["latest_job"]["error_class"] == "timeout"


def test_stories_queued_without_artifact(c):
    sid, vid, *_ = _story(c, title=None)
    _job(c, sid, vid, "queued")
    [s] = views.stories(c)
    assert s["current"] == {"analysis": None, "feedback": None}
    assert s["nodes"] == 0 and s["edges"] == 0 and s["synopsis"] == "" and s["title"] == "x1"
    assert s["latest_job"]["state"] == "queued"


def test_stories_title_falls_back_to_story_title(c):
    _story(c, title="故事標題", body={"nodes": [], "edges": []})
    [s] = views.stories(c)
    assert s["title"] == "故事標題" and s["nodes"] == 0


def test_stories_hides_story_without_artifact_or_job(c):
    _story(c, slug="empty")
    _story(c, slug="fbonly", feedback=True)                     # 只有 feedback 也不列
    assert views.stories(c) == []


def test_stories_sorted_by_slug(c):
    _story(c, slug="b", body=BODY)
    _story(c, slug="a", body=BODY)
    assert [s["slug"] for s in views.stories(c)] == ["a", "b"]


def _count_selects(c, fn):
    seen = []
    c.set_trace_callback(lambda sql: seen.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
    try:
        fn()
    finally:
        c.set_trace_callback(None)
    return len(seen)


def test_stories_constant_queries(c):
    sid, vid, *_ = _story(c, slug="a1", body=BODY, feedback=True)
    _job(c, sid, vid, "done")
    one = _count_selects(c, lambda: views.stories(c))
    for i in range(4):
        sid, vid, *_ = _story(c, slug=f"b{i}", body=BODY, feedback=True)
        _job(c, sid, vid, "done")
    assert len(views.stories(c)) == 5
    assert _count_selects(c, lambda: views.stories(c)) == one == 3


def test_conclusion_stale_rules(c):
    sid, vid, aid, _ = _story(c, body=BODY)
    new, _ = repo.add_artifact(c, sid, vid, "analysis", 1, {**BODY, "title": "新"}, {}, 9.0)
    rows = [("c1", aid, None, False),      # == current
            ("c2", None, None, True),       # artifact NULL
            ("c3", new, None, True),        # ≠ current
            ("c4", aid, 4.0, True)]         # invalidated
    for i, (ext, art, inv, _) in enumerate(rows):
        repo.add_conclusion(c, sid, ext, None, "observation", ext, ["t1"], ["引"], {}, float(i), inv)
        if art is not None:
            repo.set_conclusion_artifact(c, sid, ext, art)
    got = views.conclusions(c, "x1")
    assert [(x["id"], x["stale"]) for x in got] == [(r[0], r[3]) for r in rows]
    assert got[0] == {"id": "c1", "kind": "observation", "text": "c1", "refs": ["t1"],
                      "quotes": ["引"], "stale": False}


def test_conclusions_without_current_analysis_are_stale(c):
    sid, *_ = _story(c)
    repo.add_conclusion(c, sid, "c1", None, "question", "問", [], [], {}, 1.0, None)
    assert views.conclusions(c, "x1")[0]["stale"] is True


def test_transcript_shape_and_order(c):
    sid, *_ = _story(c)
    da = repo.ensure_discussion(c, sid, "sessA", "web", None, 0)
    db_ = repo.ensure_discussion(c, sid, "sessB", "web", None, 0)
    repo.add_utterance(c, da, 0, "user", "a0", 1.0, "den", ["t1"], None)
    repo.add_utterance(c, da, 1, "assistant", "a1", 4.0, "den", [], None)
    repo.add_utterance(c, db_, 0, "user", "b0", 2.0, "den", [], None)
    got = views.transcript(c, "x1")
    assert [t["text"] for t in got] == ["a0", "b0", "a1"]
    assert got[0] == {"ts": 1.0, "session": "sessA", "role": "user", "text": "a0",
                      "anchors": ["t1"]}
    assert isinstance(got[1]["anchors"], list) and got[1]["session"] == "sessB"


def test_unknown_slug_raises_lookup(c):
    with pytest.raises(LookupError):
        views.conclusions(c, "nope")
    with pytest.raises(LookupError):
        views.transcript(c, "nope")
