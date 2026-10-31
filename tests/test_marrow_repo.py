"""marrow.repo:冪等寫入與 current 指標。repo 不 commit,transaction 由呼叫者擁有。"""
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
        "external_id", "seq", "role", "text", "ts", "anchors"}


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


def test_discussion_by_external_scoped_to_story(conn):
    s1 = repo.ensure_story(conn, "s1", None, 0)
    s2 = repo.ensure_story(conn, "s2", None, 0)
    d1 = repo.ensure_discussion(conn, s1, "x", "web", None, 0)
    repo.ensure_discussion(conn, s2, "x", "web", None, 0)
    assert repo.discussion_by_external(conn, s1, "x")["id"] == d1
    assert repo.discussion_by_external(conn, s1, "x")["story_id"] == s1
    assert repo.discussion_by_external(conn, s1, "nope") is None


def test_latest_job_picks_highest_id_of_that_version(conn):
    s, v = _story(conn)
    v2, _ = repo.add_source_version(conn, s, "乙", 1)
    assert repo.latest_job(conn, s, v) is None
    repo.create_job(conn, "critique", s, v, {}, 0)
    a = repo.create_job(conn, "critique", s, v2, {}, 1)
    b = repo.create_job(conn, "critique", s, v2, {}, 2)
    repo.set_job_state(conn, b, "done", 3)
    assert repo.latest_job(conn, s, v2)["id"] == b != a


def test_last_mode_returns_latest_assistant_mode(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "user", "a", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "assistant", "b", 1.0, "den", [], None, mode="slow")
    repo.add_utterance(conn, d, 2, "assistant", "c", 2.0, "den", [], None, mode="direct")
    assert repo.last_mode(conn, d) == "direct"
    assert repo.utterances(conn, d)[0]["mode"] is None


def test_last_mode_none_for_legacy_rows(conn):
    s, d = _disc(conn)
    repo.add_utterance(conn, d, 0, "assistant", "舊", 1.0, "den", [], None)
    assert repo.last_mode(conn, d) is None


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
    repo.add_utterance(conn, d, 1, "assistant", "b", 1.0, "den", [], None, mode="slow", character="hyena")
    repo.add_utterance(conn, d, 2, "assistant", "c", 2.0, "den", [], None, mode="direct", character="buffalo")
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
