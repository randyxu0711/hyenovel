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
