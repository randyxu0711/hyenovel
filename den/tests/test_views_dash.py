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
                 "job_id": None, "notes_ready": False}


def test_work_detail_without_notes_and_unknown(c):
    _story(c)
    assert views.work_detail(c, "x1")["notes_ready"] is False
    with pytest.raises(LookupError):
        views.work_detail(c, "nope")


def _say(c, d, seq, role, text, ts, **kw):
    repo.add_utterance(c, d, seq, role, text, ts, "den", [], None, **kw)


def test_sessions_preview_mode_and_turns(c):
    sid, _ = _story(c)
    repo.add_source_version(c, sid, "二版", 10.0)
    old = repo.ensure_discussion(c, sid, "old", "web", None, 2.0)
    _say(c, old, 0, "user", "問", 2.0)
    _say(c, old, 1, "assistant", "舊答", 3.0, mode="direct", character="buffalo")
    new = repo.ensure_discussion(c, sid, "new", "web", None, 11.0)
    _say(c, new, 0, "user", "問", 11.0)
    _say(c, new, 1, "assistant", "一" * 70, 12.0, mode="slow", character="hyena")
    _say(c, new, 2, "user", "追問", 13.0)
    pre = repo.ensure_discussion(c, sid, "early", "web", None, 0.5)       # 第一版交稿前就有的局
    _say(c, pre, 0, "user", "先問", 0.5)
    got = views.sessions(c, "x1")
    assert [s["session"] for s in got] == ["new", "old", "early"]
    assert got[0] == {"session": "new", "started_at": 11.0, "last_at": 13.0, "turns": 1,
                      "character": "hyena", "mode": "slow", "preview": "一" * 60, "version": 2}
    assert got[1]["version"] == 1 and got[1]["character"] == "buffalo"
    assert (got[2]["turns"], got[2]["character"], got[2]["mode"], got[2]["preview"],
            got[2]["version"]) == (0, None, None, "", None)
    with pytest.raises(LookupError):
        views.sessions(c, "nope")


def test_session_turns_unknown_and_ambiguous(c):
    sid, _ = _story(c)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "user", "問", 1.0, quotes=["原"])
    _say(c, d, 1, "assistant", "答", 2.0, mode="slow", character="hyena")
    got = views.session_turns(c, "s")
    assert got == {"session": "s", "slug": "x1", "title": "標", "turns": [
        {"role": "user", "text": "問", "ts": 1.0, "mode": None, "character": None, "quotes": ["原"]},
        {"role": "assistant", "text": "答", "ts": 2.0, "mode": "slow", "character": "hyena",
         "quotes": []}]}
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
    _say(c, d, 0, "user", "問", 1.0)
    assert views.session_turns(c, "s")["title"] == "分析標題"
    assert views.recent_sessions(c, 5)[0]["title"] == "分析標題"


def test_recent_sessions_falls_back_to_story_title_then_slug(c):
    sid, _ = _story(c, "x1", None)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 1.0)
    _say(c, d, 0, "user", "問", 1.0)
    assert views.recent_sessions(c, 5)[0]["title"] == "x1"
    assert views.session_turns(c, "s")["title"] == "x1"
