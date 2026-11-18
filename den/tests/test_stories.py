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
    assert set(out) == {"slug", "title", "source", "analysis", "progress", "seeds", "memory", "attachments",
                        "version", "versions", "compare", "old_sources"}
    assert isinstance(out["analysis"], dict) and out["progress"] == "none"


def _add_notes(conn, story_id, version_id):
    body = {"slug": "x", "read": "讀到", "one_line": "一句", "points": [
        {"kind": k, "title": "標題", "quotes": [f"{k}句"], "refs": None, "body": "內文", "question": "問"}
        for k in ("moved", "confused", "wondering", "opinion")]}
    with conn:
        a, _ = repo.add_artifact(conn, story_id, version_id, "notes", 1, body, {}, 5.0)
        repo.set_current(conn, story_id, "notes", a)


def test_companion_context_seeds_carry_only_kind_and_quotes_and_never_opinion(conn):
    st = repo.story_by_slug(conn, "mini")
    _add_notes(conn, st["id"], repo.latest_source_version(conn, st["id"])["id"])
    assert stories.companion_context(conn, "mini")["seeds"] == [
        {"kind": "moved", "quotes": ["moved句"]},
        {"kind": "confused", "quotes": ["confused句"]},
        {"kind": "wondering", "quotes": ["wondering句"]}]


def test_old_seeds_not_in_new_text_are_not_carried(conn):
    st = repo.story_by_slug(conn, "mini")
    _add_notes(conn, st["id"], repo.latest_source_version(conn, st["id"])["id"])
    _ingest(conn, "改過的新稿。", slug="mini")
    assert stories.companion_context(conn, "mini")["seeds"] == []


def test_companion_context_no_notes_no_seeds(conn):
    assert stories.companion_context(conn, "mini")["seeds"] == []


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
    from den.companion import assemble
    st = repo.story_by_slug(conn, "mini")
    ana = repo.current_artifact(conn, st["id"], "analysis")
    notes = {"slug": "mini", "read": "筆記讀法甲乙", "one_line": "筆記一句丙丁", "points": [
        {"kind": "confused", "title": "筆記標題戊己", "quotes": ["像在等誰"], "refs": None,
         "body": "筆記內文庚辛", "question": None}]}
    with conn:
        nid, _ = repo.add_artifact(conn, st["id"], ana["source_version_id"], "notes", 1, notes, {}, 9.0)
        repo.set_current(conn, st["id"], "notes", nid)
    ctx = stories.companion_context(conn, "mini")
    text = repr(ctx) + assemble(ctx, {"id": "buffalo", "voice": "", "reading": "讀法"}).text
    for marker in ("筆記讀法甲乙", "筆記一句丙丁", "筆記標題戊己", "筆記內文庚辛"):
        assert marker not in text


def test_companion_context_unknown_slug(conn):
    with pytest.raises(LookupError):
        stories.companion_context(conn, "nope")


def test_companion_context_loads_only_this_works_memory(conn):
    mini = repo.story_by_slug(conn, "mini")["id"]
    other = repo.ensure_story(conn, "other", None, 0)
    repo.add_memory(conn, "author", "共用", 1.0)
    repo.add_memory(conn, "work", "這篇", 1.0, story_id=mini)
    repo.add_memory(conn, "work", "別篇", 1.0, story_id=other)
    repo.add_memory(conn, "character", "印象", 1.0, character="hyena")
    gone = repo.add_memory(conn, "work", "封存", 1.0, story_id=mini)
    repo.invalidate_memory(conn, gone, 2.0)
    assert stories.companion_context(conn, "mini")["memory"] == {"author": ["共用"], "work": ["這篇"]}


def test_companion_context_no_memory_is_empty_lists(conn):
    assert stories.companion_context(conn, "mini")["memory"] == {"author": [], "work": []}


def test_companion_context_without_story(conn):
    repo.add_memory(conn, "author", "共用", 1.0)
    out = stories.companion_context(conn, None)
    assert out == {"slug": None, "title": None, "source": "", "analysis": None, "progress": "none",
                   "seeds": [], "memory": {"author": ["共用"], "work": []}, "attachments": [],
                   "version": None, "versions": [], "compare": None, "old_sources": []}


def test_adopted_attachment_not_in_context(conn):
    d = repo.ensure_discussion(conn, None, "free", "web", None, 0)
    repo.add_attachment(conn, d, 0, "海", "浪", 1.0)
    repo.add_attachment(conn, d, 1, "山", "石", 1.0)
    sv = repo.latest_source_version(conn, repo.story_by_slug(conn, "mini")["id"])["id"]
    repo.adopt_attachment(conn, d, 1, sv)
    out = stories.companion_context(conn, None, d)
    assert out["attachments"] == [{"n": 2, "seq": 1, "name": "山", "text": "石"}]


