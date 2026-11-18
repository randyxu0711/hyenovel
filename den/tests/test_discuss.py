from den.discuss import ATTACHED, annotate, live_history, note_at, render_turn, since_clear


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


def test_note_at_clamps_to_history_length():
    assert (note_at(3, 4), note_at(4, 4), note_at(5, 0), note_at(0, 4)) == (3, 4, 0, 0)


def test_note_depth_zero_sits_right_before_the_author():
    out = render_turn([_u(0, "user", "A"), _u(1, "assistant", "B")], "C", ["引"], notes="筆記", note="N")
    assert out.index("</history>") < out.index("「引」") < out.index("N\n作者這一輪說:")


def test_note_on_first_turn_without_block():
    assert render_turn([], "嗨", note="N") == "N\n\n作者這一輪說:\n嗨"


def test_note_depth_counts_utterances_inside_history():
    h = [_u(i, "user" if i % 2 == 0 else "assistant", f"T{i}") for i in range(5)]
    out = render_turn(h, "C", note="N", note_depth=2)
    assert out.index("<history>") < out.index("T2") < out.index("N") < out.index("T3") < out.index("</history>")
    assert out.count("N") == 1


def test_note_goes_before_the_whole_utterance_group():
    h = [_u(0, "user", "A"), {**_u(1, "user", "B"), "quotes": ["引"]}, _u(2, "assistant", "D")]
    out = render_turn(h, "C", attached=[{"n": 1, "seq": 1, "name": "海"}], note="N", note_depth=2)
    assert out.index("作者:A") < out.index("N") < out.index(ATTACHED.format(name="海")) \
        < out.index("「引」") < out.index("作者:B")


def test_note_at_history_length_goes_before_the_first_utterance():
    out = render_turn([_u(0, "user", "A")], "C", summary="S", note="N", note_depth=1)
    assert out.index("</summary>") < out.index("<history>") < out.index("N") < out.index("作者:A")


def test_note_after_compact_with_empty_history():
    out = render_turn([], "嗨", summary="S", note="N")
    assert out.index("</summary>") < out.index("N") < out.index("作者這一輪說:")
    assert out.endswith("作者這一輪說:\n嗨")


def test_no_note_output_is_unchanged():
    h = [_u(0, "user", "A"), {**_u(1, "assistant", "B"), "quotes": ["q"]}]
    for args, kw in [(([], "C"), {}), (([], "C"), {"summary": "S"}), (([], "C", ["q"]), {"notes": "n"}),
                     ((h, "C"), {}), ((h, "C", ["q"]), {"notes": "n", "summary": "S"})]:
        assert render_turn(*args, **kw, note="") == render_turn(*args, **kw)


def _h(role, text, v, cmp=None, home="web"):
    return {"role": role, "text": text, "v": v, "cmp": cmp, "home": home}


def test_render_marks_version_boundary():
    out = render_turn([_h("user", "a", 1), _h("assistant", "b", 1)], "c", version=2)
    assert out.index("你:b") < out.index("(這裡起你讀的是第 2 版;前面的對話對著的是第 1 版。)") < out.index("作者這一輪說")


def test_render_no_marks_single_version():
    assert "(這裡起" not in render_turn([_h("user", "a", 1), _h("assistant", "b", 1)], "c", version=1)


def test_render_never_marks_inside_one_turn():
    h = [_h("user", "a", 1), _h("assistant", "b", 1), _h("user", "c", 2), _h("assistant", "d", 2)]
    out = render_turn(h, "e", version=2)
    assert out.index("你:b") < out.index("第 2 版") < out.index("作者:c")
    assert out.count("(這裡起") == 1


def test_render_marks_between_assistant_only_turns():
    out = render_turn([_h("assistant", "a", 1), _h("assistant", "b", 2)], "c", version=2)
    assert out.index("你:a") < out.index("第 2 版") < out.index("你:b")


def test_render_cmp_on_then_off():
    h = [_h("user", "a", 2), _h("assistant", "b", 2), _h("user", "c", 2, 1), _h("assistant", "d", 2, 1)]
    out = render_turn(h, "e", version=2, cmp=None)
    assert out.index("你:b") < out.index("(作者在這裡開始對照第 1 版。)") < out.index("作者:c") \
        < out.index("你:d") < out.index("(作者在這裡關掉了對照。)") < out.index("作者這一輪說")


def test_render_cmp_on_for_this_turn():
    out = render_turn([_h("user", "a", 2), _h("assistant", "b", 2)], "c", version=2, cmp=1)
    assert out.index("你:b") < out.index("開始對照第 1 版") < out.index("作者這一輪說")


def test_render_mcp_turn_is_not_cmp_off():
    h = [_h("user", "a", 2, 1), _h("assistant", "b", 2, 1)]
    assert "關掉了對照" not in render_turn(h, "c", version=2, cmp=None, home="mcp")
    assert "關掉了對照" not in render_turn([*h, _h("user", "c", 2, None, None), _h("assistant", "d", 2, None, None)],
                                     "e", version=2)


def test_render_old_rows_without_marks_info_are_quiet():
    out = render_turn([{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}], "c", version=2, cmp=1)
    assert "(這裡起" not in out and "對照" not in out


def test_old_quote_labelled_with_version():
    out = render_turn([], "這句", quotes=["沒有回頭", "門"], old_version=lambda q: 1 if q == "沒有回頭" else None)
    assert "「沒有回頭」(第 1 版的字,這版已經沒有)" in out and "「門」\n" in out + "\n"


def test_old_quote_labelled_in_history():
    h = [{**_h("user", "a", 2), "quotes": ["沒有回頭"]}, _h("assistant", "b", 2)]
    assert "「沒有回頭」(第 1 版的字,這版已經沒有)" in render_turn(h, "c", version=2, old_version=lambda q: 1)


VERS = [{"n": 1, "created_at": 10.0}, {"n": 2, "created_at": 20.0}]


def test_annotate_prefers_recipe_and_user_takes_its_reply():
    rows = [{"seq": 0, "role": "user", "ts": 25.0, "recipe": None},
            {"seq": 1, "role": "assistant", "ts": 26.0, "recipe": {"v": 1, "cmp": None, "home": "web"}}]
    assert [(r["v"], r["cmp"], r["home"]) for r in annotate(rows, VERS)] == [(1, None, "web"), (1, None, "web")]


def test_annotate_falls_back_to_ts_for_old_rows():
    rows = [{"seq": 0, "role": "user", "ts": 15.0, "recipe": None},
            {"seq": 1, "role": "assistant", "ts": 21.0, "recipe": {"retrieved": []}},
            {"seq": 2, "role": "user", "ts": 5.0, "recipe": None}]
    assert [(r["v"], r["cmp"], r["home"]) for r in annotate(rows, VERS)] == [(2, None, None), (2, None, None), (1, None, None)]


def test_annotate_without_versions():
    assert annotate([{"seq": 0, "role": "user", "ts": 1.0, "recipe": None}], [])[0]["v"] is None
