import threading

from den.config import MAX_CHAT_CHARS, REACTION_MARKS
from den.tests.test_app_discuss import c, fake_chat, in_loop, post_discuss  # noqa: F401
from den.tests.test_regenerate import regen_events, rows, shelved
from marrow import repo


def _session(c):
    return post_discuss(c, "mini", None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]


def turn(c, sid, seq):
    return next(t for t in c.get(f"/api/sessions/{sid}").json()["turns"] if t["seq"] == seq)


def pick(c, sid, seq, n):
    return c.put(f"/api/sessions/{sid}/turns/{seq}/variant", json={"n": n})


def edit(c, sid, seq, text):
    return c.put(f"/api/sessions/{sid}/turns/{seq}/text", json={"text": text})


def every_text(c):
    return in_loop(c, lambda conn: [r[0] for r in conn.execute("SELECT text FROM utterance")]
                   + [r[0] for r in conn.execute("SELECT text FROM utterance_variant")])


def test_pick_swaps_back_and_marks_follow_the_version(c, fake_chat):
    sid = _session(c)
    c.put(f"/api/sessions/{sid}/turns/1/reaction", json={"mark": "misread"})
    c.put(f"/api/sessions/{sid}/turns/1/voice")
    fake_chat.deltas = ["二"]
    regen_events(c, sid, 1)
    t = turn(c, sid, 1)
    assert (t["text"], t["variant"], t["reaction"], t["voice"]) == ("二", {"n": 2, "total": 2}, None, False)
    assert pick(c, sid, 1, 1).json() == {"variant": 1, "variants": 2}
    t = turn(c, sid, 1)
    assert (t["text"], t["variant"], t["reaction"]["mark"], t["voice"]) == ("AB", {"n": 1, "total": 2}, "misread", True)
    assert pick(c, sid, 1, 1).status_code == 200
    r = pick(c, sid, 1, 7)
    assert (r.status_code, r.json()["code"]) == (404, "unknown-variant")


def test_pick_only_on_the_last_row(c, fake_chat):
    sid = _session(c)
    regen_events(c, sid, 1)
    post_discuss(c, "mini", sid, "然後", [])
    r = pick(c, sid, 1, 1)
    assert (r.status_code, r.json()["code"]) == (409, "not-last-turn")


def test_edit_overwrites_and_marks_voice(c, fake_chat):
    sid = _session(c)
    before = rows(c, sid)[1]
    assert edit(c, sid, 1, "  我改的字  ").json() == {"edited": True}
    t = turn(c, sid, 1)
    assert (t["text"], t["edited"], t["voice"], t["variant"]["n"]) == ("我改的字", True, True, 1)
    assert "AB" not in every_text(c)
    after = rows(c, sid)[1]
    assert after["edited_at"] is not None
    assert {k: after[k] for k in ("recipe", "usage", "ts", "variant", "analysis_fp")} == \
        {k: before[k] for k in ("recipe", "usage", "ts", "variant", "analysis_fp")}


def test_edit_same_text_writes_nothing(c, fake_chat):
    sid = _session(c)
    assert edit(c, sid, 1, "AB").json() == {"edited": False}
    t = turn(c, sid, 1)
    assert (t["edited"], t["voice"]) == (False, False)


def test_edit_does_not_remark_after_unmark(c, fake_chat):
    sid = _session(c)
    edit(c, sid, 1, "一")
    c.delete(f"/api/sessions/{sid}/turns/1/voice")
    edit(c, sid, 1, "一")
    assert turn(c, sid, 1)["voice"] is False
    edit(c, sid, 1, "二")
    assert turn(c, sid, 1)["voice"] is True


def test_edit_rejects(c, fake_chat):
    sid = _session(c)
    assert edit(c, sid, 1, " \n").json()["code"] == "blank-reply"
    assert edit(c, sid, 1, "字" * (MAX_CHAT_CHARS + 1)).json()["code"] == "reply-too-long"
    assert edit(c, sid, 0, "x").json()["code"] == "not-assistant-turn"
    assert edit(c, sid, 5, "x").json()["code"] == "unknown-turn"


def test_edit_older_reply_feeds_the_next_compact(c, fake_chat):
    sid = _session(c)
    post_discuss(c, "mini", sid, "然後", [])
    assert edit(c, sid, 1, "早先那則").json() == {"edited": True}
    c.post(f"/api/sessions/{sid}/compact")
    assert "早先那則" in fake_chat.calls[-1][1]


def test_edited_text_reaches_next_turn_history(c, fake_chat):
    sid = _session(c)
    edit(c, sid, 1, "改過的回覆")
    post_discuss(c, "mini", sid, "然後", [])
    assert "你:改過的回覆" in fake_chat.calls[-1][1] and "你:AB" not in fake_chat.calls[-1][1]


def test_edited_version_keeps_edited_at_when_shelved(c, fake_chat):
    sid = _session(c)
    edit(c, sid, 1, "改")
    regen_events(c, sid, 1)
    assert turn(c, sid, 1)["edited"] is False and shelved(c)[0]["edited_at"] is not None
    pick(c, sid, 1, 1)
    assert turn(c, sid, 1)["edited"] is True


def test_voice_coexists_with_reaction_and_is_idempotent(c, fake_chat):
    sid = _session(c)
    c.put(f"/api/sessions/{sid}/turns/1/reaction", json={"mark": "misread"})
    assert c.put(f"/api/sessions/{sid}/turns/1/voice").status_code == 204
    assert c.put(f"/api/sessions/{sid}/turns/1/voice").status_code == 204
    t = turn(c, sid, 1)
    assert (t["reaction"]["mark"], t["voice"]) == ("misread", True)
    assert c.delete(f"/api/sessions/{sid}/turns/1/voice").status_code == 204
    assert turn(c, sid, 1)["voice"] is False
    assert c.put(f"/api/sessions/{sid}/turns/0/voice").json()["code"] == "not-assistant-turn"
    assert len(REACTION_MARKS) == 2 and "voice" not in REACTION_MARKS


def test_pick_and_edit_while_a_turn_runs_are_busy(c, fake_chat):
    sid = _session(c)
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "卡住"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert pick(c, sid, 1, 1).json()["code"] == "busy"
        assert edit(c, sid, 1, "x").json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)


def test_memory_gate_still_refuses_reply_quotes_after_edit(c, fake_chat):
    sid = _session(c)
    edit(c, sid, 1, "讀伴改過的句子")
    r = c.post("/api/memory", json={"scope": "author", "text": "x", "quote": "讀伴改過的句子",
                                    "session": sid, "seq": 1})
    assert (r.status_code, r.json()["code"]) == (422, "quote-not-in-turn")
    assert in_loop(c, lambda conn: conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]) == 0


def test_delete_session_clears_versions_and_voice(c, fake_chat):
    sid = _session(c)
    c.put(f"/api/sessions/{sid}/turns/1/voice")
    regen_events(c, sid, 1)
    c.post(f"/api/sessions/{sid}/archive")
    assert c.delete(f"/api/sessions/{sid}").status_code == 204
    assert in_loop(c, lambda conn: [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                                    for t in ("utterance_variant", "voice_mark")]) == [0, 0]
    assert in_loop(c, lambda conn: repo.discussion_by_session(conn, sid)) is None
