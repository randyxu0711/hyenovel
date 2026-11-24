import threading

from den import compact
from den.tests.test_app_discuss import (SEA, c, events, fake_chat, first_turn, free, in_loop,  # noqa: F401
                                        post_discuss)
from marrow import repo


def _rows(c, sid):
    return in_loop(c, lambda conn: repo.utterances(conn, repo.discussion_by_session(conn, sid)["id"]))


def clear(c, sid):
    return c.post(f"/api/sessions/{sid}/clear")


def squash(c, sid):
    return c.post(f"/api/sessions/{sid}/compact")


def test_clear_writes_mark_and_next_turn_sees_nothing(c, fake_chat):
    sid = first_turn(c)
    r = clear(c, sid)
    assert (r.status_code, r.json()) == (201, {"seq": 2})
    assert _rows(c, sid)[-1]["role"] == "clear"
    post_discuss(c, "mini", sid, "重來")
    assert "<history>" not in fake_chat.calls[-1][1] and "結尾太快?" not in fake_chat.calls[-1][1]


def test_clear_twice_is_nothing_to_clear(c):
    sid = first_turn(c)
    clear(c, sid)
    r = clear(c, sid)
    assert (r.status_code, r.json()["code"]) == (422, "nothing-to-clear")


def test_clear_unknown_session_404(c):
    assert clear(c, "nosuch").json()["code"] == "unknown-session"
    assert squash(c, "nosuch").json()["code"] == "unknown-session"


def test_clear_then_compact_is_nothing_to_compact(c, fake_chat):
    sid = first_turn(c)
    clear(c, sid)
    n = len(fake_chat.calls)
    r = squash(c, sid)
    assert (r.status_code, r.json()["code"]) == (422, "nothing-to-compact")
    assert len(fake_chat.calls) == n


def test_compact_twice_in_a_row_is_nothing_to_compact(c, fake_chat):
    sid = first_turn(c)
    assert squash(c, sid).status_code == 201
    n = len(fake_chat.calls)
    assert squash(c, sid).json()["code"] == "nothing-to-compact"
    assert len(fake_chat.calls) == n


def test_compact_writes_summary_and_recipe(c, fake_chat):
    sid = first_turn(c)
    fake_chat.deltas = ["摘", "要"]
    r = squash(c, sid)
    assert (r.status_code, r.json()) == (201, {"seq": 2, "text": "摘要"})
    mark = _rows(c, sid)[-1]
    assert (mark["role"], mark["text"], mark["origin"], mark["anchors"]) == ("compact", "摘要", "den", [])
    assert mark["usage"]["output"] == 7 and mark["recipe"]["run"] == compact.COMPACT_RUN.as_dict()
    assert compact.COMPACT_RUN.as_dict() == {"model": "sonnet", "effort": "medium"}
    assert "作者:結尾太快?" in fake_chat.calls[-1][1] and "你:AB" in fake_chat.calls[-1][1]
    post_discuss(c, "mini", sid, "接著")
    assert "摘要" in fake_chat.calls[-1][1] and "結尾太快?" not in fake_chat.calls[-1][1]


def test_compact_reads_raw_turns_not_previous_summary(c, fake_chat):
    sid = first_turn(c)
    clear(c, sid)
    post_discuss(c, "mini", sid, "u1")
    fake_chat.deltas = ["第一次摘要"]
    squash(c, sid)
    fake_chat.deltas = ["a2"]
    post_discuss(c, "mini", sid, "u2")
    squash(c, sid)
    sent = fake_chat.calls[-1][1]
    assert "u1" in sent and "u2" in sent and "第一次摘要" not in sent and "結尾太快?" not in sent


def test_compact_failure_writes_nothing(c, fake_chat):
    sid = first_turn(c)
    fake_chat.outcome = "crash"
    r = squash(c, sid)
    assert (r.status_code, r.json()["code"]) == (502, "compact-failed")
    assert len(_rows(c, sid)) == 2


def test_compact_truncates_long_summary(c, fake_chat, monkeypatch, caplog):
    monkeypatch.setattr(compact, "COMPACT_MAX_CHARS", 3)
    sid = first_turn(c)
    fake_chat.deltas = ["一二三四五"]
    assert squash(c, sid).json()["text"] == "一二三"
    assert "event=compact-truncated" in caplog.text


def test_clear_and_compact_busy_while_turn_running(c, fake_chat):
    sid = first_turn(c)
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "卡住"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert (clear(c, sid).status_code, squash(c, sid).status_code) == (409, 409)
        assert c.post(f"/api/sessions/{sid}/compact").json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)


def test_turn_busy_while_compact_running(c, fake_chat):
    sid = first_turn(c)
    fake_chat.hang = True
    t = threading.Thread(target=squash, args=(c, sid), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert c.post("/api/discuss", json={"session_id": sid, "message": "插隊"}).status_code == 409
    finally:
        fake_chat.release.set()
    t.join(5)


def test_clear_keeps_attachments_in_context(c, fake_chat):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    clear(c, sid)
    events(free(c, sid, "還在嗎"))
    assert SEA in fake_chat.calls[-1][0]


def test_transcript_marks_version_change():
    rows = [{"seq": 0, "role": "user", "text": "a", "ts": 1.0, "recipe": None},
            {"seq": 1, "role": "assistant", "text": "b", "ts": 2.0, "recipe": {"v": 1}},
            {"seq": 2, "role": "user", "text": "c", "ts": 3.0, "recipe": None},
            {"seq": 3, "role": "assistant", "text": "d", "ts": 4.0, "recipe": {"v": 2}}]
    assert compact.transcript(rows, [{"n": 1, "created_at": 0.0}, {"n": 2, "created_at": 2.5}]) == \
        "作者:a\n你:b\n(這裡起你讀的是第 2 版;前面的對話對著的是第 1 版。)\n作者:c\n你:d"


def test_transcript_marks_between_assistant_only_turns():
    rows = [{"seq": 0, "role": "assistant", "text": "a", "ts": 1.0, "recipe": {"v": 1}},
            {"seq": 1, "role": "assistant", "text": "b", "ts": 3.0, "recipe": {"v": 2}}]
    assert "第 2 版" in compact.transcript(rows)


def test_transcript_without_versions_is_plain():
    rows = [{"seq": 0, "role": "user", "text": "a", "ts": 1.0, "recipe": None}]
    assert compact.transcript(rows) == "作者:a"


def _ledger(c):
    return in_loop(c, lambda conn: repo.calls_since(conn, 0))


def test_compact_links_seq(c):
    sid = first_turn(c)
    seq = squash(c, sid).json()["seq"]
    row = _ledger(c)[-1]
    d = in_loop(c, lambda conn: repo.discussion_by_session(conn, sid))
    assert (row["kind"], row["outcome"], row["discussion_id"], row["seq"]) == ("compact", "ok", d["id"], seq)
    assert set(row["sizes"]) == {"compact"}


def test_compact_empty_is_discarded(c, fake_chat):
    sid = first_turn(c)
    fake_chat.deltas = []
    assert squash(c, sid).status_code == 502
    row = _ledger(c)[-1]
    assert (row["kind"], row["outcome"], row["seq"]) == ("compact", "discarded", None)


def test_compact_error_outcome_kept(c, fake_chat):
    sid = first_turn(c)
    fake_chat.outcome = "timeout"
    assert squash(c, sid).status_code == 502
    assert _ledger(c)[-1]["outcome"] == "timeout"
