from marrow.compare import diff


def test_identical_after_whitespace_and_punct_is_same():
    d = diff("甲,乙。\n丙。", "甲，乙。 \n\n丙。")
    assert d["same"] and d["runs"] == [] and d["hunks"] == []


def test_in_sentence_char_change():
    d = diff("數到第三遍,數字一樣。", "數到第三遍,我沒在記。")
    assert d["runs"] == [
        {"op": "del", "id": "d0", "at": 6, "text": "數字一樣", "chars": 4, "old": {"start": 6, "end": 10}},
        {"op": "ins", "id": "i0", "start": 6, "end": 10},
    ]
    assert d["hunks"] == [{"ids": ["d0", "i0"], "at": 6}]


def test_whole_paragraph_delete():
    d = diff("甲。\n乙。\n丙。", "甲。\n丙。")
    [r] = d["runs"]
    assert r == {"op": "del", "id": "d0", "at": 3, "text": "乙。\n", "chars": 2, "old": {"start": 3, "end": 6}}


def test_insert_only():
    d = diff("甲。丙。", "甲。乙。丙。")
    assert d["runs"] == [{"op": "ins", "id": "i0", "start": 2, "end": 4}]


def test_runs_sorted_del_before_ins_at_same_place():
    d = diff("她想起父親。", "父親站著。")
    at = [(r.get("at", r.get("start")), r["op"]) for r in d["runs"]]
    assert at == sorted(at, key=lambda x: (x[0], x[1] != "del"))


def test_hunk_groups_adjacent_runs_only():
    d = diff("一二三。四五六。七八九。", "一X三。四五六。七Y九。")
    assert len(d["hunks"]) == 2
    assert [h["ids"] for h in d["hunks"]] == [["d0", "i0"], ["d1", "i1"]]


def test_runs_count_code_points_beyond_bmp():
    d = diff("😀甲。", "😀乙。")
    assert any(r["op"] == "ins" and (r["start"], r["end"]) == (1, 2) for r in d["runs"])


def test_pairs_map_equal_chars():
    d = diff("甲乙丙", "X甲乙丙")
    assert d["pairs"][0] == 1 and d["pairs"][2] == 3


def test_deleted_last_paragraph_attaches_at_end():
    d = diff("甲。\n乙。", "甲。")
    [r] = d["runs"]
    assert r["op"] == "del" and r["at"] == 2 and r["text"].strip() == "乙。"


def test_deleted_first_paragraph():
    d = diff("甲。\n乙。", "乙。")
    [r] = d["runs"]
    assert (r["at"], r["text"]) == (0, "甲。\n")


def test_deleted_last_paragraph_with_trailing_newline_starts_own_paragraph():
    d = diff("甲。\n乙。\n", "甲。")
    [r] = d["runs"]
    assert (r["at"], r["text"]) == (2, "\n乙。")


def test_blank_lines_and_closing_quotes_stay_in_sentence():
    d = diff("「走吧。」她說。\n\n甲。", "「走吧。」她說。\n甲。")
    assert d["same"]


def test_everything_deleted():
    d = diff("甲。", "")
    assert [(r["op"], r["at"], r["text"]) for r in d["runs"]] == [("del", 0, "甲。")]
