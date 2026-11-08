"""den.memory 行為契約:載入與寫入政策。"""
import pytest

from den import memory
from marrow import repo


def test_load_returns_active_text_in_order(conn):
    s1 = repo.ensure_story(conn, "s1", None, 0)
    repo.add_memory(conn, "author", "甲", 1.0)
    gone = repo.add_memory(conn, "author", "封存", 2.0)
    repo.add_memory(conn, "author", "乙", 3.0)
    repo.add_memory(conn, "work", "丙", 4.0, story_id=s1)
    repo.invalidate_memory(conn, gone, 5.0)
    assert memory.load(conn, s1) == {"author": ["甲", "乙"], "work": ["丙"]}


# ── 寫入政策 ──

USER_TS = 5.0


@pytest.fixture
def world(conn):
    with conn:
        s1 = repo.ensure_story(conn, "s1", None, 0)
        s2 = repo.ensure_story(conn, "s2", None, 0)
        for sid, session, words in ((s1, "abc", "我不寫結局,真的"), (s1, "same", "只在甲局"), (s2, "other", "乙局的話")):
            d = repo.ensure_discussion(conn, sid, session, "/h", None, 0)
            repo.add_utterance(conn, d, 0, "user", words, USER_TS, "web", [], None)
            repo.add_utterance(conn, d, 1, "assistant", "陪讀者不寫結局", USER_TS + 1, "web", [], None)
    return {"s1": s1, "s2": s2}


def _src(session="abc", seq=0, quote="不寫結局"):
    return {"session": session, "seq": seq, "quote": quote}


def test_remember_records_source_and_utterance_time(conn, world):
    mid = memory.remember(conn, "author", "不寫結局", 9.0, story_id=world["s1"], source=_src())
    m = repo.memory(conn, mid)
    assert m["quote"] == "不寫結局" and m["learned_at"] == 9.0 and m["valid_from"] == USER_TS
    assert m["story_id"] is None and m["scope"] == "author"
    assert (m["seq"], m["discussion_id"]) == (0, repo.discussion_by_session(conn, "abc")["id"])


def test_remember_work_scope_keeps_story_on_the_row(conn, world):
    mid = memory.remember(conn, "work", "想寫海", 9.0, story_id=world["s1"], source=_src())
    assert repo.memory(conn, mid)["story_id"] == world["s1"]


def test_remember_typed_uses_now_and_has_no_source(conn, world):
    m = repo.memory(conn, memory.remember(conn, "author", "手打", 9.0))
    assert m["valid_from"] == 9.0 and m["quote"] is None and m["discussion_id"] is None


def test_work_memory_from_other_works_session_rejected(conn, world):
    with pytest.raises(memory.BadSource) as e:
        memory.remember(conn, "work", "只在甲局", 9.0, story_id=world["s2"], source=_src("same", 0, "只在甲局"))
    assert e.value.code == "session-not-of-work"
    assert memory.remember(conn, "author", "只在甲局", 9.0, story_id=world["s2"], source=_src("same", 0, "只在甲局"))
    assert memory.remember(conn, "work", "只在甲局", 9.0, story_id=world["s1"], source=_src("same", 0, "只在甲局"))


@pytest.mark.parametrize("source,code", [
    ({"session": "nope", "seq": 0, "quote": "不寫結局"}, "unknown-session"),
    ({"session": "abc", "seq": 9, "quote": "不寫結局"}, "unknown-turn"),
    ({"session": "abc", "seq": 0, "quote": "我要寫結局"}, "quote-not-in-turn"),
    ({"session": "abc", "seq": 1, "quote": "不寫結局"}, "quote-not-in-turn"),
])
def test_bad_source_codes_and_nothing_written(conn, world, source, code):
    with pytest.raises(memory.BadSource) as e:
        memory.remember(conn, "author", "x", 9.0, story_id=world["s1"], source=source)
    assert e.value.code == code
    assert repo.all_memories(conn) == []


def test_author_source_needs_no_story(conn, world):
    mid = memory.remember(conn, "author", "x", 9.0, source=_src(quote="不寫結局"))
    assert repo.memory(conn, mid)["story_id"] is None


def test_cap_counts_active_rows_per_scope(conn, world):
    s1, s2 = world["s1"], world["s2"]
    memory.remember(conn, "author", "字" * 800, 1.0)
    with pytest.raises(memory.MemoryFull):
        memory.remember(conn, "author", "多", 2.0)
    memory.remember(conn, "work", "字" * 600, 3.0, story_id=s1)
    memory.remember(conn, "work", "字" * 600, 4.0, story_id=s2)
    with pytest.raises(memory.MemoryFull):
        memory.remember(conn, "work", "多", 5.0, story_id=s1)
    assert memory.usage(conn, "author") == 800 and memory.usage(conn, "work", s1) == 600


