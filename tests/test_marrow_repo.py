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
