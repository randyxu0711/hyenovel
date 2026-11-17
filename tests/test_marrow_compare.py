from marrow.compare import diff, pin, public, trace


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


def P(quotes, kind="moved"):
    return {"kind": kind, "title": "t", "body": "b", "question": None, "quotes": quotes}


def _trace(old, new, points):
    d = diff(old, new)
    return d, trace(points, old, new, d)


def test_kept_quote_maps_to_new_position():
    _, [p] = _trace("甲。乙丙丁。", "X甲。乙丙丁。", [P(["乙丙丁"])])
    q = p["quotes"][0]
    assert (p["fate"], p["label"], q["fate"], q["new"]) == ("kept", "kept", "kept", {"start": 3, "end": 6})
    assert (p["i"], p["kind"], p["title"], p["body"], p["question"]) == (0, "moved", "t", "b", None)


def test_moved_sentence_counts_as_kept():
    _, [p] = _trace("甲。乙丙丁。", "乙丙丁。甲。", [P(["乙丙丁"])])
    assert p["quotes"][0]["fate"] == "kept" and p["quotes"][0]["new"] == {"start": 0, "end": 3}


def test_changed_quote_has_new_text():
    _, [p] = _trace("數到第三遍,數字一樣。", "數到第三遍,我沒在記。", [P(["數字一樣"], "confused")])
    q = p["quotes"][0]
    assert (q["fate"], q["new"], q["new_text"], q["del"]) == ("changed", {"start": 6, "end": 10}, "我沒在記", "d0")
    assert (p["fate"], p["label"]) == ("changed", "changed")


def test_partly_kept_quote_is_changed():
    _, [p] = _trace("她看了很久很久。", "她看了一下。", [P(["她看了很久"])])
    q = p["quotes"][0]
    assert q["fate"] == "changed" and q["new"]["start"] == 0 and q["new_text"].startswith("她看了")


def test_gone_quote_points_to_del_run():
    _, [p] = _trace("甲。她看了很久。乙。", "甲。乙。", [P(["她看了很久"])])
    q = p["quotes"][0]
    assert (q["fate"], q["new"], q["new_text"], q["del"], p["label"]) == ("gone", None, None, "d0", "gone")
    assert q["old"] == {"start": 2, "end": 7}


def test_mixed_point_label():
    _, [p] = _trace("甲甲。乙乙。", "甲甲。", [P(["甲甲", "乙乙"], "wondering")])
    assert (p["fate"], p["label"]) == ("changed", "mixed")


def test_lost_and_no_quote_are_untracked():
    _, ps = _trace("甲。", "甲。", [P(["不存在"]), P([]), P(["  "])])
    assert [(p["fate"], p["label"]) for p in ps] == [("untracked", None)] * 3
    assert ps[0]["quotes"][0] == {"quote": "不存在", "fate": "lost", "old": None, "new": None, "new_text": None, "del": None}


def test_lost_ignored_in_label():
    _, [p] = _trace("甲甲。", "甲甲。", [P(["甲甲", "不存在"])])
    assert (p["fate"], p["label"]) == ("kept", "kept")


def test_fate_uses_first_occurrence_in_old():
    _, [p] = _trace("乙乙。甲。乙乙。", "甲。乙乙。", [P(["乙乙"])])
    assert p["quotes"][0]["fate"] == "kept"


def test_missing_optional_fields_default_none():
    d = diff("甲。", "甲。")
    [p] = trace([{"kind": "moved", "title": "t", "quotes": None}], "甲。", "甲。", d)
    assert (p["body"], p["question"], p["quotes"], p["fate"]) == (None, None, [], "untracked")


def test_pin_marks_runs_under_quotes():
    d, ps = _trace("甲。她看了很久。乙。" + "長" * 40 + "。", "甲。乙。", [P(["她看了很久"])])
    pin(d["runs"], ps)
    assert [r["pinned"] for r in d["runs"] if r["op"] == "del"] == [True, False]


def test_public_drops_internal_fields():
    d = diff("甲。乙。", "甲。")
    pin(d["runs"], [])
    out = public(d)
    assert set(out) == {"runs", "hunks", "same"}
    assert out["runs"][0] == {"op": "del", "id": "d0", "at": 2, "text": "乙。", "chars": 2, "pinned": False}
    assert "old" in d["runs"][0]


def test_pin_leaves_ins_runs_alone():
    d, ps = _trace("甲。", "甲。乙。", [P(["甲"])])
    pin(d["runs"], ps)
    assert "pinned" not in d["runs"][0]
