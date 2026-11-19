import asyncio
import json

import pytest

from den import digest
from den.runner import RunResult
from marrow import repo

SAID = "作者:結尾的海是不是太突然\n你:我讀到海那段停了一下"


class Chat:
    def __init__(self, text=None, outcome="ok", boom=False):
        self.text, self.outcome, self.boom = text, outcome, boom
        self.calls = []

    async def __call__(self, system, user, *, config):
        self.calls.append((system, user))
        if self.boom:
            raise RuntimeError("x")
        yield ("delta", "x")
        yield ("result", RunResult(self.outcome, None, "", "claude-x", {"output": 3}, 9, None, 1,
                                   self.text if self.outcome == "ok" else None))


def out(summary="聊了結尾。", threads=()):
    return json.dumps({"summary": summary, "threads": list(threads)}, ensure_ascii=False)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def disc(conn):
    st = repo.story_by_slug(conn, "mini")
    d = repo.ensure_discussion(conn, st["id"], "A", "web", None, 0)
    for seq, (role, text) in enumerate([("user", "結尾的海是不是太突然"), ("assistant", "我讀到海那段停了一下"),
                                        ("user", "那我再想想"), ("assistant", "好")]):
        repo.add_utterance(conn, d, seq, role, text, 1.0, "den", [], None)
    conn.commit()
    return st["id"], d


def test_parse_drops_unquoted_thread():
    got = digest.parse(out(threads=[{"text": "甲", "quote": "結尾的海是不是", "source_quote": None},
                                    {"text": "乙", "quote": "從來沒說過的話", "source_quote": None}]), SAID, [])
    assert [t["text"] for t in got[1]] == ["甲"]


def test_parse_min_quote_len():
    got = digest.parse(out(threads=[{"text": "甲", "quote": "結尾", "source_quote": None},
                                    {"text": "乙", "quote": 3, "source_quote": None}, "壞", {"text": ""}]), SAID, [])
    assert got == ("聊了結尾。", [])


def test_parse_source_quote_missing_becomes_none():
    got = digest.parse(out(threads=[{"text": "甲", "quote": "結尾的海是不是", "source_quote": "沒有這句"},
                                    {"text": "乙", "quote": "海那段停了", "source_quote": "海很藍"},
                                    {"text": "丙", "quote": "海那段停了", "source_quote": 5}]), SAID, ["天空,海很藍。"])
    assert [t["source_quote"] for t in got[1]] == [None, "海很藍", None]


def test_parse_bad_json_none():
    assert digest.parse("不是 JSON", SAID, []) is None
    assert digest.parse(out(summary="  "), SAID, []) is None
    assert digest.parse(json.dumps({"threads": []}), SAID, []) is None


def test_parse_empty_threads_keeps_summary():
    assert digest.parse(out(), SAID, []) == ("聊了結尾。", [])
    assert digest.parse(json.dumps({"summary": "s", "threads": "x"}), SAID, []) == ("s", [])


def test_parse_caps_threads_and_truncates(monkeypatch):
    monkeypatch.setattr(digest, "DIGEST_MAX_CHARS", 3)
    monkeypatch.setattr(digest, "THREADS_PER_DIGEST", 1)
    got = digest.parse(out(threads=[{"text": "甲", "quote": "結尾的海是不是", "source_quote": None}] * 3), SAID, [])
    assert got[0] == "聊了結" and len(got[1]) == 1


def test_make_writes_digest_and_threads(conn, disc):
    s, d = disc
    chat = Chat(out(threads=[{"text": "海的節奏", "quote": "結尾的海是不是", "source_quote": None}]))
    did = run(digest.make(conn, chat, d, s, now=lambda: 5.0))
    cur = repo.current_digest(conn, d)
    assert cur["id"] == did and cur["through_seq"] == 3 and cur["usage"]["model"] == "claude-x"
    assert [t["text"] for t in repo.threads_of(conn, cur["root_id"])] == ["海的節奏"]
    assert "作者:結尾的海是不是太突然" in chat.calls[0][1] and "<previous>" not in chat.calls[0][1]


