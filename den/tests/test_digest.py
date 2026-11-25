import asyncio
import json

import pytest

from den import digest, suggest
from den.runner import RunResult
from marrow import repo

SAID = "作者:結尾的海是不是太突然\n你:我讀到海那段停了一下"


class Chat:
    def __init__(self, text=None, outcome="ok", boom=False):
        self.text, self.outcome, self.boom = text, outcome, boom
        self.calls = []

    async def __call__(self, system, user, *, config, **_):
        self.calls.append((system, user))
        if self.boom:
            raise RuntimeError("x")
        yield ("delta", "x")
        yield ("result", RunResult(self.outcome, None, "", "claude-x", {"output": 3}, 9, None, 1,
                                   self.text if self.outcome == "ok" else None))


def out(summary="聊了結尾。", threads=(), memories=()):
    return json.dumps({"summary": summary, "threads": list(threads), "memories": list(memories)},
                      ensure_ascii=False)


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


def test_make_skips_marker_rows_and_cleared(conn, disc):
    s, d = disc
    repo.add_utterance(conn, d, 4, "compact", "壓縮摘要", 2.0, "den", [], None)
    repo.add_utterance(conn, d, 5, "clear", "", 2.0, "den", [], None)
    chat = Chat(out())
    assert run(digest.make(conn, chat, d, s)) is None and chat.calls == []
    repo.add_utterance(conn, d, 6, "user", "清空後的新話", 3.0, "den", [], None)
    run(digest.make(conn, chat, d, s))
    user = chat.calls[0][1]
    assert "清空後的新話" in user and "壓縮摘要" not in user and "結尾的海" not in user
    assert repo.current_digest(conn, d)["through_seq"] == 6


def test_clear_after_digest_rebuilds_without_previous(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out("舊摘要", threads=[{"text": "海", "quote": "結尾的海是不是", "source_quote": None}])), d, s))
    repo.add_utterance(conn, d, 4, "clear", "", 2.0, "den", [], None)
    repo.add_utterance(conn, d, 5, "user", "重新開始聊", 3.0, "den", [], None)
    chat = Chat(out("新摘要"))
    run(digest.make(conn, chat, d, s))
    assert "舊摘要" not in chat.calls[0][1] and "<threads>" not in chat.calls[0][1]
    cur = repo.current_digest(conn, d)
    assert cur["text"] == "新摘要" and repo.threads_of(conn, cur["root_id"]) == []


def test_redigest_input_has_open_threads(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out(threads=[{"text": "開著的", "quote": "結尾的海是不是", "source_quote": None},
                                             {"text": "結束的", "quote": "海那段停了", "source_quote": None}])), d, s))
    root = repo.current_digest(conn, d)["root_id"]
    repo.set_thread_ended(conn, repo.threads_of(conn, root)[1]["id"], 3.0)
    repo.add_utterance(conn, d, 4, "user", "再聊一下", 3.0, "den", [], None)
    chat = Chat(out())
    run(digest.make(conn, chat, d, s))
    user = chat.calls[0][1]
    assert "<threads>" in user and "開著的" in user and "結束的" not in user


class Racing(Chat):
    def __init__(self, conn, d, act):
        super().__init__(out("模型的"))
        self.conn, self.d, self.act = conn, d, act

    async def __call__(self, system, user, *, config, **_):
        self.act(self.conn, self.d)
        async for ev in super().__call__(system, user, config=config):
            yield ev


def test_edit_while_running_is_kept(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out("第一版")), d, s))
    repo.add_utterance(conn, d, 4, "user", "再聊一下", 3.0, "den", [], None)
    cur = repo.current_digest(conn, d)
    edit = lambda c, x: repo.add_digest(c, x, "作者改的", cur["through_seq"], 9.0, root_id=cur["root_id"], edited=True)
    assert run(digest.make(conn, Racing(conn, d, edit), d, s)) is None
    assert repo.current_digest(conn, d)["text"] == "作者改的" and repo.digest_failed_seq(conn, d) is None


def test_deleted_while_running_writes_nothing(conn, disc):
    s, d = disc
    assert run(digest.make(conn, Racing(conn, d, repo.delete_discussion), d, s)) is None
    assert conn.execute("SELECT COUNT(*) FROM digest").fetchone()[0] == 0


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


