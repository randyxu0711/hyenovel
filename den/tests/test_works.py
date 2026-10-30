"""den.works:作品視圖(比對、狀態、排序、讀 part)。in-memory DB,用 repo 造資料。"""
import pytest

from den import works
from marrow import db, repo


@pytest.fixture
def c():
    conn = db.connect("sqlite:///:memory:")
    db.migrate(conn, None)
    yield conn
    conn.close()


def _row(slug, title, text):
    return {"slug": slug, "title": title, "latest_text": text}


def test_match_single_char_title_and_opening_only():
    rows = [_row("d01", "海", "她走到岸邊。"), _row("d02", "豆花", "早上。" + "x" * 300 + "海"),
            _row("d03", None, "海風很大。")]
    assert [r["slug"] for r in works.match(rows, "海")] == ["d01", "d03"]


def test_match_exact_slug_wins():
    rows = [_row("d01", "d02 的續篇", ""), _row("d02", "豆花", "")]
    assert [r["slug"] for r in works.match(rows, "d02")] == ["d02"]


def test_match_ignores_whitespace_and_case():
    assert works.match([_row("d01", "Blue Sea", "")], " blue  sea ")


def test_match_empty_query_returns_all():
    rows = [_row("d01", "a", ""), _row("d02", "b", "")]
    assert len(works.match(rows, "  ")) == 2 and len(works.match(rows, None)) == 2


LATEST, OLD = 2, 1


@pytest.mark.parametrize("ana_ver,job,want", [
    (LATEST, None, "ready"), (None, (LATEST, "running"), "running"), (None, (LATEST, "queued"), "running"),
    (None, (LATEST, "paused"), "stopped"), (None, (LATEST, "failed"), "stopped"),
    (OLD, None, "stale"), (OLD, (OLD, "running"), "stale"), (None, (OLD, "done"), "none"),
    (None, None, "none"), (LATEST, (LATEST, "running"), "ready")])
def test_state(ana_ver, job, want):
    row = {"latest_sv_id": LATEST}
    ana = None if ana_ver is None else {"source_version_id": ana_ver}
    j = None if job is None else {"source_version_id": job[0], "state": job[1]}
    assert works.state(row, ana, j) == want


def _story(c, slug, title, text, now):
    sid = repo.ensure_story(c, slug, title, now)
    vid, _ = repo.add_source_version(c, sid, text, now)
    return sid, vid


def test_listing_orders_by_recent_activity(c):
    _story(c, "d01", "舊", "舊稿", 1.0)
    _story(c, "d02", "新", "新稿", 5.0)
    sid, _ = _story(c, "d03", "剛聊", "聊過", 0.5)
    d = repo.ensure_discussion(c, sid, "s", "mcp", None, 9.0)
    repo.close_discussion(c, d, 9.0)
    assert [w["slug"] for w in works.listing(c, None)] == ["d03", "d02", "d01"]
    assert [w["slug"] for w in works.listing(c, None, limit=1)] == ["d03"]


def test_listing_title_prefers_analysis_title(c):
    sid, vid = _story(c, "d01", "故事標題", "她走了。\n\n海很冷。", 1.0)
    aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, {"title": "分析標題"}, {}, 2.0)
    repo.set_current(c, sid, "analysis", aid)
    _story(c, "d02", None, "x", 1.0)
    w = {x["slug"]: x for x in works.listing(c, None)}
    assert w["d01"]["title"] == "分析標題" and w["d01"]["state"] == "ready"
    assert w["d01"]["opening"] == "她走了。海很冷。"
    assert w["d02"]["title"] == "d02" and w["d02"]["state"] == "none"


def test_listing_job_fields_only_when_running_or_stopped(c):
    sid, vid = _story(c, "d01", "t", "x", 1.0)
    jid = repo.create_job(c, "critique", sid, vid, {}, 2.0)
    repo.set_job_state(c, jid, "paused", 3.0, error_class="usage-limit")
    [w] = works.listing(c, None)
    assert (w["state"], w["job_id"], w["error_class"]) == ("stopped", jid, "usage-limit")
    repo.set_job_state(c, jid, "done", 4.0)
    [w] = works.listing(c, None)
    assert (w["state"], w["job_id"], w["error_class"]) == ("none", None, None)


def test_listing_opening_truncated(c):
    _story(c, "d01", "t", "字" * 40, 1.0)
    assert works.listing(c, None)[0]["opening"] == "字" * 30 + "…"
