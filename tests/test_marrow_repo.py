"""marrow.repo:冪等寫入與 current 指標。repo 不 commit,transaction 由呼叫者擁有。"""
import hashlib

import pytest

from marrow import repo


def _story(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    v, _ = repo.add_source_version(conn, s, "甲", 0)
    return s, v


def test_ensure_story_idempotent_and_updates_title(conn):
    a = repo.ensure_story(conn, "s1", None, 1.0)
    assert repo.ensure_story(conn, "s1", "標題", 2.0) == a
    assert repo.story_by_slug(conn, "s1")["title"] == "標題"
    repo.ensure_story(conn, "s1", None, 3.0)                 # None 不抹掉既有標題
    assert repo.story_by_slug(conn, "s1")["title"] == "標題"
    assert repo.story_by_slug(conn, "nope") is None


def test_source_versions_dedupe_and_number(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    assert repo.latest_source_version(conn, s) is None
    v1, c1 = repo.add_source_version(conn, s, "甲", 0)
    assert c1 and repo.add_source_version(conn, s, "甲", 1) == (v1, False)
    v2, c2 = repo.add_source_version(conn, s, "乙", 2)
    latest = repo.latest_source_version(conn, s)
    assert c2 and latest["n"] == 2 and latest["id"] == v2 and latest["text"] == "乙"


def test_artifact_dedupe_by_content_not_key_order(conn):
    s, v = _story(conn)
    a, c = repo.add_artifact(conn, s, v, "analysis", 1, {"a": 1, "b": 2}, {"tier": "A"}, 0)
    assert c and repo.add_artifact(conn, s, v, "analysis", 1, {"b": 2, "a": 1}, {}, 1) == (a, False)


def test_same_body_different_kind_is_distinct(conn):
    s, v = _story(conn)
    a, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"x": 1}, {}, 0)
    b, c = repo.add_artifact(conn, s, v, "feedback", 1, {"x": 1}, {}, 0)
    assert c and a != b


def test_current_pointer_moves(conn):
    s, v = _story(conn)
    assert repo.current_artifact(conn, s, "analysis") is None
    a1, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"x": 1}, {"tier": "A"}, 0)
    a2, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"x": 2}, {"tier": "A"}, 0)
    repo.set_current(conn, s, "analysis", a1)
    repo.set_current(conn, s, "analysis", a2)
    cur = repo.current_artifact(conn, s, "analysis")
    assert cur["id"] == a2 and cur["body"] == {"x": 2} and cur["provenance"] == {"tier": "A"}


def test_canonical_json_keeps_cjk_and_sorts():
    assert repo.canonical_json({"b": "字", "a": 1}) == '{"a": 1, "b": "字"}'
    assert len(repo.sha256_text("x")) == 64


# ── 討論 / 逐字 / 結論 / 收束 ──