def test_cap_counts_code_points_not_bytes_and_ignores_invalidated(conn):
    mid = memory.remember(conn, "author", "😀" * 800, 1.0)
    memory.archive(conn, mid, 2.0)
    assert memory.usage(conn, "author") == 0
    assert memory.remember(conn, "author", "字" * 800, 3.0)


def test_edit_supersedes_and_keeps_source(conn, world):
    old = memory.remember(conn, "author", "不寫結局", 1.0, story_id=world["s1"], source=_src())
    new = memory.edit(conn, old, "現在會寫結局", 2.0)
    assert repo.memory(conn, old)["invalidated_at"] == 2.0
    n = repo.memory(conn, new)
    assert n["root_id"] == old and n["quote"] == "不寫結局" and n["valid_from"] == 2.0
    assert n["discussion_id"] == repo.memory(conn, old)["discussion_id"] and n["seq"] == 0


def test_second_edit_stays_on_the_same_chain(conn):
    a = memory.remember(conn, "author", "一", 1.0)
    b = memory.edit(conn, a, "二", 2.0)
    c = memory.edit(conn, b, "三", 3.0)
    assert repo.memory(conn, c)["root_id"] == a
    assert repo.current_in_chain(conn, a)["id"] == c


def test_edit_keeps_work_scope_story(conn, world):
    a = memory.remember(conn, "work", "一", 1.0, story_id=world["s1"])
    assert repo.memory(conn, memory.edit(conn, a, "二", 2.0))["story_id"] == world["s1"]


def test_edit_shorter_passes_when_at_cap(conn):
    mid = memory.remember(conn, "author", "字" * 800, 1.0)
    assert memory.edit(conn, mid, "字", 2.0)


def test_edit_over_cap_changes_nothing(conn):
    mid = memory.remember(conn, "author", "字" * 700, 1.0)
    memory.remember(conn, "author", "字" * 100, 1.0)
    with pytest.raises(memory.MemoryFull):
        memory.edit(conn, mid, "字" * 701, 2.0)
    assert repo.memory(conn, mid)["invalidated_at"] is None


def test_edit_and_archive_need_the_current_row(conn):
    old = memory.remember(conn, "author", "舊", 1.0)
    memory.edit(conn, old, "新", 2.0)
    with pytest.raises(memory.NotCurrent):
        memory.edit(conn, old, "再改", 3.0)
    with pytest.raises(memory.NotCurrent):
        memory.archive(conn, old, 3.0)


@pytest.mark.parametrize("call", [lambda c: memory.edit(c, 99, "x", 1.0), lambda c: memory.archive(c, 99, 1.0),
                                  lambda c: memory.revert(c, 99, 1.0)])
def test_missing_row_is_lookup_error(conn, call):
    with pytest.raises(LookupError):
        call(conn)


def test_revert_old_version_replaces_current(conn):
    old = memory.remember(conn, "author", "舊", 1.0)
    new = memory.edit(conn, old, "新", 2.0)
    back = memory.revert(conn, old, 3.0)
    assert repo.memory(conn, new)["invalidated_at"] == 3.0
    assert repo.memory(conn, back)["text"] == "舊"
    assert repo.current_in_chain(conn, old)["id"] == back


def test_revert_twice_leaves_one_live_row(conn):
    old = memory.remember(conn, "author", "舊", 1.0)
    memory.edit(conn, old, "新", 2.0)
    memory.revert(conn, old, 3.0)
    memory.revert(conn, old, 4.0)
    live = [r for r in repo.all_memories(conn) if r["invalidated_at"] is None]
    assert [r["text"] for r in live] == ["舊"]


def test_revert_archived_row_restores_it(conn):
    mid = memory.remember(conn, "author", "甲", 1.0)
    memory.archive(conn, mid, 2.0)
    assert repo.memory(conn, memory.revert(conn, mid, 3.0))["text"] == "甲"


def test_revert_current_row_is_rejected(conn):
    mid = memory.remember(conn, "author", "甲", 1.0)
    with pytest.raises(memory.AlreadyCurrent):
        memory.revert(conn, mid, 2.0)


def test_revert_over_cap_is_rejected(conn):
    mid = memory.remember(conn, "author", "字" * 800, 1.0)
    memory.archive(conn, mid, 2.0)
    memory.remember(conn, "author", "字" * 800, 3.0)
    with pytest.raises(memory.MemoryFull):
        memory.revert(conn, mid, 4.0)


def test_revert_longer_old_version_counts_replaced_row_once(conn):
    old = memory.remember(conn, "author", "字" * 800, 1.0)
    memory.edit(conn, old, "短", 2.0)
    assert memory.revert(conn, old, 3.0)


def test_writes_are_committed(conn):
    memory.remember(conn, "author", "甲", 1.0)
    assert conn.in_transaction is False
