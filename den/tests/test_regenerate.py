import json
import threading

import pytest

from den import discuss
from den.tests.test_app_discuss import SEA, c, events, fake_chat, free, in_loop, post_discuss  # noqa: F401
from marrow import repo


def regen(c, sid, seq):
    return c.post(f"/api/sessions/{sid}/turns/{seq}/regenerate")


def regen_events(c, sid, seq):
    r = regen(c, sid, seq)
    assert r.status_code == 200, r.text
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def rows(c, sid):
    return in_loop(c, lambda conn: repo.utterances(conn, repo.discussion_by_session(conn, sid)["id"]))


def shelved(c):
    return in_loop(c, lambda conn: [repo._row(r) for r in conn.execute(
        "SELECT * FROM utterance_variant ORDER BY discussion_id, seq, n")])


def _two_turns(c, fake_chat, quotes=()):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    body = {"session_id": sid, "message": "那盞燈呢", "anchors": ["m1"], "quotes": list(quotes)}
    c.post("/api/discuss/mini", json=body)
    return sid


@pytest.mark.parametrize("shape", ["quoted", "opener", "attached", "continue"])
def test_redo_sends_the_same_bytes_as_the_first_run(c, fake_chat, shape):
    if shape == "quoted":
        sid, seq = _two_turns(c, fake_chat, ["桌上那盞燈還亮著"]), 3
    elif shape == "opener":
        sid, seq = post_discuss(c, "mini", None, "", [])[-1]["data"]["session_id"], 0
    elif shape == "attached":
        sid, seq = events(free(c, message="", attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"], 0
    else:
        sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
        post_discuss(c, "mini", sid, "", [])
        seq = 2
    first = fake_chat.calls[-1]
    fake_chat.deltas = ["新", "版"]
    evs = regen_events(c, sid, seq)
    assert fake_chat.calls[-1] == first
    assert evs[-2]["data"]["seq"] == seq and evs[-2]["data"]["text"] == "新版"
    assert (evs[-2]["data"]["variant"], evs[-2]["data"]["variants"]) == (2, 2)


def test_redo_replaces_in_place_and_shelves_the_old(c, fake_chat):
    sid = _two_turns(c, fake_chat)
    before = rows(c, sid)
    fake_chat.deltas = ["二"]
    regen_events(c, sid, 3)
    after = rows(c, sid)
    assert len(after) == len(before) and after[3]["text"] == "二" and after[3]["variant"] == 2
    assert after[3]["recipe"]["retrieved"] is not None and after[:3] == before[:3]
    old = shelved(c)
    assert [(v["seq"], v["n"], v["text"]) for v in old] == [(3, 1, "AB")]
    assert (old[0]["recipe"], old[0]["usage"], old[0]["ts"]) == (before[3]["recipe"], before[3]["usage"], before[3]["ts"])
    fake_chat.deltas = ["三"]
    assert regen_events(c, sid, 3)[-2]["data"]["variants"] == 3


def test_history_after_redo_only_has_the_kept_version(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    fake_chat.deltas = ["留下的"]
    regen_events(c, sid, 1)
    post_discuss(c, "mini", sid, "然後", [])
    sent = fake_chat.calls[-1][1]
    assert "你:留下的" in sent and "你:AB" not in sent


@pytest.mark.parametrize("failure", ["crash", "no-result", "raise"])
def test_failed_redo_changes_nothing(c, fake_chat, failure):
    sid = _two_turns(c, fake_chat)
    before = rows(c, sid)
    if failure == "crash":
        fake_chat.outcome = "crash"
    elif failure == "no-result":
        async def nothing():
            yield ("delta", "x")
        fake_chat.override = nothing
    else:
        async def boom():
            raise RuntimeError("x")
            yield
        fake_chat.override = boom
    assert regen_events(c, sid, 3)[-1]["event"] == "error"
    assert rows(c, sid) == before and shelved(c) == []


def test_failed_commit_changes_nothing(c, fake_chat, monkeypatch):
    sid = _two_turns(c, fake_chat)
    before = rows(c, sid)

    def broken(*a, **k):
        raise RuntimeError("disk")
    monkeypatch.setattr(repo, "close_discussion", broken)
    assert regen_events(c, sid, 3)[-1]["data"]["code"] == "commit-failed"
    monkeypatch.undo()
    assert rows(c, sid) == before and shelved(c) == []


def test_only_the_last_row_can_be_redone(c, fake_chat):
    sid = _two_turns(c, fake_chat)
    n = len(fake_chat.calls)
    assert (regen(c, sid, 1).status_code, regen(c, sid, 1).json()["code"]) == (409, "not-last-turn")
    assert (regen(c, sid, 2).status_code, regen(c, sid, 2).json()["code"]) == (422, "not-assistant-turn")
    assert regen(c, sid, 9).json()["code"] == "unknown-turn"
    assert regen(c, "nope", 1).json()["code"] == "unknown-session"
    c.post(f"/api/sessions/{sid}/clear")
    assert regen(c, sid, 3).json()["code"] == "not-last-turn"
    assert len(fake_chat.calls) == n


def test_redo_rejects_legacy_session(c, fake_chat):
    def legacy(conn):
        st = repo.story_by_slug(conn, "mini")
        d = repo.ensure_discussion(conn, st["id"], "old", "web", None, 0)
        repo.add_utterance(conn, d, 0, "assistant", "舊", 1.0, "den", [], None)
        conn.commit()
    in_loop(c, legacy)
    assert (regen(c, "old", 0).status_code, regen(c, "old", 0).json()["code"]) == (409, "legacy-session")


def test_redo_rejects_archived_character(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    in_loop(c, lambda conn: (conn.execute("UPDATE character SET archived_at = 1 WHERE id = 'hyena'"), conn.commit()))
    n = len(fake_chat.calls)
    r = regen(c, sid, 1)
    assert (r.status_code, r.json()["code"]) == (422, "unknown-character") and len(fake_chat.calls) == n


def test_redo_keeps_the_character_of_that_reply(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    c.post("/api/discuss/mini", json={"session_id": sid, "message": "換你", "character": "deer"})
    assert regen_events(c, sid, 3)[-2]["data"]["character"] == "deer"


def test_redo_while_a_turn_runs_is_busy(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "卡住"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        r = regen(c, sid, 1)
        assert (r.status_code, r.json()["code"]) == (409, "busy")
    finally:
        fake_chat.release.set()
    t.join(5)


def test_turn_while_redo_runs_is_busy(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    fake_chat.hang = True
    t = threading.Thread(target=regen, args=(c, sid, 1), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        r = c.post("/api/discuss/mini", json={"session_id": sid, "message": "插隊"})
        assert (r.status_code, r.json()["code"]) == (409, "busy")
        assert c.post(f"/api/sessions/{sid}/clear").json()["code"] == "busy"
        assert c.post(f"/api/sessions/{sid}/archive").json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)


@pytest.mark.parametrize("sneak", ["clear", "user", "deleted"])
def test_redo_rechecks_the_last_row_after_taking_the_lock(c, fake_chat, sneak):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    n = len(fake_chat.calls)

    async def drive():
        conn = c.app.state.mgr.conn
        turn = discuss.prepare_redo(conn, sid, 1)
        with conn:
            if sneak == "deleted":
                repo.delete_discussion(conn, turn["discussion_id"])
            else:
                repo.add_utterance(conn, turn["discussion_id"], 2, sneak, "插", 9.0, "den", [], None)
        return [ev async for ev in discuss.run_turn(conn, c.app.state.chat, turn, "", [])]
    evs = c.portal.call(drive)
    assert [e["event"] for e in evs] == ["error"] and evs[0]["data"]["code"] == "not-last-turn"
    assert len(fake_chat.calls) == n


def test_redo_after_compact_is_not_last(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    c.post(f"/api/sessions/{sid}/compact")
    assert regen(c, sid, 1).json()["code"] == "not-last-turn"


def test_next_turn_retrieval_uses_the_kept_versions_recipe(c, fake_chat, monkeypatch):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    regen_events(c, sid, 1)
    kept = rows(c, sid)[1]["recipe"]["retrieved"]
    in_loop(c, lambda conn: (conn.execute("UPDATE utterance_variant SET recipe = ?",
                                          ('{"retrieved": ["shelved-only"]}',)), conn.commit()))
    recipe = json.dumps({**rows(c, sid)[1]["recipe"], "retrieved": ["kept-only"]})
    in_loop(c, lambda conn: (conn.execute("UPDATE utterance SET recipe = ? WHERE seq = 1", (recipe,)), conn.commit()))
    seen = {}
    real = discuss.retrieve.pick

    def spy(*a, **k):
        seen["previous"] = list(k["previous"])
        return real(*a, **k)
    monkeypatch.setattr(discuss.retrieve, "pick", spy)
    post_discuss(c, "mini", sid, "然後", [])
    assert kept is not None and seen["previous"] == ["kept-only"]


def test_everything_else_is_busy_while_redo_runs(c, fake_chat):
    sid = post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]
    fake_chat.hang = True
    t = threading.Thread(target=regen, args=(c, sid, 1), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert c.post(f"/api/sessions/{sid}/compact").json()["code"] == "busy"
        assert c.put(f"/api/sessions/{sid}/turns/1/variant", json={"n": 1}).json()["code"] == "busy"
        assert c.put(f"/api/sessions/{sid}/turns/1/text", json={"text": "x"}).json()["code"] == "busy"
        assert regen(c, sid, 1).json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)


def test_pick_and_edit_reject_legacy_session(c, fake_chat):
    def legacy(conn):
        st = repo.story_by_slug(conn, "mini")
        d = repo.ensure_discussion(conn, st["id"], "old", "web", None, 0)
        repo.add_utterance(conn, d, 0, "assistant", "舊", 1.0, "den", [], None)
        conn.commit()
    in_loop(c, legacy)
    assert c.put("/api/sessions/old/turns/0/variant", json={"n": 1}).json()["code"] == "legacy-session"
    assert c.put("/api/sessions/old/turns/0/text", json={"text": "x"}).json()["code"] == "legacy-session"