def test_make_idempotent_no_call(conn, disc):
    s, d = disc
    chat = Chat(out())
    first = run(digest.make(conn, chat, d, s))
    assert run(digest.make(conn, chat, d, s)) == first and len(chat.calls) == 1


def test_make_empty_discussion_none(conn, disc):
    s, _ = disc
    e = repo.ensure_discussion(conn, s, "E", "web", None, 0)
    chat = Chat(out())
    assert run(digest.make(conn, chat, e, s)) is None and chat.calls == []


def test_make_skips_marker_rows(conn, disc):
    s, d = disc
    repo.add_utterance(conn, d, 4, "compact", "壓縮摘要", 2.0, "den", [], None)
    repo.add_utterance(conn, d, 5, "clear", "", 2.0, "den", [], None)
    chat = Chat(out())
    run(digest.make(conn, chat, d, s))
    assert "壓縮摘要" not in chat.calls[0][1] and repo.current_digest(conn, d)["through_seq"] == 3


def test_make_incremental_input_has_prev_summary(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out("第一版")), d, s))
    repo.add_utterance(conn, d, 4, "user", "新的問題來了", 3.0, "den", [], None)
    chat = Chat(out("第二版"))
    run(digest.make(conn, chat, d, s))
    user = chat.calls[0][1]
    assert "<previous>\n第一版\n</previous>" in user and "新的問題來了" in user and "結尾的海是不是太突然" not in user
    assert repo.current_digest(conn, d)["text"] == "第二版"


def test_redigest_keeps_edit_and_ended(conn, disc):
    s, d = disc
    first = run(digest.make(conn, Chat(out(threads=[{"text": "海", "quote": "結尾的海是不是", "source_quote": None},
                                                     {"text": "停", "quote": "海那段停了", "source_quote": None}])), d, s))
    root = repo.digest_by_id(conn, first)["root_id"]
    t_sea = repo.threads_of(conn, root)[0]["id"]
    repo.set_thread_ended(conn, t_sea, 4.0)
    repo.add_digest(conn, d, "作者改過的摘要", 3, 4.5, root_id=root, edited=True)
    repo.add_utterance(conn, d, 4, "user", "再聊一下", 5.0, "den", [], None)
    chat = Chat(out("更新後", threads=[{"text": "海又來", "quote": "結尾的海是不是太突然", "source_quote": None},
                                      {"text": "停", "quote": "海那段停了", "source_quote": None}]))
    run(digest.make(conn, chat, d, s))
    assert "作者改過的摘要" in chat.calls[0][1]
    cur = repo.current_digest(conn, d)
    assert cur["root_id"] == root
    assert [(t["text"], t["ended_at"]) for t in repo.threads_of(conn, root)] == [("海又來", 4.0), ("停", None)]


@pytest.mark.parametrize("chat", [Chat(boom=True), Chat(outcome="crash"), Chat("不是 JSON")],
                         ids=["raise", "crash", "bad-json"])
def test_make_failure_returns_none(conn, disc, chat):
    s, d = disc
    assert run(digest.make(conn, chat, d, s)) is None
    assert repo.current_digest(conn, d) is None


def test_failed_digest_not_retried_until_new_turns(conn, disc):
    s, d = disc
    bad = Chat("不是 JSON")
    run(digest.make(conn, bad, d, s))
    run(digest.make(conn, bad, d, s))
    assert len(bad.calls) == 1 and repo.digest_failed_seq(conn, d) == 3
    repo.add_utterance(conn, d, 4, "user", "又聊了", 3.0, "den", [], None)
    good = Chat(out())
    assert run(digest.make(conn, good, d, s)) is not None and len(good.calls) == 1


@pytest.mark.parametrize("chat", [Chat(boom=True), Chat(outcome="usage-limit")], ids=["raise", "usage-limit"])
def test_retryable_failure_not_recorded(conn, disc, chat):
    s, d = disc
    run(digest.make(conn, chat, d, s))
    assert repo.digest_failed_seq(conn, d) is None


def test_system_fills_limits():
    text = digest.system().text
    assert "{" not in text.split("只輸出")[0] and str(digest.DIGEST_MAX_CHARS) in text