def _disc(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    return s, repo.ensure_discussion(conn, s, "sess", "web", None, 0)


def test_utterance_seq_is_idempotency_key(conn):
    s, d = _disc(conn)
    assert repo.ensure_discussion(conn, s, "sess", "web", None, 9) == d
    assert repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", ["t1"], "fp")
    assert not repo.add_utterance(conn, d, 0, "user", "別的字", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "assistant", "答", 2.0, "den", [], None)
    us = repo.utterances(conn, d)
    assert [u["text"] for u in us] == ["問", "答"] and us[0]["anchors"] == ["t1"]


def test_close_discussion_only_moves_forward(conn):
    _, d = _disc(conn)
    repo.close_discussion(conn, d, 5.0)
    repo.close_discussion(conn, d, 3.0)
    assert conn.execute("SELECT ended_at FROM discussion WHERE id=?", (d,)).fetchone()[0] == 5.0


def test_conclusion_and_settlement_idempotent(conn):
    s, d = _disc(conn)
    args = (s, "c0001", d, "observation", "文", ["t1"], ["引"], {"session": "sess"}, 1.0, None)
    assert repo.add_conclusion(conn, *args) and not repo.add_conclusion(conn, *args)
    repo.add_conclusion(conn, s, "c0000", None, "question", "早", [], ["引"], {}, 0.5, None)
    cs = repo.conclusions(conn, s)
    assert [c["external_id"] for c in cs] == ["c0000", "c0001"]
    assert cs[1]["refs"] == ["t1"] and cs[1]["provenance"] == {"session": "sess"}
    assert repo.add_settlement(conn, d, 2.0, 1) and not repo.add_settlement(conn, d, 3.0, 1)


def test_reverted_edit_is_a_new_version(conn):                            # final review I2
    s = repo.ensure_story(conn, "s1", None, 0)
    repo.add_source_version(conn, s, "甲", 0)
    repo.add_source_version(conn, s, "乙", 1)
    v3, created = repo.add_source_version(conn, s, "甲", 2)
    latest = repo.latest_source_version(conn, s)
    assert created and latest["id"] == v3 and latest["n"] == 3 and latest["text"] == "甲"


def test_next_den_slug_empty_is_d01(conn):
    assert repo.next_den_slug(conn) == "d01"


def test_next_den_slug_ignores_s_prefix(conn):
    repo.ensure_story(conn, "s01", None, 0)
    repo.ensure_story(conn, "s07", None, 0)
    assert repo.next_den_slug(conn) == "d01"


def test_next_den_slug_increments(conn):
    repo.ensure_story(conn, "d01", None, 0)
    repo.ensure_story(conn, "d09", None, 0)
    repo.ensure_story(conn, "dx", None, 0)
    assert repo.next_den_slug(conn) == "d10"


def test_story_by_latest_sha_matches_latest_only(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    repo.add_source_version(conn, s, "甲", 0)
    repo.add_source_version(conn, s, "乙", 1)
    assert repo.story_by_latest_sha(conn, repo.sha256_text("甲")) is None
    assert repo.story_by_latest_sha(conn, repo.sha256_text("乙"))["id"] == s


def test_has_pending_jobs(conn):
    s, v = _story(conn)
    assert repo.has_pending_jobs(conn) is False
    j = repo.create_job(conn, "critique", s, v, {}, 0)
    assert repo.has_pending_jobs(conn) is True            # queued
    repo.set_job_state(conn, j, "running", 1)
    assert repo.has_pending_jobs(conn) is True
    for st in ("done", "failed", "cancelled", "paused"):
        repo.set_job_state(conn, j, st, 2)
        assert repo.has_pending_jobs(conn) is False


def test_active_job_only_queued_or_running_same_version(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    assert repo.active_job(conn, s, v) is None
    other = repo.create_job(conn, "critique", s, v2, {}, 0)       # 別的版本不算
    assert repo.active_job(conn, s, v) is None
    j = repo.create_job(conn, "critique", s, v, {}, 1)
    later = repo.create_job(conn, "critique", s, v, {}, 2)
    assert repo.active_job(conn, s, v)["id"] == j                 # 最舊的優先
    repo.set_job_state(conn, j, "running", 3)
    assert repo.active_job(conn, s, v)["id"] == j
    for st in ("done", "failed", "paused", "cancelled"):
        repo.set_job_state(conn, j, st, 4)
        repo.set_job_state(conn, later, st, 4)
        assert repo.active_job(conn, s, v) is None
    assert repo.active_job(conn, s, v2)["id"] == other


def test_list_jobs_joins_story_and_orders_newest_first(conn):
    s, v = _story(conn)
    repo.ensure_story(conn, "s1", "標題", 0)
    t = repo.ensure_story(conn, "s2", None, 0)
    tv, _ = repo.add_source_version(conn, t, "乙", 0)
    assert repo.list_jobs(conn, 10) == []
    a = repo.create_job(conn, "critique", s, v, {}, 1)
    b = repo.create_job(conn, "critique", t, tv, {}, 1)          # 同 updated_at → id 大的先
    c = repo.create_job(conn, "critique", s, v, {}, 2)
    repo.set_job_state(conn, a, "done", 5)
    rows = repo.list_jobs(conn, 10)
    assert [r["id"] for r in rows] == [a, c, b]
    assert (rows[0]["slug"], rows[0]["title"], rows[0]["state"]) == ("s1", "標題", "done")
    assert (rows[2]["slug"], rows[2]["title"]) == ("s2", None)
    assert rows[0]["params"] == {}                               # JSON 欄位已 decode
    assert all(r["is_latest_version"] is True for r in rows)
    repo.add_source_version(conn, s, "甲改", 6)                   # s1 改稿:舊版的 job 不再是最新版
    flags = {r["id"]: r["is_latest_version"] for r in repo.list_jobs(conn, 10)}
    assert flags == {a: False, c: False, b: True}
    assert [r["id"] for r in repo.list_jobs(conn, 2)] == [a, c]


def test_resumable_job_newest_paused_failed_cancelled_same_version(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    assert repo.resumable_job(conn, s, v) is None
    other = repo.create_job(conn, "critique", s, v2, {}, 0)
    repo.set_job_state(conn, other, "paused", 0)                  # 別的版本不算
    a = repo.create_job(conn, "critique", s, v, {}, 1)
    b = repo.create_job(conn, "critique", s, v, {}, 2)
    for st in ("queued", "running", "done"):
        repo.set_job_state(conn, a, st, 3)
        repo.set_job_state(conn, b, st, 3)
        assert repo.resumable_job(conn, s, v) is None
    for st in ("paused", "failed", "cancelled"):
        repo.set_job_state(conn, a, st, 4)
        assert repo.resumable_job(conn, s, v)["id"] == a
        repo.set_job_state(conn, b, st, 4)
        assert repo.resumable_job(conn, s, v)["id"] == b          # 最新的優先
        repo.set_job_state(conn, b, "done", 4)
    assert repo.resumable_job(conn, s, v2)["id"] == other


def test_has_newer_done_job_only_later_ids_same_version(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    j1 = repo.create_job(conn, "critique", s, v, {}, 0)
    assert repo.has_newer_done_job(conn, s, v, j1) is False
    other = repo.create_job(conn, "critique", s, v2, {}, 0)       # 別的版本不算
    repo.set_job_state(conn, other, "done", 1)
    assert repo.has_newer_done_job(conn, s, v, j1) is False
    j2 = repo.create_job(conn, "critique", s, v, {}, 0)
    for st in ("queued", "running", "paused", "failed", "cancelled"):
        repo.set_job_state(conn, j2, st, 2)
        assert repo.has_newer_done_job(conn, s, v, j1) is False
    repo.set_job_state(conn, j2, "done", 3)
    assert repo.has_newer_done_job(conn, s, v, j1) is True        # j1 被後來跑完的取代
    assert repo.has_newer_done_job(conn, s, v, j2) is False       # 自己不算
    j3 = repo.create_job(conn, "critique", s, v, {}, 4)
    assert repo.has_newer_done_job(conn, s, v, j3) is False       # 較早的 done 不擋重跑


# ── 列表用批次查詢 / 逐字 / 結論回填(切片 4a)──

def test_stories_sorted_by_slug(conn):
    repo.ensure_story(conn, "s2", "乙", 0)
    repo.ensure_story(conn, "s1", "甲", 0)
    assert [(s["slug"], s["title"]) for s in repo.stories(conn)] == [("s1", "甲"), ("s2", "乙")]


def test_current_artifacts_all_stories_in_one_query(conn):
    s, v = _story(conn)
    s2 = repo.ensure_story(conn, "s2", None, 0)
    v2, _ = repo.add_source_version(conn, s2, "乙", 0)
    a, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"k": 1}, {}, 0)
    f, _ = repo.add_artifact(conn, s, v, "feedback", 1, {"k": 2}, {}, 0)
    b, _ = repo.add_artifact(conn, s2, v2, "analysis", 1, {"k": 3}, {}, 0)
    for st, kind, aid in ((s, "analysis", a), (s, "feedback", f), (s2, "analysis", b)):
        repo.set_current(conn, st, kind, aid)
    got = {(c["story_id"], c["kind"]): c["artifact"] for c in repo.current_artifacts(conn)}
    assert set(got) == {(s, "analysis"), (s, "feedback"), (s2, "analysis")}
    assert got[(s, "analysis")]["id"] == a and got[(s, "analysis")]["body"] == {"k": 1}
    assert "cur_kind" not in got[(s, "analysis")] and got[(s2, "analysis")]["story_id"] == s2


def test_latest_jobs_picks_max_id_per_story(conn):
    s, v = _story(conn)
    s2 = repo.ensure_story(conn, "s2", None, 0)
    v2, _ = repo.add_source_version(conn, s2, "乙", 0)
    repo.create_job(conn, "critique", s, v, {}, 0)
    j2 = repo.create_job(conn, "critique", s, v, {}, 1)
    j3 = repo.create_job(conn, "critique", s2, v2, {}, 2)
    repo.ensure_story(conn, "s3", None, 0)                        # 無 job 的篇不在結果裡
    got = repo.latest_jobs(conn)
    assert {k: x["id"] for k, x in got.items()} == {s: j2, s2: j3}


def test_discussions_with_utterances_orders_by_ts_then_seq(conn):
    s, _ = _story(conn)
    other = repo.ensure_story(conn, "s2", None, 0)
    da = repo.ensure_discussion(conn, s, "A", "web", None, 0)
    db_ = repo.ensure_discussion(conn, s, "B", "web", None, 0)
    dz = repo.ensure_discussion(conn, other, "Z", "web", None, 0)
    repo.add_utterance(conn, da, 0, "user", "a0", 1.0, "den", ["t1"], None)
    repo.add_utterance(conn, da, 1, "assistant", "a1", 3.0, "den", [], None)
    repo.add_utterance(conn, db_, 0, "user", "b0", 2.0, "den", [], None)
    repo.add_utterance(conn, dz, 0, "user", "z0", 0.5, "den", [], None)
    got = repo.discussions_with_utterances(conn, s)
    assert [(u["external_id"], u["text"]) for u in got] == [("A", "a0"), ("B", "b0"), ("A", "a1")]
    assert got[0]["anchors"] == ["t1"] and set(got[0]) == {
        "external_id", "seq", "role", "text", "ts", "anchors", "character", "quotes",
        "analysis_fp", "archived_at"}


def test_discussions_with_utterances_carries_character_quotes(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None, quotes=["原句"])
    repo.add_utterance(conn, d, 1, "assistant", "答", 2.0, "den", [], None, character="hyena")
    u, a = repo.discussions_with_utterances(conn, s)
    assert u["quotes"] == ["原句"]
    assert (a["character"], a["quotes"]) == ("hyena", None)


def test_recent_discussions_orders_by_last_activity_and_limits(conn):
    s, _ = _story(conn)
    s2 = repo.ensure_story(conn, "s2", "乙", 0)
    a = repo.ensure_discussion(conn, s, "A", "web", None, 1.0)
    b = repo.ensure_discussion(conn, s2, "B", "web", None, 2.0)
    repo.ensure_discussion(conn, s, "empty", "web", None, 3.0)           # 沒發言的局不列
    repo.add_utterance(conn, a, 0, "user", "問", 1.0, "den", [], None)
    repo.add_utterance(conn, a, 1, "assistant", "答" * 80, 5.0, "den", [], "fpA", character="hyena")
    repo.add_utterance(conn, a, 2, "user", "再問", 6.0, "den", [], None)
    repo.add_utterance(conn, b, 0, "user", "問", 2.0, "den", [], None)
    repo.add_utterance(conn, b, 1, "assistant", "乙答", 4.0, "den", [], None, character="buffalo")
    got = repo.recent_discussions(conn, 10)
    assert [g["external_id"] for g in got] == ["A", "B"]
    assert got[0] == {"external_id": "A", "slug": "s1", "title": None, "custom_title": None, "started_at": 1.0,
                      "last_at": 6.0, "turns": 1, "character": "hyena",
                      "preview": "答" * 80, "fp": "fpA", "story_id": s}
    assert (got[1]["title"], got[1]["turns"], got[1]["preview"]) == ("乙", 1, "乙答")
    assert [g["external_id"] for g in repo.recent_discussions(conn, 1)] == ["A"]


def test_analysis_versions_maps_fp_to_source_version_n(conn):
    s, v1 = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 7.0)
    a1, _ = repo.add_artifact(conn, s, v1, "analysis", 1, {"t": 1}, {}, 1.0)
    a2, _ = repo.add_artifact(conn, s, v2, "analysis", 1, {"t": 2}, {}, 8.0)
    repo.add_artifact(conn, s, v2, "notes", 1, {"t": 3}, {}, 8.0)          # 非 analysis 不算
    got = repo.analysis_versions(conn, s)
    assert got == {repo.artifact(conn, a1)["sha256"]: 1, repo.artifact(conn, a2)["sha256"]: 2}


def test_artifact_versions_by_kind(conn):
    s, v1 = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 7.0)
    repo.add_artifact(conn, s, v1, "analysis", 1, {"t": 1}, {}, 1.0)
    repo.add_artifact(conn, s, v1, "notes", 1, {"t": 2}, {}, 1.0)
    repo.add_artifact(conn, s, v2, "analysis", 1, {"t": 3}, {}, 8.0)
    assert repo.artifact_versions(conn, s, "analysis") == {1, 2}
    assert repo.artifact_versions(conn, s, "notes") == {1}
    assert repo.artifact_versions(conn, s, "feedback") == set()



def test_add_utterance_stores_usage_json(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "assistant", "B", 1.0, "den", [], "fp",
                       usage={"output": 3, "duration_ms": 900})
    assert repo.utterances(conn, d)[0]["usage"] == {"output": 3, "duration_ms": 900}


def test_add_utterance_usage_defaults_null(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None)
    assert repo.utterances(conn, d)[0]["usage"] is None
    assert conn.execute("SELECT usage FROM utterance WHERE discussion_id = ?",
                        (d,)).fetchone()[0] is None      # 真的是 SQL NULL,不是字串 "null"


def test_latest_job_picks_highest_id_of_that_version(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    assert repo.latest_job(conn, s, v) is None
    repo.create_job(conn, "critique", s, v, {}, 0)
    a = repo.create_job(conn, "critique", s, v2, {}, 1)
    b = repo.create_job(conn, "critique", s, v2, {}, 2)
    repo.set_job_state(conn, b, "done", 3)
    assert repo.latest_job(conn, s, v2)["id"] == b != a




def test_works_latest_version_and_last_talk(conn):
    a = repo.ensure_story(conn, "a", "甲篇", 0)
    repo.add_source_version(conn, a, "第一版", 1)
    repo.add_source_version(conn, a, "第二版", 2)
    for ext, end in (("x", 10.0), ("y", 20.0)):
        d = repo.ensure_discussion(conn, a, ext, "mcp", None, 5.0)
        repo.close_discussion(conn, d, end)
    b = repo.ensure_story(conn, "b", None, 0)
    repo.add_source_version(conn, b, "乙", 3)
    rows = {r["slug"]: r for r in repo.works(conn)}
    assert rows["a"]["latest_n"] == 2 and rows["a"]["latest_text"] == "第二版"
    assert rows["a"]["submitted_at"] == 2 and rows["a"]["talked_at"] == 20
    assert rows["a"]["title"] == "甲篇" and rows["a"]["id"] == a
    assert rows["b"]["talked_at"] is None and rows["b"]["latest_sv_id"]


def test_active_jobs_of_story(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    ids = {}
    for st, ver in (("queued", v2), ("running", v), ("done", v), ("paused", v2)):
        ids[st] = repo.create_job(conn, "critique", s, ver, {}, 0)
        repo.set_job_state(conn, ids[st], st, 1)
    assert [j["id"] for j in repo.active_jobs_of_story(conn, s)] == [ids["queued"], ids["running"]]


def test_last_character_and_stored_on_utterance(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "assistant", "舊", 1.0, "den", [], None)
    assert repo.last_character(conn, d) is None
    repo.add_utterance(conn, d, 1, "assistant", "b", 1.0, "den", [], None, character="hyena")
    repo.add_utterance(conn, d, 2, "assistant", "c", 2.0, "den", [], None, character="buffalo")
    assert repo.last_character(conn, d) == "buffalo"
    assert repo.utterances(conn, d)[0]["character"] is None


def test_migration_0007_adds_character(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(utterance)")}
    assert "character" in cols


def test_migration_0008_adds_quotes(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(utterance)")}
    assert "quotes" in cols


def test_add_utterance_stores_quotes(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "user", "a", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "user", "b", 2.0, "den", [], None, quotes=["甲", "乙"])
    rows = repo.utterances(conn, d)
    assert rows[0]["quotes"] is None and rows[1]["quotes"] == ["甲", "乙"]



def test_source_versions_and_by_n(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    for i, t in enumerate(["甲", "乙", "丙"]):
        repo.add_source_version(conn, s, t, float(i))
    assert [(v["n"], v["text"]) for v in repo.source_versions(conn, s)] == [(1, "甲"), (2, "乙"), (3, "丙")]
    assert repo.source_version_by_n(conn, s, 2)["text"] == "乙"
    assert repo.source_version_by_n(conn, s, 9) is None


def test_recent_discussions_legacy_filter_applies_before_limit(conn):
    s, _ = _story(conn)
    new = repo.ensure_discussion(conn, s, "new", "web", None, 1.0)
    repo.add_utterance(conn, new, 0, "assistant", "答", 1.0, "den", [], None, character="hyena")
    for i, ext in enumerate(["old1", "old2"]):   # 舊局:assistant 沒記 character(或只有 user)
        d = repo.ensure_discussion(conn, s, ext, "web", None, 2.0 + i)
        repo.add_utterance(conn, d, 0, "user", "問", 2.0 + i, "den", [], None)
        repo.add_utterance(conn, d, 1, "assistant", "舊答", 3.0 + i, "den", [], None)
    assert [g["external_id"] for g in repo.recent_discussions(conn, 1)] == ["new"]
    assert [g["external_id"] for g in repo.recent_discussions(conn, 1, legacy=True)] == ["old2"]
    assert [g["external_id"] for g in repo.recent_discussions(conn, 5, legacy=True)] == ["old2", "old1"]


def test_character_versions_and_latest(conn):
    assert repo.latest_character(conn, "x") is None and repo.latest_characters(conn) == []
    repo.add_character(conn, "x", "builtin", 1.0)
    assert repo.latest_character(conn, "x") is None
    assert repo.add_character_version(conn, "x", {"a": 1}, 1.0) == 1
    assert repo.add_character_version(conn, "x", {"a": 2}, 2.0) == 2
    repo.add_character(conn, "w", "imported", 3.0)
    repo.add_character_version(conn, "w", {"b": 1}, 3.0)
    x = repo.latest_character(conn, "x")
    assert (x["id"], x["origin"], x["archived_at"], x["n"], x["card"]) == ("x", "builtin", None, 2, {"a": 2})
    assert x["sha256"] == hashlib.sha256(repo.canonical_json({"a": 2}).encode()).hexdigest()
    assert [(r["id"], r["n"]) for r in repo.latest_characters(conn)] == [("x", 2), ("w", 1)]


def test_archive_keeps_first_time_and_unarchive_clears(conn):
    repo.add_character(conn, "x", "imported", 1.0)
    repo.add_character_version(conn, "x", {}, 1.0)
    repo.archive_character(conn, "x", 2.0)
    repo.archive_character(conn, "x", 3.0)
    assert repo.latest_character(conn, "x")["archived_at"] == 2.0
    repo.unarchive_character(conn, "x")
    assert repo.latest_character(conn, "x")["archived_at"] is None


def test_setting_upsert(conn):
    assert repo.get_setting(conn, "k") is None
    repo.set_setting(conn, "k", "a")
    repo.set_setting(conn, "k", "b")
    assert repo.get_setting(conn, "k") == "b"


def test_discussion_without_story(conn):
    d = repo.ensure_discussion(conn, None, "abc", "web", None, 1.0)
    row = repo.discussion_by_session(conn, "abc")
    assert (row["id"], row["story_id"], row["slug"]) == (d, None, None)
    assert repo.discussion_by_session(conn, "nope") is None


def test_session_id_is_global(conn):
    s, d = _disc(conn)
    other = repo.ensure_story(conn, "s2", None, 0)
    with pytest.raises(ValueError):
        repo.ensure_discussion(conn, other, "sess", "web", None, 1.0)
    assert repo.ensure_discussion(conn, s, "sess", "web", None, 2.0) == d
    assert conn.execute("SELECT COUNT(*) FROM discussion").fetchone()[0] == 1
    assert repo.discussion_by_session(conn, "sess")["slug"] == "s1"


def test_bind_only_unbound(conn):
    a = repo.ensure_story(conn, "a", None, 0)
    b = repo.ensure_story(conn, "b", None, 0)
    d = repo.ensure_discussion(conn, None, "x", "web", None, 0)
    repo.bind_discussion(conn, d, a)
    repo.bind_discussion(conn, d, b)
    assert repo.discussion_by_session(conn, "x")["story_id"] == a


def test_attachments_numbered_in_order(conn):
    d = repo.ensure_discussion(conn, None, "x", "web", None, 0)
    assert repo.add_attachment(conn, d, 0, "海", "浪", 1.0) == 1
    assert repo.add_attachment(conn, d, 3, "山", "石", 2.0) == 2
    got = repo.attachments(conn, d)
    assert [(a["n"], a["seq"], a["name"], a["text"], a["source_version_id"]) for a in got] == [
        (1, 0, "海", "浪", None), (2, 3, "山", "石", None)]
    assert got[0]["sha256"] == repo.sha256_text("浪") and got[1]["added_at"] == 2.0


def test_adopt_sets_source_version(conn):
    s, v = _story(conn)
    d = repo.ensure_discussion(conn, None, "x", "web", None, 0)
    repo.add_attachment(conn, d, 0, "海", "甲", 1.0)
    repo.add_attachment(conn, d, 1, "山", "乙", 1.0)
    repo.adopt_attachment(conn, d, 1, v)
    assert [a["source_version_id"] for a in repo.attachments(conn, d)] == [v, None]


def test_recent_includes_storyless_and_skips_marks(conn):
    d = repo.ensure_discussion(conn, None, "free", "web", None, 1.0)
    repo.add_utterance(conn, d, 0, "assistant", "嗨", 1.0, "den", [], None, character="hyena")
    repo.add_utterance(conn, d, 1, "compact", "摘要", 2.0, "den", [], None)
    repo.add_utterance(conn, d, 2, "clear", "", 3.0, "den", [], None)
    got = repo.recent_discussions(conn, 5)
    assert [(g["external_id"], g["slug"], g["title"], g["turns"], g["preview"]) for g in got] == [
        ("free", None, None, 1, "嗨")]


def test_story_transcript_skips_marks(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "compact", "摘要", 2.0, "den", [], None)
    repo.add_utterance(conn, d, 2, "clear", "", 3.0, "den", [], None)
    repo.add_utterance(conn, d, 3, "assistant", "答", 4.0, "den", [], None)
    assert [u["text"] for u in repo.discussions_with_utterances(conn, s)] == ["問", "答"]


def test_activity_times_ignores_storyless(conn):
    s, d = _disc(conn)
    free = repo.ensure_discussion(conn, None, "free", "web", None, 0)
    repo.add_utterance(conn, d, 0, "assistant", "答", 4.0, "den", [], None)
    repo.add_utterance(conn, free, 0, "assistant", "答", 9.0, "den", [], None)
    assert repo.activity_times(conn) == {s: 4.0}


def test_rename_archive_and_archived_stories(conn):
    s, _ = _story(conn)
    other = repo.ensure_story(conn, "s2", None, 0)
    repo.ensure_discussion(conn, s, "A", "web", None, 1.0)
    repo.rename_story(conn, s, "新名")
    assert repo.story(conn, s)["custom_title"] == "新名"
    assert repo.archived_stories(conn) == []
    repo.archive_story(conn, s, 5.0)
    repo.archive_story(conn, s, 9.0)                                    # 再封存不改第一次的時間
    repo.archive_story(conn, other, 7.0)
    got = repo.archived_stories(conn)
    assert [(g["slug"], g["archived_at"], g["sessions"]) for g in got] == [("s2", 7.0, 0), ("s1", 5.0, 1)]
    assert got[1]["custom_title"] == "新名"
    repo.unarchive_story(conn, s)
    assert [g["slug"] for g in repo.archived_stories(conn)] == ["s2"]


def test_archived_story_hides_its_sessions_from_recent(conn):
    s, _ = _story(conn)
    a = repo.ensure_discussion(conn, s, "A", "web", None, 1.0)
    free = repo.ensure_discussion(conn, None, "F", "web", None, 1.0)
    for d in (a, free):
        repo.add_utterance(conn, d, 0, "assistant", "答", 2.0, "den", [], None, character="hyena")
    repo.archive_story(conn, s, 3.0)
    assert [g["external_id"] for g in repo.recent_discussions(conn, 10)] == ["F"]
    assert repo.discussion_by_session(conn, "A")["archived_at"] is None


def test_delete_story_removes_everything_of_it_and_nothing_else(conn):
    s, v = _story(conn)
    keep, kv = repo.ensure_story(conn, "s2", None, 0), None
    kv, _ = repo.add_source_version(conn, keep, "乙", 0)
    art, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"a": 1}, {}, 0)
    repo.set_current(conn, s, "analysis", art)
    job = repo.create_job(conn, "critique", s, v, {}, 0)
    repo.add_attempt(conn, job, "analyst", 1, runner="cli", model=None, cli_version=None, outcome="ok",
                     raw_output=None, parsed=None, gate_verdict=None, tokens=None, duration_ms=None,
                     artifact_id=art, now=0)
    d = repo.ensure_discussion(conn, s, "A", "web", None, 1.0)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None)
    repo.add_memory(conn, "work", "這篇的事", 1.0, story_id=s)
    author = repo.add_memory(conn, "author", "寫短句", 1.0, quote="問", discussion_id=d, seq=0)
    repo.add_conclusion(conn, s, "c1", d, "k", "t", [], [], {}, 0, None)
    free = repo.ensure_discussion(conn, None, "F", "web", None, 1.0)
    repo.add_utterance(conn, free, 0, "user", "稿", 1.0, "den", [], None)
    repo.add_attachment(conn, free, 0, "稿", "甲", 1.0)
    repo.adopt_attachment(conn, free, 1, v)
    kd = repo.ensure_discussion(conn, keep, "K", "web", None, 1.0)
    repo.add_memory(conn, "work", "那篇的事", 1.0, story_id=keep)

    repo.delete_story(conn, s)

    assert repo.story(conn, s) is None and repo.discussion_by_session(conn, "A") is None
    for table in ("source_version", "artifact", "current_artifact", "job", "conclusion"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE story_id = ?", (s,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM attempt").fetchone()[0] == 0
    assert [r["text"] for r in conn.execute("SELECT text FROM memory ORDER BY id")] == ["寫短句", "那篇的事"]
    assert conn.execute("SELECT discussion_id FROM memory WHERE id = ?", (author,)).fetchone()[0] is None
    assert [a["source_version_id"] for a in repo.attachments(conn, free)] == [None]
    assert repo.discussion_by_session(conn, "K")["id"] == kd
    assert repo.latest_source_version(conn, keep)["id"] == kv
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_artifact_at_returns_latest_for_that_version(conn):
    sid = repo.ensure_story(conn, "s", "t", 0)
    v1, _ = repo.add_source_version(conn, sid, "一", 1)
    v2, _ = repo.add_source_version(conn, sid, "二", 2)
    repo.add_artifact(conn, sid, v1, "notes", 1, {"n": "old"}, {}, 3)
    repo.add_artifact(conn, sid, v1, "notes", 1, {"n": "new"}, {}, 4)
    assert repo.artifact_at(conn, sid, "notes", v1)["body"] == {"n": "new"}
    assert repo.artifact_at(conn, sid, "notes", v2) is None


# ── digest ──

def _talked_disc(conn, s, sid, end, users=2):
    d = repo.ensure_discussion(conn, s, sid, "web", None, 0)
    seq = 0
    for i in range(users):
        repo.add_utterance(conn, d, seq, "user", f"問{i}", 1.0, "den", [], None)
        repo.add_utterance(conn, d, seq + 1, "assistant", f"答{i}", 1.0, "den", [], None)
        seq += 2
    repo.close_discussion(conn, d, end)
    return d


def test_add_digest_supersedes(conn):
    s, d = _disc(conn)
    a = repo.add_digest(conn, d, "一", 3, 1.0)
    b = repo.add_digest(conn, d, "二", 5, 2.0, root_id=a, usage={"model": "m"})
    cur = repo.current_digest(conn, d)
    assert (cur["id"], cur["root_id"], cur["text"], cur["through_seq"], cur["edited"]) == (b, a, "二", 5, 0)
    old = repo.digest_by_id(conn, a)
    assert old["invalidated_at"] == 2.0 and old["root_id"] == a
    assert (old["session"], old["at"]) == ("sess", None)
    e = repo.add_digest(conn, d, "改", 5, 3.0, root_id=a, edited=True)
    assert repo.current_digest(conn, d)["edited"] == 1 and repo.digest_by_id(conn, e)["root_id"] == a
    assert repo.current_digest(conn, 999) is None and repo.digest_by_id(conn, 999) is None


def test_prior_discussions_filters(conn):
    s, _ = _disc(conn)
    a = _talked_disc(conn, s, "A", 10.0)
    b = _talked_disc(conn, s, "B", 30.0)
    c = _talked_disc(conn, s, "C", 20.0)
    _talked_disc(conn, s, "one", 40.0, users=1)
    arch = _talked_disc(conn, s, "arch", 50.0)
    repo.archive_discussion(conn, arch, 51.0)
    new = _talked_disc(conn, s, "new", 60.0)
    _talked_disc(conn, repo.ensure_story(conn, "s2", None, 0), "other", 70.0)
    got = repo.prior_discussions(conn, s, exclude=new, limit=3, min_user_turns=2)
    assert [g["id"] for g in got] == [b, c, a]
    assert got[0]["external_id"] == "B" and got[0]["ended_at"] == 30.0
    assert [g["id"] for g in repo.prior_discussions(conn, s, exclude=None, limit=1, min_user_turns=2)] == [new]


def test_threads_roundtrip_and_ended(conn):
    s, d = _disc(conn)
    root = repo.add_digest(conn, d, "一", 3, 1.0)
    t1, t2 = repo.replace_threads(conn, root, [
        {"text": "甲", "quote": "問一問", "source_quote": None, "ended_at": None},
        {"text": "乙", "quote": "答一答", "source_quote": "海", "ended_at": 5.0}], 1.0)
    assert [(t["id"], t["text"], t["source_quote"], t["ended_at"]) for t in repo.threads_of(conn, root)] == \
        [(t1, "甲", None, None), (t2, "乙", "海", 5.0)]
    repo.set_thread_ended(conn, t1, 7.0)
    assert repo.thread_by_id(conn, t1)["ended_at"] == 7.0
    assert repo.thread_by_id(conn, t1)["session"] == "sess"
    repo.set_thread_ended(conn, t1, None)
    assert repo.thread_by_id(conn, t1)["ended_at"] is None
    (t3,) = repo.replace_threads(conn, root, [{"text": "丙", "quote": "問一問", "source_quote": None,
                                                "ended_at": None}], 2.0)
    assert [t["id"] for t in repo.threads_of(conn, root)] == [t3]
    assert repo.thread_by_id(conn, t1)["replaced_at"] == 2.0
    assert repo.thread_by_id(conn, 999) is None


def test_talked_marks(conn):
    s, d = _disc(conn)
    other = repo.ensure_discussion(conn, s, "o", "web", None, 0)
    root = repo.add_digest(conn, d, "一", 3, 1.0)
    (t,) = repo.replace_threads(conn, root, [{"text": "甲", "quote": "問一問", "source_quote": None,
                                               "ended_at": None}], 1.0)
    repo.mark_talked(conn, t, other)
    repo.mark_talked(conn, t, other)
    assert repo.talked_in(conn, other) == {t} and repo.talked_in(conn, d) == set()
    repo.unmark_talked(conn, t, other)
    assert repo.talked_in(conn, other) == set()


def test_digest_failure_upsert(conn):
    s, d = _disc(conn)
    assert repo.digest_failed_seq(conn, d) is None
    repo.record_digest_failure(conn, d, 3, 1.0)
    repo.record_digest_failure(conn, d, 5, 2.0)
    assert repo.digest_failed_seq(conn, d) == 5


def _digest_web(conn, s):
    old = _talked_disc(conn, s, "old", 1.0)
    new = _talked_disc(conn, s, "new", 2.0)
    root = repo.add_digest(conn, old, "一", 3, 1.0)
    repo.add_digest(conn, old, "二", 3, 2.0, root_id=root)
    (t,) = repo.replace_threads(conn, root, [{"text": "甲", "quote": "問一問", "source_quote": None,
                                               "ended_at": None}], 1.0)
    repo.mark_talked(conn, t, new)
    nr = repo.add_digest(conn, new, "新", 3, 3.0)
    (nt,) = repo.replace_threads(conn, nr, [{"text": "乙", "quote": "問一問", "source_quote": None,
                                              "ended_at": None}], 3.0)
    repo.mark_talked(conn, nt, old)
    repo.record_digest_failure(conn, old, 3, 1.0)
    return old, new


def test_delete_discussion_removes_digests(conn):
    s, _ = _disc(conn)
    old, new = _digest_web(conn, s)
    repo.delete_discussion(conn, old)
    for table in ("digest", "digest_failure"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE discussion_id = ?", (old,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM thread_talked").fetchone()[0] == 0
    assert [t["text"] for t in conn.execute("SELECT text FROM digest_thread")] == ["乙"]
    assert repo.current_digest(conn, new)["text"] == "新"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_delete_story_removes_digests(conn):
    s, _ = _disc(conn)
    _digest_web(conn, s)
    repo.delete_story(conn, s)
    for table in ("digest", "digest_thread", "thread_talked", "digest_failure"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


# ── memory candidate ──

def test_candidate_roundtrip(conn):
    s, _ = _disc(conn)
    d = _talked_disc(conn, s, "c1", 1.0)
    cid = repo.add_candidate(conn, d, 0, "我想讓結尾留白", "想讓結尾留白", "work", 5.0)
    c = repo.candidate(conn, cid)
    assert (c["session"], c["story_id"], c["seq"], c["scope"], c["resolution"]) == ("c1", s, 0, "work", None)
    assert [x["id"] for x in repo.candidates_of_story(conn, s)] == [cid]
    assert repo.candidate(conn, 999) is None


def test_pending_candidates_filters_resolved_and_old(conn):
    s, _ = _disc(conn)
    d = _talked_disc(conn, s, "c1", 1.0)
    skipped = repo.add_candidate(conn, d, 0, "引一", "一", "author", 10.0)
    repo.resolve_candidate(conn, skipped, "skipped", 11.0)
    repo.add_candidate(conn, d, 0, "引二", "二", "author", 1.0)
    live = repo.add_candidate(conn, d, 0, "引三", "三", "author", 10.0)
    (row,) = repo.pending_candidates(conn, 5.0)
    assert (row["id"], row["session"], row["slug"]) == (live, "c1", "s1")
    repo.archive_story(conn, s, 20.0)
    assert repo.pending_candidates(conn, 5.0) == []


def test_resolve_candidate_back_to_pending(conn):
    s, _ = _disc(conn)
    d = _talked_disc(conn, s, "c1", 1.0)
    cid = repo.add_candidate(conn, d, 0, "引", "一", "author", 1.0)
    mid = repo.add_memory(conn, "author", "一", 2.0)
    repo.resolve_candidate(conn, cid, "saved", 2.0, mid)
    assert (repo.candidate(conn, cid)["resolution"], repo.candidate(conn, cid)["memory_id"]) == ("saved", mid)
    repo.resolve_candidate(conn, cid, None, None, None)
    c = repo.candidate(conn, cid)
    assert (c["resolution"], c["resolved_at"], c["memory_id"]) == (None, None, None)


def test_delete_discussion_drops_candidates(conn):
    s, _ = _disc(conn)
    d = _talked_disc(conn, s, "c1", 1.0)
    repo.add_digest(conn, d, "一", 3, 1.0)
    repo.add_candidate(conn, d, 0, "引", "一", "author", 1.0)
    repo.delete_story(conn, s)
    assert conn.execute("SELECT COUNT(*) FROM memory_candidate").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_candidates_of_scope(conn):
    s, _ = _disc(conn)
    d = _talked_disc(conn, s, "c1", 1.0)
    a = repo.add_candidate(conn, d, 0, "引", "一", "author", 1.0)
    repo.add_candidate(conn, d, 0, "引", "二", "work", 1.0)
    assert [c["id"] for c in repo.candidates_of_scope(conn, "author")] == [a]
