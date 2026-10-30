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
    assert [r["slug"] for r in works.match(rows, "海")] == ["d01"]          # 標題完全相符優先
    assert [r["slug"] for r in works.match(rows[1:], "海")] == ["d03"]     # 全文深處的「海」不算


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
    (None, None, "none"), (LATEST, (LATEST, "running"), "notes-running"),
    (LATEST, (LATEST, "queued"), "notes-running"), (LATEST, (LATEST, "paused"), "notes-stopped"),
    (LATEST, (LATEST, "cancelled"), "notes-stopped"), (LATEST, (LATEST, "done"), "ready"),
    (LATEST, (OLD, "paused"), "ready")])
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


def test_listing_reviewer_stopped_is_visible(c):
    """分析已換上、reviewer 停住:不能只說「分析好了」,作者要看得到停住與原因。"""
    sid, vid = _story(c, "d01", "t", "x", 1.0)
    aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, {"title": "t"}, {}, 2.0)
    repo.set_current(c, sid, "analysis", aid)
    jid = repo.create_job(c, "critique", sid, vid, {}, 2.0)
    repo.set_job_state(c, jid, "paused", 3.0, step="reviewer", error_class="usage-limit")
    [w] = works.listing(c, None)
    assert (w["state"], w["job_id"], w["error_class"]) == ("notes-stopped", jid, "usage-limit")


def test_listing_opening_truncated(c):
    _story(c, "d01", "t", "字" * 40, 1.0)
    assert works.listing(c, None)[0]["opening"] == "字" * 30 + "…"


ANA = {"title": "燈", "slug": "a", "nodes": [{"id": "t1", "type": "theme", "label": "等待"}], "edges": []}
FB = {"slug": "a", "read": "讀到的", "key_points": [], "one_line": "一句話"}


NOTES = {"slug": "mini", "read": "一個人回到空屋。", "one_line": "燈等的是誰。", "points": [
    {"kind": "confused", "title": "燈為誰亮", "quotes": ["像在等誰"], "refs": ["k1"],
     "body": "以為有人要回來。", "question": "燈在等的是誰?"}]}


def _two_versions(c, analysed=1, feedback=False, notes=False):
    sid = repo.ensure_story(c, "a", "燈", 0)
    v1, _ = repo.add_source_version(c, sid, "第一版原文", 1)
    v2, _ = repo.add_source_version(c, sid, "第二版原文", 2)
    vid = {1: v1, 2: v2}[analysed]
    aid, _ = repo.add_artifact(c, sid, vid, "analysis", 1, ANA, {}, 3)
    repo.set_current(c, sid, "analysis", aid)
    if feedback:
        fid, _ = repo.add_artifact(c, sid, vid, "feedback", 1, FB, {}, 3)
        repo.set_current(c, sid, "feedback", fid)
    if notes:
        nid, _ = repo.add_artifact(c, sid, vid, "notes", 1, NOTES, {}, 3)
        repo.set_current(c, sid, "notes", nid)
    return sid


def test_read_source_is_latest_version(c):
    _two_versions(c)
    out = works.read_part(c, "a", "source")
    assert out.splitlines()[0] == "〈燈〉第 2 版原文:" and "第二版原文" in out and "第一版" not in out


def test_read_analysis_marks_older_version(c):
    _two_versions(c, analysed=1)
    out = works.read_part(c, "a", "analysis")
    assert out.splitlines()[0] == "(這是第 1 版的分析;最新是第 2 版,新版還沒有分析結果。)"
    assert "等待" in out and "---" not in out.splitlines()[1]


def test_read_analysis_latest_has_no_version_note(c):
    _two_versions(c, analysed=2)
    assert not works.read_part(c, "a", "analysis").startswith("(這是第")


def test_read_feedback_labelled_legacy(c):
    _two_versions(c, analysed=2, feedback=True)
    out = works.read_part(c, "a", "feedback")
    assert out.splitlines()[0] == "(舊版客觀回饋:舊的編輯評論流程產生,之後會由備課筆記取代。)"
    assert "一句話" in out


def test_read_feedback_older_version_noted(c):
    _two_versions(c, analysed=1, feedback=True)
    assert "這是第 1 版的回饋" in works.read_part(c, "a", "feedback")


def test_read_notes(c):
    _two_versions(c, analysed=2, notes=True)
    out = works.read_part(c, "a", "notes")
    assert out.startswith("# 備課筆記 —〈燈〉") and "[困惑] 燈為誰亮" in out and "---" not in out.splitlines()[0]


def test_read_notes_marks_older_version(c):
    _two_versions(c, analysed=1, notes=True)
    assert works.read_part(c, "a", "notes").splitlines()[0] == \
        "(這是第 1 版的筆記;最新是第 2 版,新版還沒有筆記。)"


def test_read_missing_parts(c):
    sid = repo.ensure_story(c, "b", None, 0)
    repo.add_source_version(c, sid, "x", 1)
    with pytest.raises(works.Missing) as e:
        works.read_part(c, "b", "analysis")
    assert e.value.reason == "not-analyzed"
    _two_versions(c)
    with pytest.raises(works.Missing) as e:
        works.read_part(c, "a", "feedback")
    assert e.value.reason == "no-feedback"
    with pytest.raises(works.Missing) as e:
        works.read_part(c, "a", "notes")
    assert e.value.reason == "no-notes"
    with pytest.raises(LookupError):
        works.read_part(c, "nope", "source")


def test_match_exact_title_beats_substring():
    rows = [_row("d01", "海", "她走到岸邊。"), _row("d02", "海-v2", "x"), _row("d03", "豆花", "海邊的早上。")]
    assert [r["slug"] for r in works.match(rows, "海")] == ["d01"]


def test_match_title_substring_beats_opening():
    rows = [_row("d02", "海-v2", "x"), _row("d03", "豆花", "海邊的早上。")]
    assert [r["slug"] for r in works.match(rows, "海")] == ["d02"]
