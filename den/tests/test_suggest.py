import json

import pytest

from den import memory, suggest
from marrow import repo

TURNS = [{"seq": 0, "role": "user", "text": "我其實想讓結尾留白,不要講破"},
         {"seq": 1, "role": "assistant", "text": "讀伴覺得海那段寫得很安靜"},
         {"seq": 2, "role": "user", "text": "我寫東西習慣先寫最後一段再往前補"}]


def raw(*items):
    return json.dumps({"summary": "s", "threads": [], "memories": list(items)}, ensure_ascii=False)


def mem(text="作者先寫結尾", quote="習慣先寫最後一段再往前補", scope="author"):
    return {"text": text, "quote": quote, "scope": scope}


@pytest.fixture
def disc(conn):
    st = repo.story_by_slug(conn, "mini")
    d = repo.ensure_discussion(conn, st["id"], "A", "web", None, 0)
    for u in TURNS:
        repo.add_utterance(conn, d, u["seq"], u["role"], u["text"], 1.0, "den", [], None)
    conn.commit()
    return st["id"], d


def test_parse_keeps_author_quote_and_seq():
    (m,) = suggest.parse(raw(mem()), TURNS)
    assert m == {"text": "作者先寫結尾", "quote": "習慣先寫最後一段再往前補", "seq": 2, "scope": "author"}


def test_parse_drops_assistant_quote():
    assert suggest.parse(raw(mem(quote="海那段寫得很安靜")), TURNS) == []


def test_parse_drops_short_quote():
    assert suggest.parse(raw(mem(quote="想讓結尾留白,")), TURNS) == []
    assert suggest.parse(raw(mem(quote="想讓結尾留白,不")), TURNS)[0]["seq"] == 0
    assert suggest.parse(raw(mem(quote=" 想讓結尾留白,不要 ")), TURNS)[0]["seq"] == 0
    assert suggest.parse(raw(mem(quote="  想讓結尾留白,  ")), TURNS) == []


def test_parse_drops_bad_scope():
    assert suggest.parse(raw(mem(scope="character")), TURNS) == []


def test_parse_caps_three():
    items = [mem(text=f"事{i}") for i in range(5)]
    assert len(suggest.parse(raw(*items), TURNS)) == suggest.CANDIDATES_PER_DIGEST == 3


@pytest.mark.parametrize("body", ['{"summary": "s"}', '{"summary": "s", "memories": "x"}',
                                  '{"summary": "s", "memories": [{"quote": "習慣先寫最後一段再往前補"}]}',
                                  '{"summary": "s", "memories": [{"text": " ", "quote": "習慣先寫最後一段再往前補"}]}',
                                  '{"summary": "s", "memories": [{"text": "x", "quote": 3}]}', "not json"])
def test_parse_missing_or_bad_memories_is_empty(body):
    assert suggest.parse(body, TURNS) == []


def test_store_dedupes_across_story(conn, disc):
    s, d = disc
    other = repo.ensure_discussion(conn, s, "B", "web", None, 0)
    repo.add_utterance(conn, other, 0, "user", "我寫東西習慣先寫最後一段", 1.0, "den", [], None)
    skipped = repo.add_candidate(conn, other, 0, "習慣先寫最後一段", "先寫結尾", "author", 1.0)
    repo.resolve_candidate(conn, skipped, "skipped", 2.0)
    repo.add_memory(conn, "work", "想留白", 1.0, story_id=s, quote="其實想讓結尾留白,不要講破", discussion_id=d, seq=0)
    repo.add_memory(conn, "author", "手動的", 1.0)
    items = [{"text": "先寫結尾", "quote": "習慣先寫最後一段再往前補", "seq": 2, "scope": "author"},
             {"text": "留白", "quote": "想讓結尾留白,不要講破", "seq": 0, "scope": "work"},
             {"text": "手動的", "quote": "我寫東西習慣先寫最後", "seq": 2, "scope": "author"},
             {"text": "甲", "quote": "其實想讓結尾留白", "seq": 0, "scope": "work"},
             {"text": "新的一件", "quote": "東西習慣先寫最後一段再往前補", "seq": 2, "scope": "author"}]
    assert suggest.store(conn, d, s, items, 5.0) == 0
    fresh = [{"text": "甲", "quote": "我其實想讓結尾", "seq": 0, "scope": "work"},
             {"text": "乙", "quote": "我其實想讓結尾留白", "seq": 0, "scope": "work"}]
    repo.delete_discussion(conn, other)
    conn.execute("DELETE FROM memory")
    assert suggest.store(conn, d, s, fresh, 5.0) == 1
    assert [c["text"] for c in repo.candidates_of_story(conn, s)] == ["甲"]


def test_known_lists_memories_and_candidates_newest_first(conn, disc, monkeypatch):
    s, d = disc
    repo.add_memory(conn, "author", "關於我", 1.0)
    repo.add_memory(conn, "work", "這篇", 1.0, story_id=s)
    repo.add_candidate(conn, d, 0, "引引引引", "候選一", "work", 1.0)
    repo.add_candidate(conn, d, 0, "引引引引", "候選二", "work", 2.0)
    assert suggest.known(conn, s) == ["關於我", "這篇", "候選二", "候選一"]
    monkeypatch.setattr(suggest, "KNOWN_MAX", 2)
    assert suggest.known(conn, s) == ["關於我", "這篇"]


