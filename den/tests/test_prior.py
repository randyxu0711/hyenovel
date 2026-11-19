import asyncio
import json

from den import prior, suggest
from den.runner import RunResult
from marrow import repo


def _out(threads=()):
    return json.dumps({"summary": "摘", "threads": list(threads)}, ensure_ascii=False)


class Chat:
    def __init__(self, text=_out(), gate=None, boom_first=False):
        self.text, self.gate, self.boom_first = text, gate, boom_first
        self.calls = 0

    async def __call__(self, system, user, *, config):
        self.calls += 1
        if self.boom_first and self.calls == 1:
            raise RuntimeError("x")
        if self.gate is not None:
            await self.gate.wait()
        yield ("result", RunResult("ok", None, "", "m", {}, 1, None, 1, self.text))


def _disc(conn, story, sid, end, words=("結尾的海是不是太突然", "我讀到海那段停了一下")):
    d = repo.ensure_discussion(conn, story, sid, "web", None, 0)
    for i in range(2):
        repo.add_utterance(conn, d, 2 * i, "user", words[0], 1.0, "den", [], None)
        repo.add_utterance(conn, d, 2 * i + 1, "assistant", words[1], 1.0, "den", [], None)
    repo.close_discussion(conn, d, end)
    conn.commit()
    return d


def _mini(conn):
    return repo.story_by_slug(conn, "mini")["id"]


def test_enabled_default_and_toggle(conn):
    assert prior.enabled(conn)
    prior.set_enabled(conn, False)
    assert not prior.enabled(conn)
    prior.set_enabled(conn, True)
    assert prior.enabled(conn)


def test_ensure_single_flight(conn):
    s = _mini(conn)
    _disc(conn, s, "A", 1.0)

    async def go():
        gate = asyncio.Event()
        chat = Chat(gate=gate)
        q = prior.PriorQueue(conn, chat)
        q.ensure(s)
        q.ensure(s)
        assert q.running(s) and len(q.tasks) == 1
        gate.set()
        assert await q.wait(s, 5)
        assert not q.running(s) and q.tasks == {}
        return chat.calls
    assert asyncio.run(go()) == 1


def test_ensure_one_failure_continues(conn):
    s = _mini(conn)
    a, b = _disc(conn, s, "A", 1.0), _disc(conn, s, "B", 2.0)

    async def go():
        q = prior.PriorQueue(conn, Chat(boom_first=True))
        q.ensure(s)
        await q.wait(s, 5)
    asyncio.run(go())
    assert repo.current_digest(conn, b) is None and repo.current_digest(conn, a) is not None


def test_ensure_without_chat_noop(conn):
    async def go():
        q = prior.PriorQueue(conn, None)
        q.ensure(_mini(conn))
        return q.tasks
    assert asyncio.run(go()) == {}


def test_wait_no_task_returns_false_immediately(conn):
    assert asyncio.run(prior.PriorQueue(conn, Chat()).wait(_mini(conn), 5)) is False


def test_wait_timeout_false(conn):
    s = _mini(conn)
    _disc(conn, s, "A", 1.0)

    async def go():
        gate = asyncio.Event()
        q = prior.PriorQueue(conn, Chat(gate=gate))
        q.ensure(s)
        got = await q.wait(s, 0.01)
        still = q.running(s)
        await q.close()
        return got, still
    assert asyncio.run(go()) == (False, True)


def test_gather_caps_and_stale(conn, monkeypatch):
    monkeypatch.setattr(prior, "MAX_THREADS", 2)
    s = _mini(conn)
    a, b = _disc(conn, s, "A", 1.0), _disc(conn, s, "B", 2.0)
    _disc(conn, s, "C", 3.0)
    ra = repo.add_digest(conn, a, "甲摘", 3, 1.0)
    rb = repo.add_digest(conn, b, "乙摘", 3, 2.0)
    repo.add_digest(conn, b, "乙改", 3, 2.5, root_id=rb, edited=True)
    t = lambda text, src=None, ended=None: {"text": text, "quote": "結尾的海", "source_quote": src, "ended_at": ended}
    repo.replace_threads(conn, ra, [t("a1"), t("a2"), t("a-stale", "不在稿裡")], 1.0)
    repo.replace_threads(conn, rb, [t("b1", "海"), t("b-ended", ended=5.0)], 2.0)
    got = prior.gather(conn, s, None, "天空與海")
    assert [(d["session"], d["text"], d["edited"]) for d in got["digests"]] == [("B", "乙改", True), ("A", "甲摘", False)]
    assert [(x["text"], x["stale"], x["session"]) for x in got["threads"]] == \
        [("b1", False, "B"), ("a1", False, "A"), ("a-stale", True, "A")]
    assert [d["session"] for d in prior.gather(conn, s, b, "海")["digests"]] == ["A"]


def test_end_replaced_thread_ends_successor(conn):
    s = _mini(conn)
    d = _disc(conn, s, "A", 1.0)
    root = repo.add_digest(conn, d, "摘", 3, 1.0)
    t = lambda text, q: {"text": text, "quote": q, "source_quote": None, "ended_at": None}
    (old,) = repo.replace_threads(conn, root, [t("海", "結尾的海")], 1.0)
    same, other = repo.replace_threads(conn, root, [t("海2", "結尾的海是不是"), t("別的", "我讀到海那段")], 2.0)
    prior.end_thread(conn, old, 5.0)
    assert [x["ended_at"] for x in repo.threads_of(conn, root)] == [5.0, None]
    prior.end_thread(conn, old, None)
    assert repo.thread_by_id(conn, same)["ended_at"] is None
    prior.end_thread(conn, other, 6.0)
    assert repo.thread_by_id(conn, other)["ended_at"] == 6.0


class Q:
    def __init__(self, busy=False):
        self.busy, self.log = busy, []

    def running(self, story_id):
        return self.busy

    def ensure(self, story_id):
        self.log.append("ensure")

    async def wait(self, story_id, timeout):
        self.log.append("wait")
        return True


def _snap(conn, queue, use=True, every=()):
    s = repo.story_by_slug(conn, "mini")["id"]
    return asyncio.run(prior.snapshot(conn, queue, s, None, list(every), use, 0.1))


def test_first_turn_suggest_only_runs_queue_without_prior(conn):
    prior.set_enabled(conn, False)
    q = Q()
    assert _snap(conn, q) is None and q.log == ["ensure"]
    q = Q(busy=True)
    assert _snap(conn, q) is None and q.log == []
    suggest.set_enabled(conn, False)
    q = Q()
    assert _snap(conn, q) is None and q.log == []


def test_first_turn_not_use_prior_but_suggest_on(conn):
    q = Q()
    assert _snap(conn, q, use=False) is None and q.log == ["ensure"]


def test_suggest_only_second_turn_still_none(conn):
    prior.set_enabled(conn, False)
    q = Q()
    every = [{"role": "user", "seq": 0}, {"role": "assistant", "seq": 1, "recipe": {"prior": None}}]
    assert _snap(conn, q, every=every) is None and q.log == []
