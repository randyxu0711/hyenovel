"""den.stories 行為契約。用 conn fixture(mini 已匯入);呼叫者包 with conn,測試照做。"""
import pytest

from den import config, stories
from marrow import repo


def _ingest(conn, text, title=None, slug=None):
    with conn:
        return stories.ingest(conn, text, title, slug, 5.0)


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM story").fetchone()[0]


def test_ingest_new_story_gets_d_slug(conn):
    out = _ingest(conn, "他走進門。\n", "標題")
    assert out == {"slug": "d01", "title": "標題", "version": 1, "new_version": True,
                   "reused": False}


def test_ingest_same_text_no_slug_reuses(conn):
    _ingest(conn, "他走進門。")
    n = _count(conn)
    out = _ingest(conn, "他走進門。")
    assert out["reused"] is True and out["new_version"] is False and out["slug"] == "d01"
    assert _count(conn) == n


def test_ingest_with_slug_new_version(conn):
    _ingest(conn, "初稿。")                       # 先無 slug 建出 d01
    out = _ingest(conn, "改稿。", slug="d01")
    assert out["version"] == 2 and out["new_version"] is True and out["reused"] is False
    again = _ingest(conn, "改稿。", slug="d01")
    assert again["version"] == 2 and again["new_version"] is False


def test_ingest_normalizes_before_sha(conn):
    _ingest(conn, "a\r\n")
    out = _ingest(conn, "a\n")
    assert out["reused"] is True


def test_ingest_rejects_blank(conn):
    with pytest.raises(ValueError, match="空白故事"):
        _ingest(conn, " \n\t ")


def test_ingest_rejects_oversize(conn):
    with pytest.raises(ValueError, match="原文過長"):
        _ingest(conn, "字" * (config.MAX_SOURCE_BYTES // 3 + 1))


def test_ingest_unknown_slug_rejected(conn):
    n = _count(conn)
    for slug in ("s07", "d1", "d01"):
        with pytest.raises(ValueError, match="unknown slug"):
            _ingest(conn, "x", slug=slug)
    assert _count(conn) == n


def test_ingest_rejects_bad_slug(conn):
    with pytest.raises(ValueError, match="bad slug"):
        _ingest(conn, "x", slug="../x")


def test_discussion_context_ok(conn):
    out = stories.discussion_context(conn, "mini")
    assert set(out) == {"slug", "title", "source", "stale", "analysis", "feedback", "conclusions"}
    assert out["stale"] is False and out["slug"] == "mini"
    assert out["source"] == repo.latest_source_version(conn, repo.story_by_slug(conn, "mini")["id"])["text"]
    assert isinstance(out["analysis"], dict)


def test_discussion_context_stale_after_revision(conn):
    with conn:
        repo.add_source_version(conn, repo.story_by_slug(conn, "mini")["id"], "新稿。", 9.0)
    out = stories.discussion_context(conn, "mini")
    assert out["stale"] is True
    assert out["source"] != "新稿。"


def test_discussion_context_unknown_slug(conn):
    with pytest.raises(LookupError):
        stories.discussion_context(conn, "nope")


def test_discussion_context_not_analyzed(conn):
    _ingest(conn, "還沒分析。")
    with pytest.raises(ValueError, match="not-analyzed"):
        stories.discussion_context(conn, "d01")


def test_discussion_context_hides_invalidated_conclusions(conn):
    sid = repo.story_by_slug(conn, "mini")["id"]
    with conn:
        repo.add_conclusion(conn, sid, "c1", None, "reading", "活的", ["m1"], ["q"], {}, 1.0, None)
        repo.add_conclusion(conn, sid, "c2", None, "reading", "死的", [], [], {}, 2.0, 3.0)
    out = stories.discussion_context(conn, "mini")
    assert out["conclusions"] == [{"kind": "reading", "text": "活的", "refs": ["m1"], "quotes": ["q"],
                                   "stale": True}]   # artifact 未知 → 舊


def test_discussion_context_conclusion_staleness_follows_current_analysis(conn):
    sid = repo.story_by_slug(conn, "mini")["id"]
    a = repo.current_artifact(conn, sid, "analysis")
    with conn:
        repo.add_conclusion(conn, sid, "c1", None, "reading", "對得上", [], [], {}, 1.0, None)
        repo.set_conclusion_artifact(conn, sid, "c1", a["id"])
        repo.add_conclusion(conn, sid, "c2", None, "reading", "對舊稿", [], [], {}, 2.0, None)
        repo.set_conclusion_artifact(conn, sid, "c2", a["id"])
        new, _ = repo.add_artifact(conn, sid, a["source_version_id"], "analysis", 1, {"x": 1}, {}, 9.0)
        repo.add_conclusion(conn, sid, "c3", None, "reading", "對新稿", [], [], {}, 3.0, None)
        repo.set_conclusion_artifact(conn, sid, "c3", new)
    before = {c["text"]: c["stale"] for c in stories.discussion_context(conn, "mini")["conclusions"]}
    assert before == {"對得上": False, "對舊稿": False, "對新稿": True}
    with conn:
        repo.set_current(conn, sid, "analysis", new)
    after = {c["text"]: c["stale"] for c in stories.discussion_context(conn, "mini")["conclusions"]}
    assert after == {"對得上": True, "對舊稿": True, "對新稿": False}


def test_discussion_context_feedback_when_present(conn):
    sid = repo.story_by_slug(conn, "mini")["id"]
    a = repo.current_artifact(conn, sid, "analysis")
    with conn:
        aid, _ = repo.add_artifact(conn, sid, a["source_version_id"], "feedback", 1,
                                   {"items": []}, {}, 2.0)
        repo.set_current(conn, sid, "feedback", aid)
    assert stories.discussion_context(conn, "mini")["feedback"] == {"items": []}


# ── companion_context ──

def test_companion_context_keys_have_no_judgment_layer(conn):
    out = stories.companion_context(conn, "mini")
    assert set(out) == {"slug", "title", "source", "analysis", "progress"}
    assert isinstance(out["analysis"], dict) and out["progress"] == "none"


def test_companion_context_unanalyzed_story_has_source_only(conn):
    _ingest(conn, "還沒分析。")
    out = stories.companion_context(conn, "d01")
    assert out["analysis"] is None and out["source"] == "還沒分析。\n" and out["progress"] == "none"


def test_companion_context_hides_stale_analysis(conn):
    _ingest(conn, "改過的新稿。", slug="mini")
    out = stories.companion_context(conn, "mini")
    assert out["analysis"] is None and out["source"] == "改過的新稿。\n"


def test_companion_context_progress_reports_latest_job_state(conn):
    _ingest(conn, "還沒分析。")
    st = repo.story_by_slug(conn, "d01")
    v = repo.latest_source_version(conn, st["id"])["id"]
    with conn:
        j = repo.create_job(conn, "critique", st["id"], v, {}, 6.0)
        repo.set_job_state(conn, j, "running", 7.0)
    assert stories.companion_context(conn, "d01")["progress"] == "running"


def test_companion_context_unknown_slug(conn):
    with pytest.raises(LookupError):
        stories.companion_context(conn, "nope")