@pytest.mark.parametrize("chat", [Chat(boom=True), Chat(outcome="usage-limit"), Chat(outcome="timeout")],
                         ids=["raise", "usage-limit", "timeout"])
def test_retryable_failure_not_recorded(conn, disc, chat):
    s, d = disc
    run(digest.make(conn, chat, d, s))
    assert repo.digest_failed_seq(conn, d) is None


def test_system_fills_limits():
    text = digest.system().text
    assert "{" not in text.split("只輸出")[0] and str(digest.DIGEST_MAX_CHARS) in text
    assert "最多 3 條" in text


MEM = {"text": "作者在想結尾", "quote": "結尾的海是不是太突然", "scope": "work"}


def test_make_stores_candidates_when_enabled(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out(memories=[MEM])), d, s, now=lambda: 5.0))
    (c,) = repo.candidates_of_story(conn, s)
    assert (c["discussion_id"], c["seq"], c["text"], c["created_at"]) == (d, 0, "作者在想結尾", 5.0)


def test_make_skips_candidates_when_disabled(conn, disc):
    s, d = disc
    suggest.set_enabled(conn, False)
    run(digest.make(conn, Chat(out(memories=[MEM])), d, s))
    assert repo.current_digest(conn, d) is not None and repo.candidates_of_story(conn, s) == []


def test_make_failed_summary_stores_no_candidates(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(json.dumps({"summary": "", "memories": [MEM]})), d, s))
    assert repo.candidates_of_story(conn, s) == []


def test_make_input_lists_known(conn, disc):
    s, d = disc
    repo.add_memory(conn, "work", "想讓結尾留白", 1.0, story_id=s)
    chat = Chat(out())
    run(digest.make(conn, chat, d, s))
    user = chat.calls[0][1]
    assert user.startswith("已經記住或提過的事:\n<known>\n- 想讓結尾留白\n</known>")


def test_make_input_without_known_has_no_block(conn, disc):
    s, d = disc
    chat = Chat(out())
    run(digest.make(conn, chat, d, s))
    assert "<known>" not in chat.calls[0][1]


def test_suggest_off_prompt_has_no_memories(conn, disc):
    s, d = disc
    suggest.set_enabled(conn, False)
    repo.add_memory(conn, "work", "想讓結尾留白", 1.0, story_id=s)
    chat = Chat(out())
    run(digest.make(conn, chat, d, s))
    system, user = chat.calls[0]
    assert "memories" not in system and "記憶:" not in system and "<known>" not in user
    assert "memories" in digest.system(True).text and "memories" not in digest.system(False).text


def _metered(conn, chat):
    from den import meter
    return meter.wrap_chat(chat, conn)


def test_digest_ledger_links_id(conn, disc):
    s, d = disc
    did = run(digest.make(conn, _metered(conn, Chat(out())), d, s))
    [row] = repo.calls_since(conn, 0)
    assert (row["kind"], row["outcome"], row["digest_id"], row["discussion_id"], row["story_id"]) == (
        "digest", "ok", did, d, s)
    assert "digest" in row["sizes"]


def test_digest_changed_while_running_discarded(conn, disc):
    s, d = disc
    run(digest.make(conn, Chat(out("第一版")), d, s))
    repo.add_utterance(conn, d, 4, "user", "再聊一下", 3.0, "den", [], None)
    cur = repo.current_digest(conn, d)
    edit = lambda c, x: repo.add_digest(c, x, "作者改的", cur["through_seq"], 9.0, root_id=cur["root_id"], edited=True)
    assert run(digest.make(conn, _metered(conn, Racing(conn, d, edit)), d, s)) is None
    [row] = repo.calls_since(conn, 0)
    assert row["outcome"] == "discarded" and row["digest_id"] is None


def test_digest_parse_fail_gate_rejected(conn, disc):
    s, d = disc
    assert run(digest.make(conn, _metered(conn, Chat("不是 JSON")), d, s)) is None
    assert repo.calls_since(conn, 0)[0]["outcome"] == "gate_rejected"


def test_digest_error_outcome_kept(conn, disc):
    s, d = disc
    run(digest.make(conn, _metered(conn, Chat(outcome="timeout")), d, s))
    assert repo.calls_since(conn, 0)[0]["outcome"] == "timeout"
