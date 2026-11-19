import json

import pytest

from den import suggest
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
