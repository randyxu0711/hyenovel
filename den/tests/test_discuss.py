from den.discuss import render_turn


def test_render_turn_first_turn_is_just_message():
    assert render_turn([], "這篇的結尾太快?") == "這篇的結尾太快?"


def test_render_turn_wraps_history_and_marks_new_message():
    out = render_turn([{"role": "user", "text": "A"}, {"role": "assistant", "text": "B"}], "C")
    assert out.index("A") < out.index("B") < out.index("C")
    assert "<history>" in out and "</history>" in out
    assert out.rstrip().endswith("C")              # 新訊息在最後、在歷史區塊之外
    assert "作者:A" in out and "編輯:B" in out
