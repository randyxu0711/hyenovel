"""den.spans:對話文字裡的「」引文與其在原文的位移。"""
from den import spans


def test_quotes_in_basic_and_min_length():
    assert spans.quotes_in("他說「海很深」,又說「浪」。") == ["海很深"]


def test_quotes_in_nested_and_unpaired_skipped():
    assert spans.quotes_in("「一「二」三」") == []
    assert spans.quotes_in("「海很深「山很高」尾」") == []
    assert spans.quotes_in("「沒收尾") == []
    assert spans.quotes_in("沒開頭」") == []


def test_quotes_in_length_bounds():
    assert spans.quotes_in("「" + "字" * 400 + "」") == ["字" * 400]
    assert spans.quotes_in("「" + "字" * 401 + "」") == []


def test_quotes_in_dedup_keeps_order():
    assert spans.quotes_in("「海很深」「山很高」「海很深」") == ["海很深", "山很高"]


def test_quotes_in_skips_blank_and_punctuation_only():
    assert spans.quotes_in("「……」「  」「，。！」「 …… 」") == []


def test_locate_all_first_occurrence():
    assert spans.locate_all(["海很深"], "海很深。海很深。")[0] == {"quote": "海很深", "start": 0, "end": 3}


def test_locate_all_loose_punctuation_and_missing():
    [a, b] = spans.locate_all(["他走進門.屋裡", "不存在的話"], "他走進門。屋裡沒有人。")
    assert (a["start"], a["end"]) == (0, 7)
    assert b == {"quote": "不存在的話", "start": None, "end": None}


def test_locate_all_beyond_bmp_counts_code_points():
    assert spans.locate_all(["石頭"], "𠀋石頭")[0]["start"] == 1