def test_enabled_defaults_on_and_toggles(conn):
    assert suggest.enabled(conn)
    suggest.set_enabled(conn, False)
    assert not suggest.enabled(conn)
    suggest.set_enabled(conn, True)
    assert suggest.enabled(conn)


def _cand(conn, disc, scope="work", text="想讓結尾留白"):
    s, d = disc
    cid = repo.add_candidate(conn, d, 0, "想讓結尾留白,不要講破", text, scope, 1.0)
    conn.commit()
    return cid


def test_save_writes_memory_with_source(conn, disc):
    cid = _cand(conn, disc)
    mid = suggest.save(conn, cid, "work", None, 5.0)
    m, c = repo.memory(conn, mid), repo.candidate(conn, cid)
    assert (m["scope"], m["text"], m["quote"], m["seq"], m["discussion_id"]) == (
        "work", "想讓結尾留白", "想讓結尾留白,不要講破", 0, disc[1])
    assert (c["resolution"], c["memory_id"], c["resolved_at"]) == ("saved", mid, 5.0)


def test_save_edited_text_and_other_scope(conn, disc):
    mid = suggest.save(conn, _cand(conn, disc), "author", "作者喜歡留白", 5.0)
    m = repo.memory(conn, mid)
    assert (m["scope"], m["text"], m["story_id"]) == ("author", "作者喜歡留白", None)


def test_save_over_cap_stays_pending(conn, disc):
    repo.add_memory(conn, "author", "滿" * 800, 1.0)
    cid = _cand(conn, disc)
    with pytest.raises(memory.MemoryFull):
        suggest.save(conn, cid, "author", None, 5.0)
    assert repo.candidate(conn, cid)["resolution"] is None


def test_save_rolls_back_when_resolve_fails(conn, disc, monkeypatch):
    cid = _cand(conn, disc)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(repo, "resolve_candidate", boom)
    with pytest.raises(RuntimeError):
        suggest.save(conn, cid, "work", None, 5.0)
    assert repo.active_memories(conn, "work", disc[0]) == []


def test_save_twice_is_not_pending(conn, disc):
    cid = _cand(conn, disc)
    suggest.save(conn, cid, "work", None, 5.0)
    with pytest.raises(suggest.NotPending):
        suggest.save(conn, cid, "work", None, 6.0)
    with pytest.raises(suggest.NotPending):
        suggest.skip(conn, cid, 6.0)
    assert len(repo.active_memories(conn, "work", disc[0])) == 1


def test_unknown_candidate(conn):
    for act in (lambda: suggest.save(conn, 999, "work", None, 1.0), lambda: suggest.skip(conn, 999, 1.0),
                lambda: suggest.undo(conn, 999, 1.0)):
        with pytest.raises(suggest.UnknownCandidate):
            act()
    assert not issubclass(suggest.UnknownCandidate, LookupError)


def test_skip_then_undo_back_to_pending(conn, disc):
    cid = _cand(conn, disc)
    suggest.skip(conn, cid, 5.0)
    assert repo.candidate(conn, cid)["resolution"] == "skipped"
    suggest.undo(conn, cid, 6.0)
    assert repo.candidate(conn, cid)["resolution"] is None


def test_undo_pending_raises(conn, disc):
    with pytest.raises(suggest.IsPending):
        suggest.undo(conn, _cand(conn, disc), 5.0)


def test_undo_saved_archives_memory(conn, disc):
    cid = _cand(conn, disc)
    mid = suggest.save(conn, cid, "work", None, 5.0)
    suggest.undo(conn, cid, 6.0)
    assert repo.memory(conn, mid)["invalidated_at"] == 6.0
    c = repo.candidate(conn, cid)
    assert (c["resolution"], c["memory_id"]) == (None, None)


def test_undo_after_memory_edited_raises_not_current(conn, disc):
    cid = _cand(conn, disc)
    mid = suggest.save(conn, cid, "work", None, 5.0)
    new = memory.edit(conn, mid, "作者改過的", 6.0)
    with pytest.raises(memory.NotCurrent):
        suggest.undo(conn, cid, 7.0)
    assert repo.candidate(conn, cid)["resolution"] == "saved" and repo.memory(conn, new)["invalidated_at"] is None


def test_undo_after_memory_archived_just_reopens(conn, disc):
    cid = _cand(conn, disc)
    mid = suggest.save(conn, cid, "work", None, 5.0)
    memory.archive(conn, mid, 6.0)
    suggest.undo(conn, cid, 7.0)
    assert repo.candidate(conn, cid)["resolution"] is None and repo.memory(conn, mid)["invalidated_at"] == 6.0


def test_pending_drops_older_than_ttl_and_when_off(conn, disc):
    cid = _cand(conn, disc)
    assert [c["id"] for c in suggest.pending(conn, 1.0 + suggest.CANDIDATE_TTL_S)] == [cid]
    assert suggest.pending(conn, 2.0 + suggest.CANDIDATE_TTL_S) == []
    suggest.set_enabled(conn, False)
    assert suggest.pending(conn, 1.0) == []
