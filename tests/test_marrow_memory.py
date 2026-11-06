"""memory 表:一條記憶是一條 chain,改動都新增一列。"""
import sqlite3

import pytest

from marrow import repo


@pytest.fixture
def world(conn):
    s1 = repo.ensure_story(conn, "s1", "甲篇", 0)
    s2 = repo.ensure_story(conn, "s2", None, 0)
    d = repo.ensure_discussion(conn, s1, "sess", "/h", None, 0)
    repo.add_utterance(conn, d, 0, "user", "我不寫結局", 5.0, "web", [], None)
    return {"s1": s1, "s2": s2, "d": d}


def test_migration_adds_memory_table(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 11
    assert conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0] == 0


def test_scope_shape_is_enforced(conn, world):
    for scope, kw in (("work", {}), ("author", {"story_id": world["s1"]}), ("character", {}),
                      ("author", {"character": "hyena"}), ("nonsense", {})):
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_memory(conn, scope, "x", 1.0, **kw)


@pytest.mark.parametrize("partial", [{"quote": "x"}, {"discussion_id": 1}, {"seq": 0},
                                     {"quote": "x", "seq": 0}, {"discussion_id": 1, "seq": 0}])
def test_source_is_all_or_nothing(conn, world, partial):
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_memory(conn, "author", "x", 1.0, **partial)


def test_source_must_point_at_existing_utterance(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_memory(conn, "author", "x", 1.0, quote="x", discussion_id=99, seq=0)
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_memory(conn, "author", "x", 1.0, quote="x", discussion_id=world["d"], seq=7)


def test_valid_from_defaults_to_now_and_learned_at_is_always_now(conn, world):
    a = repo.memory(conn, repo.add_memory(conn, "author", "x", 3.0))
    b = repo.memory(conn, repo.add_memory(conn, "author", "y", 4.0, valid_from=2.0))
    assert (a["valid_from"], a["learned_at"]) == (3.0, 3.0)
    assert (b["valid_from"], b["learned_at"]) == (2.0, 4.0)
    assert repo.memory(conn, 9999) is None


def test_active_excludes_invalidated_and_other_works(conn, world):
    s1, s2 = world["s1"], world["s2"]
    a = repo.add_memory(conn, "work", "甲", 1.0, story_id=s1)
    b = repo.add_memory(conn, "work", "乙", 2.0, story_id=s1)
    c = repo.add_memory(conn, "work", "丙", 3.0, story_id=s1)
    repo.add_memory(conn, "work", "丁", 3.0, story_id=s2)
    repo.invalidate_memory(conn, a, 4.0)
    assert [m["id"] for m in repo.active_memories(conn, "work", s1)] == [b, c]


def test_active_author_scope_ignores_story_and_character_rows(conn, world):
    a = repo.add_memory(conn, "author", "共用", 1.0)
    repo.add_memory(conn, "work", "這篇", 1.0, story_id=world["s1"])
    repo.add_memory(conn, "character", "印象", 1.0, character="hyena")
    assert [m["id"] for m in repo.active_memories(conn, "author")] == [a]


def test_current_in_chain_finds_the_live_row(conn):
    a = repo.add_memory(conn, "author", "舊", 1.0)
    assert repo.current_in_chain(conn, a)["id"] == a
    repo.invalidate_memory(conn, a, 2.0)
    assert repo.current_in_chain(conn, a) is None
    b = repo.add_memory(conn, "author", "新", 2.0, root_id=a)
    assert repo.current_in_chain(conn, a)["id"] == b
    repo.invalidate_memory(conn, b, 3.0)
    assert repo.current_in_chain(conn, a) is None


def test_all_memories_carries_slug_and_session(conn, world):
    src = repo.add_memory(conn, "author", "有來源", 1.0, quote="不寫結局",
                          discussion_id=world["d"], seq=0)
    wrk = repo.add_memory(conn, "work", "這篇", 2.0, story_id=world["s2"])
    typed = repo.add_memory(conn, "author", "手寫", 3.0)
    newer = repo.add_memory(conn, "author", "有來源二", 4.0, root_id=src)
    rows = repo.all_memories(conn)
    assert [r["id"] for r in rows] == [src, newer, wrk, typed]
    by = {r["id"]: r for r in rows}
    assert (by[src]["slug"], by[src]["title"], by[src]["session"]) == ("s1", "甲篇", "sess")
    assert (by[wrk]["slug"], by[wrk]["session"]) == ("s2", None)
    assert (by[typed]["slug"], by[typed]["session"]) == (None, None)


def test_memories_of_discussion_only_returns_live_rows(conn, world):
    d = world["d"]
    a = repo.add_memory(conn, "author", "甲", 1.0, quote="不寫結局", discussion_id=d, seq=0)
    b = repo.add_memory(conn, "work", "乙", 1.0, story_id=world["s1"], quote="結局", discussion_id=d, seq=0)
    repo.add_memory(conn, "author", "手寫", 1.0)
    repo.invalidate_memory(conn, a, 2.0)
    assert [m["id"] for m in repo.memories_of_discussion(conn, d)] == [b]
