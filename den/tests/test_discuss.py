from den.discuss import render_turn


def test_render_turn_first_turn_is_just_message():
    assert render_turn([], "這篇的結尾太快?") == "這篇的結尾太快?"


def test_render_turn_wraps_history_and_marks_new_message():
    out = render_turn([{"role": "user", "text": "A"}, {"role": "assistant", "text": "B"}], "C")
    assert out.index("A") < out.index("B") < out.index("C")
    assert "<history>" in out and "</history>" in out
    assert out.rstrip().endswith("C")              # 新訊息在最後、在歷史區塊之外
    assert "作者:A" in out and "你:B" in out


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
