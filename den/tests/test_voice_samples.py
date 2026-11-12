import json

import pytest

from den import companion
from den.config import MAX_VOICE_SAMPLE_CHARS, MAX_VOICE_SAMPLES
from den.tests.test_app_discuss import c, events, fake_chat, in_loop  # noqa: F401
from den.tests.test_regenerate import regen_events
from den.tests.test_reply_edit import edit


def _say(c, message="結尾太快?", sid=None, character=None):
    body = {"session_id": sid, "message": message, "anchors": [], **({"character": character} if character else {})}
    return events(c.post("/api/discuss/mini", json=body))[-1]["data"]["session_id"]


def voice(c, sid, seq=1):
    assert c.put(f"/api/sessions/{sid}/turns/{seq}/voice").status_code == 204


def system(fake_chat):
    return fake_chat.calls[-1][0]


def test_no_marks_means_no_sample_layers(c, fake_chat):
    _say(c)
    assert "這位作者認得的你" not in system(fake_chat)


def test_marked_reply_reaches_other_sessions_after_examples(c, fake_chat):
    fake_chat.deltas = ["像它的那句"]
    a = _say(c, "燈呢")
    voice(c, a)
    fake_chat.deltas = ["AB"]
    _say(c)
    s = system(fake_chat)
    assert "<example>\n作者:燈呢\n鬣狗:像它的那句\n</example>\n" in s
    assert s.index("你平常怎麼說話") < s.index("這位作者認得的你") < s.index("像它的那句")


def test_samples_are_material_not_instructions(c, fake_chat):
    _say(c)
    plain = in_loop(c, lambda conn: conn.execute(
        "SELECT recipe FROM utterance WHERE role='assistant' ORDER BY ts DESC LIMIT 1").fetchone()[0])
    a = _say(c)
    voice(c, a)
    _say(c)
    marked = in_loop(c, lambda conn: conn.execute(
        "SELECT recipe FROM utterance WHERE role='assistant' ORDER BY ts DESC LIMIT 1").fetchone()[0])
    p, m = json.loads(plain)["prompt"], json.loads(marked)["prompt"]
    assert "samples" in m["material"] and "samples" not in p["material"]
    assert m["layers"]["samples_header"] and "samples" not in m["layers"]


def test_own_session_is_excluded(c, fake_chat):
    fake_chat.deltas = ["自己這局"]
    a = _say(c)
    voice(c, a)
    _say(c, "再說", sid=a)
    assert "這位作者認得的你" not in system(fake_chat)


def test_other_character_and_unmarked_and_shelved_do_not_flow(c, fake_chat):
    fake_chat.deltas = ["鹿說的"]
    d = _say(c, character="deer")
    voice(c, d)
    fake_chat.deltas = ["換下去的"]
    h = _say(c)
    voice(c, h)
    fake_chat.deltas = ["新版"]
    regen_events(c, h, 1)
    u = _say(c)
    voice(c, u)
    c.delete(f"/api/sessions/{u}/turns/1/voice")
    _say(c)
    assert "這位作者認得的你" not in system(fake_chat)


def test_sample_is_the_current_text(c, fake_chat):
    a = _say(c)
    voice(c, a)
    edit(c, a, 1, "改過的樣子")
    _say(c)
    assert "鬣狗:改過的樣子" in system(fake_chat)


def test_deleted_session_samples_disappear_and_card_export_has_none(c, fake_chat):
    fake_chat.deltas = ["會被刪的"]
    a = _say(c)
    voice(c, a)
    c.post(f"/api/sessions/{a}/archive")
    c.delete(f"/api/sessions/{a}")
    _say(c)
    assert "會被刪的" not in system(fake_chat)
    b = _say(c)
    voice(c, b)
    assert "AB" not in str(c.get("/api/characters/hyena/export").json())


def test_redo_bytes_hold_with_samples(c, fake_chat):
    a = _say(c)
    voice(c, a)
    b = _say(c)
    first = fake_chat.calls[-1]
    regen_events(c, b, 1)
    assert fake_chat.calls[-1] == first and "這位作者認得的你" in first[0]


def _row(text, prompt=None):
    return {"text": text, "prompt": prompt}


def test_pick_samples_limits():
    many = [_row(str(i)) for i in range(MAX_VOICE_SAMPLES + 2)]
    assert companion.pick_samples(many) == many[:MAX_VOICE_SAMPLES]
    big = _row("字" * (MAX_VOICE_SAMPLE_CHARS + 1))
    half = _row("字" * (MAX_VOICE_SAMPLE_CHARS // 2), "問")
    assert companion.pick_samples([big, half, half, _row("短")]) == [half]
    assert companion.pick_samples([]) == []


@pytest.mark.parametrize("prompt", [None, "問"])
def test_sample_size_counts_the_author_line(prompt):
    r = _row("字" * MAX_VOICE_SAMPLE_CHARS, prompt)
    assert companion.pick_samples([r]) == ([r] if prompt is None else [])
