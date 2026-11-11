from den.discuss import ATTACHED, live_history, render_turn, since_clear


def test_render_turn_first_turn_is_just_message():
    assert render_turn([], "這篇的結尾太快?") == "這篇的結尾太快?"


def test_render_turn_wraps_history_and_marks_new_message():
    out = render_turn([{"role": "user", "text": "A"}, {"role": "assistant", "text": "B"}], "C")
    assert out.index("A") < out.index("B") < out.index("C")
    assert "<history>" in out and "</history>" in out
    assert out.rstrip().endswith("C")              # 新訊息在最後、在歷史區塊之外
    assert "作者:A" in out and "你:B" in out


def test_render_turn_labels_other_characters_replies_by_name():
    out = render_turn([{"role": "user", "text": "A"},
                       {"role": "assistant", "text": "B", "character": "hyena"},
                       {"role": "assistant", "text": "C", "character": "deer"}], "D",
                      others={"hyena": "鬣狗"})
    assert "另一位讀伴(鬣狗):B" in out and "你:C" in out
    assert "你:B" not in out


def test_render_turn_includes_quotes_block():
    out = render_turn([], "這句怎麼樣?", ["整條街只有他那盞燈還亮著", "他把燈關了"])
    assert out.index("作者指著原文的這幾段:") < out.index("「整條街只有他那盞燈還亮著」") \
        < out.index("「他把燈關了」") < out.index("作者這一輪說:")
    assert out.rstrip().endswith("這句怎麼樣?")


def test_render_turn_restores_past_quotes_in_history():
    out = render_turn([{"role": "user", "text": "A", "quotes": ["引一"]},
                       {"role": "assistant", "text": "B", "quotes": None}], "C")
    assert out.index("作者指著原文的這幾段:") < out.index("「引一」") < out.index("作者:A") < out.index("你:B")
    assert out.count("作者指著原文的這幾段:") == 1


def test_render_turn_puts_notes_before_the_message_on_first_turn():
    out = render_turn([], "這句?", notes="筆記一\n筆記二")
    assert out == "筆記一\n筆記二\n\n作者這一輪說:\n這句?"


def test_render_turn_puts_notes_after_history_and_before_quotes():
    out = render_turn([{"role": "user", "text": "A"}], "B", ["引"], notes="筆記")
    assert out.index("</history>") < out.index("筆記") < out.index("作者指著原文") < out.index("作者這一輪說:")


def _u(seq, role, text=""):
    return {"seq": seq, "role": role, "text": text}


def test_live_history_after_clear_is_empty():
    assert live_history([_u(0, "user", "A"), _u(1, "assistant", "B"), _u(2, "clear")]) == (None, [])


def test_live_history_after_compact_keeps_summary_and_tail():
    us = [_u(0, "user", "A"), _u(1, "assistant", "B"), _u(2, "compact", "摘"), _u(3, "user", "C"), _u(4, "assistant", "D")]
    assert live_history(us) == ("摘", us[3:])
    assert live_history(us[:2]) == (None, us[:2])


def test_since_clear_ignores_compact_marks():
    u1, u2 = _u(2, "user", "u1"), _u(4, "user", "u2")
    us = [_u(0, "user", "old"), _u(1, "clear"), u1, _u(3, "compact", "摘"), u2]
    assert since_clear(us) == [u1, u2]
    assert since_clear([u1]) == [u1]


def test_live_history_never_returns_marks():
    us = [_u(0, "user", "A"), _u(1, "compact", "x"), _u(2, "assistant", "B"), _u(3, "clear"),
          _u(4, "user", "C"), _u(5, "compact", "y"), _u(6, "assistant", "D")]
    for got in (live_history(us)[1], live_history(us[:3])[1], since_clear(us)):
        assert {u["role"] for u in got} <= {"user", "assistant"}


def test_render_turn_with_summary_only():
    out = render_turn([], "C", summary="之前聊過海")
    assert out == "之前的對話摘要:\n<summary>\n之前聊過海\n</summary>\n\n作者這一輪說:\nC"


def test_render_turn_with_summary_and_history():
    out = render_turn([_u(3, "user", "A")], "C", summary="摘")
    assert out.index("<summary>") < out.index("</summary>") < out.index("<history>") < out.index("作者:A")


def test_render_turn_without_summary_unchanged():
    h = [{"role": "user", "text": "A"}, {"role": "assistant", "text": "B"}]
    assert render_turn(h, "C", summary=None) == render_turn(h, "C")
    assert render_turn([], "C", summary="") == "C"


def test_render_turn_marks_attachment_in_history():
    live = [_u(4, "user", "看這篇"), _u(5, "assistant", "好")]
    out = render_turn(live, "C", attached=[{"n": 1, "seq": 1, "name": "舊"}, {"n": 2, "seq": 4, "name": "海"}])
    assert out.index(ATTACHED.format(name="海")) < out.index("作者:看這篇")
    assert "舊" not in out
