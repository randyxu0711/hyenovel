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