def test_sources_skips_empty_work_source():
    att = [{"n": 1, "seq": 0, "name": "海", "text": "浪"}]
    assert stories.sources({"source": "", "attachments": att, "old_sources": []}) == ["浪"]
    assert stories.sources({"source": "原文", "attachments": att, "old_sources": []}) == ["原文", "浪"]


def test_memory_load_without_story(conn):
    from den import memory
    repo.add_memory(conn, "author", "甲", 1.0)
    repo.add_memory(conn, "work", "別篇", 1.0, story_id=repo.story_by_slug(conn, "mini")["id"])
    assert memory.load(conn, None) == {"author": ["甲"], "work": []}


V1_TEXT = "甲。她看了很久。乙。門開著。"
V2_TEXT = "甲。乙。門開著。丙。"


def _notes(conn, sid, vid, points, current=False):
    aid, _ = repo.add_artifact(conn, sid, vid, "notes", 1, {"points": points}, {}, 9.0)
    if current:
        repo.set_current(conn, sid, "notes", aid)


V1_POINTS = [{"kind": "moved", "title": "t", "body": "b", "question": None, "quotes": ["門開著"]},
             {"kind": "confused", "title": "t", "body": "b", "question": "q", "quotes": ["她看了很久"]},
             {"kind": "opinion", "title": "t", "body": "b", "question": None, "quotes": ["甲"]}]
V2_POINTS = [{"kind": "wondering", "title": "t", "body": "b", "question": None, "quotes": ["丙"]}]


def _two(conn, noted=(), current_v2=False):
    with conn:
        sid = repo.ensure_story(conn, "d01", "標", 0)
        ids = [repo.add_source_version(conn, sid, t, float(i))[0] for i, t in enumerate((V1_TEXT, V2_TEXT), 1)]
        if 1 in noted:
            _notes(conn, sid, ids[0], V1_POINTS, current=True)
        if 2 in noted:
            _notes(conn, sid, ids[1], V2_POINTS, current=current_v2)
    return sid


def test_context_without_cmp_has_no_compare(conn):
    _two(conn)
    ctx = stories.companion_context(conn, "d01")
    assert ctx["compare"] is None and ctx["old_sources"] == []
    assert ctx["version"] == 2 and [v["n"] for v in ctx["versions"]] == [1, 2]
    assert ctx["versions"][0]["text"] == V1_TEXT and ctx["versions"][1]["created_at"] == 2.0


def test_context_cmp_builds_compare(conn):
    _two(conn, noted=(1,))
    ctx = stories.companion_context(conn, "d01", cmp=1)
    c = ctx["compare"]
    assert (c["old"], c["new"]) == (1, 2) and c["hunks"] == 2
    assert c["changes"] == [{"kind": "del", "old": "她看了很久。", "new": None},
                            {"kind": "ins", "old": None, "new": "丙。"}]
    assert (c["dels"], c["inss"]) == (6, 2) and c["heavy"] is False
    assert c["fates"] == [{"kind": "moved", "quote": "門開著", "fate": "kept"},
                          {"kind": "confused", "quote": "她看了很久", "fate": "gone"}]
    assert ctx["old_sources"] == [V1_TEXT]


def test_context_cmp_heavy_rewrite(conn):
    with conn:
        sid = repo.ensure_story(conn, "d01", "標", 0)
        repo.add_source_version(conn, sid, "甲。乙。", 1.0)
        repo.add_source_version(conn, sid, "丙。丁。", 2.0)
    c = stories.companion_context(conn, "d01", cmp=1)["compare"]
    assert c["heavy"] is True and c["fates"] == []


def test_context_cmp_unknown_or_not_older_raises(conn):
    _two(conn)
    for bad in (0, 2, 3):
        with pytest.raises(stories.UnknownVersion):
            stories.companion_context(conn, "d01", cmp=bad)


def test_context_cmp_ignored_without_work(conn):
    ctx = stories.companion_context(conn, None, cmp=1)
    assert ctx["compare"] is None and ctx["versions"] == [] and ctx["version"] is None


def test_interim_seeds_only_kept_and_in_new_text(conn):
    _two(conn, noted=(1,))
    assert stories.companion_context(conn, "d01")["seeds"] == [{"kind": "moved", "quotes": ["門開著"]}]


def test_interim_seeds_empty_without_older_notes(conn):
    _two(conn)
    assert stories.companion_context(conn, "d01")["seeds"] == []


def test_seeds_switch_back_once_latest_has_notes(conn):
    _two(conn, noted=(1, 2), current_v2=True)
    assert stories.companion_context(conn, "d01")["seeds"] == [{"kind": "wondering", "quotes": ["丙"]}]


def test_sources_include_old_sources(conn):
    _two(conn)
    assert stories.sources(stories.companion_context(conn, "d01", cmp=1)) == [V2_TEXT, V1_TEXT]
