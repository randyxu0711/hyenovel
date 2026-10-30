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


def test_companion_context_never_includes_notes(conn):
    """spec §7.4:備課筆記只給作者,進 companion 會被當成自己的閱讀照念。"""
    from den.companion import render_companion
    st = repo.story_by_slug(conn, "mini")
    ana = repo.current_artifact(conn, st["id"], "analysis")
    notes = {"slug": "mini", "read": "筆記讀法甲乙", "one_line": "筆記一句丙丁", "points": [
        {"kind": "confused", "title": "筆記標題戊己", "quotes": ["像在等誰"], "refs": None,
         "body": "筆記內文庚辛", "question": None}]}
    with conn:
        nid, _ = repo.add_artifact(conn, st["id"], ana["source_version_id"], "notes", 1, notes, {}, 9.0)
        repo.set_current(conn, st["id"], "notes", nid)
    ctx = stories.companion_context(conn, "mini")
    text = repr(ctx) + render_companion(ctx, "direct")
    for marker in ("筆記讀法甲乙", "筆記一句丙丁", "筆記標題戊己", "筆記內文庚辛"):
        assert marker not in text


def test_companion_context_unknown_slug(conn):
    with pytest.raises(LookupError):
        stories.companion_context(conn, "nope")
