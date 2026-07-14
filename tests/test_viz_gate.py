"""引用閘門(擋幻覺的命脈)的性質。

⚠️ 閘門不是子字串比對,是**三層寬鬆匹配**(viz.py:locate):
  ① 逐字 find
  ② 標點正規化後 find(半形⇄全形、ASCII 引號與左右彎引號全部視為等價)
  ③ 忽略空白差異(非空白字元用 \\s* 連接成 regex)

所以「非子字串 → 必擋」是**錯的性質**:quote="他 說" vs source="他說"
不是子字串,但第三層會放行 —— 而那是刻意的正確行為(作者手打與子代理
產出的空白/標點差異不該被當成幻覺)。

正確的反向性質是:**含有原文裡根本不存在的「實字」→ 必擋**。
那才是幻覺引用的本質:編出原文沒有的字。
"""
from hypothesis import assume, given, settings
from hypothesis import strategies as st

import viz

# CJK 實字:不碰標點/空白正規化那兩層,所以「不在原文裡」是乾淨的判準
CJK = st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF)


def _norm(s: str) -> str:
    """viz._PUNCT 是 1:1 等長的 translate 表(故正規化後索引在原文仍有效)。"""
    return s.translate(viz._PUNCT)


@given(source=st.text(min_size=2), i=st.integers(min_value=0), j=st.integers(min_value=0))
@settings(max_examples=300)
def test_any_substring_of_source_is_accepted(source, i, j):
    """正向:從原文切出來的任一段,閘門必須放行(否則真引用被誤擋)。"""
    a, b = sorted((i % len(source), j % len(source)))
    assume(b > a)
    quote = source[a:b]
    assert viz.locate(quote, source) is not None, f"原文切片被誤擋:{quote!r}"


@given(source=st.text(min_size=2), i=st.integers(min_value=0), j=st.integers(min_value=0))
@settings(max_examples=300)
def test_span_is_within_source(source, i, j):
    """命中的座標必須落在原文範圍內、且 start < end(文本軸靠它定位)。"""
    a, b = sorted((i % len(source), j % len(source)))
    assume(b > a)
    span = viz.locate(source[a:b], source)
    assert span is not None
    start, end = span
    assert 0 <= start < end <= len(source), f"座標越界:{span} vs len={len(source)}"


@given(source=st.text(alphabet=CJK, min_size=5), extra=CJK)
@settings(max_examples=300)
def test_hallucinated_character_is_always_blocked(source, extra):
    """反向(幻覺的本質):quote 含有原文裡根本沒有的實字 → 必擋。

    這是整個產品可信度的地基:analyst 編造引用而閘門放行,
    整份分析就是廢的,而且不會有任何跡象。
    """
    assume(extra not in source)
    assume(_norm(extra) not in _norm(source))
    quote = source[:3] + extra          # 前半真、尾巴編造 —— 正是幻覺引用的樣子
    assert viz.locate(quote, source) is None, f"幻覺引用沒被擋:{quote!r}"


@given(source=st.text(min_size=2), i=st.integers(min_value=0), j=st.integers(min_value=0))
@settings(max_examples=300)
def test_punctuation_normalization_is_equivalence(source, i, j):
    """標點不變性:把 quote 的標點換成等價形式,仍須命中。

    這是刻意的寬容(子代理難辨 U+201C/U+201D、作者常混用半形全形),
    但「寬容」必須是等價,不能變成「什麼都放行」—— 那由上面的反向性質守住。
    """
    a, b = sorted((i % len(source), j % len(source)))
    assume(b > a)
    quote = source[a:b]
    assert viz.locate(quote, source) is not None
    assert viz.locate(_norm(quote), source) is not None, "正規化後的 quote 應等價命中"


def test_whitespace_difference_is_tolerated():
    """第三層:空白差異可容忍(換行/縮排不該被當幻覺)。"""
    source = "他走進門。屋裡沒有人。"
    assert viz.locate("他走進門。\n屋裡沒有人。", source) is not None


def test_validate_and_locate_reports_hallucination_and_marks_pos():
    """validate_and_locate:命中的寫座標(_pos ∈ [0,1]),沒命中的進 errors 且 _pos=None。"""
    source = "他走進門。屋裡沒有人。"
    analysis = {
        "nodes": [
            {"id": "b1", "type": "beat", "label": "進門",
             "evidence": [{"quote": "他走進門。"}]},
            {"id": "b2", "type": "beat", "label": "幻覺",
             "evidence": [{"quote": "他跳進海裡。"}]},
        ]
    }
    errors = viz.validate_and_locate(analysis, source)
    assert [e[0] for e in errors] == ["b2"], "只有 b2 該被判幻覺"

    ok_ev = analysis["nodes"][0]["evidence"][0]
    assert 0.0 <= ok_ev["_pos"] <= 1.0
    assert ok_ev["_start"] < ok_ev["_end"]

    bad_ev = analysis["nodes"][1]["evidence"][0]
    assert bad_ev["_pos"] is None and bad_ev["_start"] == -1


def test_validate_and_locate_tolerates_missing_evidence():
    """node 沒有 evidence(character 型別可選)→ 不得炸。"""
    analysis = {"nodes": [{"id": "c1", "type": "character", "label": "他"}]}
    assert viz.validate_and_locate(analysis, "他走進門。") == []
