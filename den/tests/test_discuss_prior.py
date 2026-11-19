import asyncio

from den import prior
from den.tests.test_app_discuss import c, fake_chat, in_loop, post_discuss  # noqa: F401
from marrow import repo

DIGEST = "上次聊到結尾的海"


def seed(c, source_quote=None, text="海的節奏還沒聊完"):
    def go(conn):
        s = repo.story_by_slug(conn, "mini")["id"]
        d = repo.ensure_discussion(conn, s, "old", "web", None, 0)
        for i in range(2):
            repo.add_utterance(conn, d, 2 * i, "user", "結尾的海是不是太突然", 1.0, "den", [], None)
            repo.add_utterance(conn, d, 2 * i + 1, "assistant", "我讀到海那段停了一下", 1.0, "den", [], None,
                               character="hyena")
        repo.close_discussion(conn, d, 1.0)
        root = repo.add_digest(conn, d, DIGEST, 3, 1.0)
        (t,) = repo.replace_threads(conn, root, [{"text": text, "quote": "結尾的海是不是",
                                                   "source_quote": source_quote, "ended_at": None}], 1.0)
        conn.commit()
        return {"digest": root, "thread": t, "old": d}
    return in_loop(c, go)


def send(c, sid, message="你好", **extra):
    r = c.post("/api/discuss/mini", json={"session_id": sid, "message": message, "anchors": [], **extra})
    assert r.status_code == 200
    return [e for e in (__import__("json").loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: "))]


def sid_of(evs):
    return evs[-1]["data"]["session_id"]


def first_recipe(c, sid):
    def go(conn):
        d = repo.discussion_by_session(conn, sid)
        return next(u for u in repo.utterances(conn, d["id"]) if u["role"] == "assistant")["recipe"]
    return in_loop(c, go)


def test_first_turn_injects_and_snapshots(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None))
    system = fake_chat.calls[-1][0]
    assert "之前和作者聊過的" in system and DIGEST in system and "海的節奏還沒聊完「結尾的海是不是」" in system
    assert first_recipe(c, sid)["prior"] == {"digests": [ids["digest"]], "threads": [ids["thread"]]}


def test_prior_false_snapshot_none(c, fake_chat):
    seed(c)
    sid = sid_of(send(c, None, prior=False))
    assert DIGEST not in fake_chat.calls[-1][0] and first_recipe(c, sid)["prior"] is None


def test_setting_off_snapshot_none(c, fake_chat):
    seed(c)
    c.put("/api/settings/prior", json={"enabled": False})
    sid = sid_of(send(c, None))
    assert DIGEST not in fake_chat.calls[-1][0] and first_recipe(c, sid)["prior"] is None


def test_later_turn_uses_snapshot_version(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None))
    assert c.put(f"/api/digests/{ids['digest']}", json={"text": "作者後來改的"}).status_code == 201
    send(c, sid, "再一句")
    assert DIGEST in fake_chat.calls[-1][0] and "作者後來改的" not in fake_chat.calls[-1][0]


def test_ended_thread_drops_on_later_turn(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None))
    c.put(f"/api/threads/{ids['thread']}", json={"ended": True})
    send(c, sid, "再一句")
    assert DIGEST in fake_chat.calls[-1][0] and "海的節奏還沒聊完" not in fake_chat.calls[-1][0]


def test_stale_thread_not_injected(c, fake_chat):
    seed(c, source_quote="稿裡沒有這一句")
    sid = sid_of(send(c, None))
    assert DIGEST in fake_chat.calls[-1][0] and "海的節奏還沒聊完" not in fake_chat.calls[-1][0]
    assert first_recipe(c, sid)["prior"]["threads"] == []
    assert c.get(f"/api/sessions/{sid}").json()["prior"]["threads"] == []


def test_talked_marked_after_commit(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None, "我想回到結尾的海是不是太突然"))
    view = c.get(f"/api/sessions/{sid}").json()["prior"]
    assert view["threads"][0]["id"] == ids["thread"] and view["threads"][0]["talked"] is True


def test_session_view_includes_prior(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None))
    view = c.get(f"/api/sessions/{sid}").json()["prior"]
    assert view["digests"] == [{"id": ids["digest"], "at": 1.0, "text": DIGEST}]
    assert view["threads"] == [{"id": ids["thread"], "text": "海的節奏還沒聊完", "quote": "結尾的海是不是",
                                "at": 1.0, "session": "old", "ended": False, "talked": False}]


def test_turn_proceeds_without_digest(c, fake_chat):
    sid = sid_of(send(c, None))
    assert "之前和作者聊過的" not in fake_chat.calls[-1][0]
    assert first_recipe(c, sid)["prior"] == {"digests": [], "threads": []}
    assert c.get(f"/api/sessions/{sid}").json()["prior"] is None


def test_digest_ready_later_joins_next_turn(c, fake_chat):
    sid = sid_of(send(c, None))
    ids = seed(c)
    send(c, sid, "第二句")
    assert DIGEST in fake_chat.calls[-1][0]
    assert c.get(f"/api/sessions/{sid}").json()["prior"]["digests"][0]["id"] == ids["digest"]
    c.put(f"/api/digests/{ids['digest']}", json={"text": "之後改的"})
    send(c, sid, "第三句")
    assert DIGEST in fake_chat.calls[-1][0] and "之後改的" not in fake_chat.calls[-1][0]


def test_opted_out_stays_out_when_digest_appears(c, fake_chat):
    sid = sid_of(send(c, None, prior=False))
    seed(c)
    send(c, sid, "第二句")
    assert DIGEST not in fake_chat.calls[-1][0]


def test_first_turn_kicks_when_idle_no_wait(c, fake_chat):
    def go(conn):
        s = repo.story_by_slug(conn, "mini")["id"]
        d = repo.ensure_discussion(conn, s, "old", "web", None, 0)
        for i in range(2):
            repo.add_utterance(conn, d, 2 * i, "user", "問", 1.0, "den", [], None)
            repo.add_utterance(conn, d, 2 * i + 1, "assistant", "答", 1.0, "den", [], None, character="hyena")
        conn.commit()
        return d
    old = in_loop(c, go)
    send(c, None)
    for _ in range(200):
        if in_loop(c, lambda conn: repo.digest_failed_seq(conn, old)) is not None:
            break
        __import__("time").sleep(0.02)
    assert in_loop(c, lambda conn: repo.digest_failed_seq(conn, old)) == 3


def test_redo_first_turn_keeps_prior_snapshot(c, fake_chat):
    ids = seed(c)
    evs = send(c, None)
    sid, seq = sid_of(evs), next(e for e in evs if e["event"] == "message")["data"]["seq"]
    assert c.put(f"/api/digests/{ids['digest']}", json={"text": "重說前改的"}).status_code == 201
    r = c.post(f"/api/sessions/{sid}/turns/{seq}/regenerate")
    assert r.status_code == 200
    assert first_recipe(c, sid)["prior"] == {"digests": [ids["digest"]], "threads": [ids["thread"]]}
    assert DIGEST in fake_chat.calls[-1][0] and "重說前改的" not in fake_chat.calls[-1][0]


def test_session_view_tolerates_deleted_digest(c, fake_chat):
    ids = seed(c)
    sid = sid_of(send(c, None))

    def drop(conn):
        repo.delete_discussion(conn, ids["old"])
        conn.commit()
    in_loop(c, drop)
    assert c.get(f"/api/sessions/{sid}").json()["prior"] is None
    send(c, sid, "再一句")
    assert DIGEST not in fake_chat.calls[-1][0]


class Queue:
    def __init__(self, running):
        self.is_running, self.log = running, []

    def running(self, story_id):
        return self.is_running

    async def wait(self, story_id, timeout):
        self.log.append(("wait", timeout))
        return True

    def ensure(self, story_id):
        self.log.append(("ensure",))


def test_snapshot_waits_when_running_else_kicks(conn):
    s = repo.story_by_slug(conn, "mini")["id"]
    busy, idle = Queue(True), Queue(False)
    assert asyncio.run(prior.snapshot(conn, busy, s, None, [], True, 8.0)) == {"digests": [], "threads": []}
    asyncio.run(prior.snapshot(conn, idle, s, None, [], True, 8.0))
    assert busy.log == [("wait", 8.0)] and idle.log == [("ensure",)]


def test_free_chat_no_prior(conn):
    q = Queue(True)
    assert asyncio.run(prior.snapshot(conn, q, None, None, [], True, 8.0)) is None and q.log == []
    assert prior.resolve(conn, None, "") is None
