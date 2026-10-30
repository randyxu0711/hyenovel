"""marrow.gate:三層引文匹配 + v1 閘門(node id 完整性、引文、refs)。"""
import copy
import json
from pathlib import Path

import pytest

import viz
from marrow import gate, schema

MINI = Path(__file__).parent / "fixtures" / "mini"


@pytest.fixture
def source():
    return (MINI / "source.md").read_text(encoding="utf-8")


@pytest.fixture
def analysis():
    return schema.to_v1("analysis", json.loads((MINI / "analysis.json").read_text(encoding="utf-8")))


@pytest.fixture
def feedback(feedback_json):
    return schema.to_v1("feedback", feedback_json)


def test_locate_moved_unchanged():
    assert viz.locate is gate.locate


def test_gate_analysis_passes_fixture(analysis, source):
    assert gate.gate_analysis(analysis, source) == []


def test_gate_analysis_bad_quote(analysis, source):
    a = copy.deepcopy(analysis)
    a["nodes"][1]["evidence"][0]["quote"] = "原文沒有這句"
    errs = gate.gate_analysis(a, source)
    assert len(errs) == 1
    assert errs[0].startswith("node ") and "引文在原文找不到" in errs[0]


def test_gate_analysis_dangling_edge(analysis, source):
    a = copy.deepcopy(analysis)
    a["edges"].append({"type": "relates_to", "from": "k1", "to": "zz", "note": None})
    assert "edge k1->zz: 端點 zz 不存在" in gate.gate_analysis(a, source)


def test_gate_analysis_dangling_from(analysis, source):
    a = copy.deepcopy(analysis)
    a["edges"].append({"type": "relates_to", "from": "yy", "to": "k1", "note": None})
    assert "edge yy->k1: 端點 yy 不存在" in gate.gate_analysis(a, source)


def test_gate_analysis_duplicate_id(analysis, source):
    a = copy.deepcopy(analysis)
    a["nodes"].append(copy.deepcopy(a["nodes"][0]))
    assert "node b1: id 重複" in gate.gate_analysis(a, source)


def test_gate_analysis_schema_error_still_checks_quotes(analysis, source):
    a = copy.deepcopy(analysis)
    del a["synopsis"]
    a["nodes"][0]["evidence"][0]["quote"] = "原文沒有這句"
    errs = gate.gate_analysis(a, source)
    assert any(e.startswith("schema: ") for e in errs)
    assert any("引文在原文找不到" in e for e in errs)


@pytest.mark.parametrize("body", [
    {"nodes": "x"},
    {"nodes": ["x", {"id": "a", "evidence": "y"}, {"id": "b", "evidence": ["z", {"quote": 3}]}],
     "edges": "x"},
    {"nodes": [{"id": "a"}], "edges": ["x"]},
    [],
])
def test_gate_analysis_malformed_shape_no_raise(body, source):
    assert gate.gate_analysis(body, source)


def test_gate_feedback_passes(feedback, analysis, source):
    assert gate.gate_feedback(feedback, analysis, source) == []


def test_gate_feedback_bad_ref(feedback, analysis, source):
    f = copy.deepcopy(feedback)
    f["key_points"][0]["refs"] = ["zz"]
    errs = gate.gate_feedback(f, analysis, source)
    assert any("refs zz 不是存在的 node id" in e and e.startswith("feedback「收尾太快」") for e in errs)


def test_gate_feedback_bad_quote(feedback, analysis, source):
    f = copy.deepcopy(feedback)
    f["strengths"][0]["quotes"] = ["原文沒有這句"]
    errs = gate.gate_feedback(f, analysis, source)
    assert errs == ["feedback「燈的用法」: 引文在原文找不到:「原文沒有這句」"]


@pytest.mark.parametrize("fb,an", [
    ({"strengths": "x", "key_points": [1, {"quotes": "q", "refs": 5}]}, {"nodes": "x"}),
    ({"strengths": [{"title": "t", "quotes": [3], "refs": [4]}]}, {"nodes": ["x", {"id": 1}]}),
    ([], []),
])
def test_gate_feedback_malformed_shape_no_raise(fb, an, source):
    assert gate.gate_feedback(fb, an, source)


def test_errors_never_contain_fix(analysis, source):
    a = copy.deepcopy(analysis)
    a["nodes"][0]["evidence"][0]["quote"] = "原文沒有這句"
    first = source.split("。")[0]
    assert not any(first in e for e in gate.gate_analysis(a, source))


@pytest.mark.parametrize("blank", ["   ", "\n", "　", " 　\n"])
def test_gate_analysis_whitespace_only_quote_rejected(analysis, source, blank):
    a = copy.deepcopy(analysis)
    a["nodes"][1]["evidence"][0]["quote"] = blank
    assert any("引文在原文找不到" in e for e in gate.gate_analysis(a, source))


@pytest.mark.parametrize("blank", ["   ", "\n", "　", " 　\n"])
def test_gate_feedback_whitespace_only_quote_rejected(feedback, analysis, source, blank):
    f = copy.deepcopy(feedback)
    f["strengths"][0]["quotes"] = [blank]
    assert any("引文在原文找不到" in e for e in gate.gate_feedback(f, analysis, source))


def _notes(**point):
    p = {"kind": "confused", "title": "燈為誰亮", "quotes": ["像在等誰"], "refs": ["k1"],
         "body": "讀到這裡以為有人要回來,後面沒有接上。", "question": "燈在等的是誰?"}
    p.update(point)
    return {"slug": "mini", "read": "一個人回到空屋。", "points": [p], "one_line": "燈等的是誰。"}


def test_gate_notes_passes_valid(analysis, source):
    assert gate.gate_notes(_notes(), analysis, source) == []


def test_gate_notes_rejects_hallucinated_quote(analysis, source):
    errs = gate.gate_notes(_notes(quotes=["原文沒有這句"]), analysis, source)
    assert len(errs) == 1 and errs[0].startswith("筆記「燈為誰亮」") and "引文在原文找不到" in errs[0]


def test_gate_notes_rejects_unknown_ref(analysis, source):
    assert any("refs t99 不是存在的 node id" in e
               for e in gate.gate_notes(_notes(refs=["t99"]), analysis, source))


def test_gate_notes_rejects_bad_kind(analysis, source):
    assert any(e.startswith("schema:") for e in gate.gate_notes(_notes(kind="praise"), analysis, source))


def test_gate_notes_rejects_confidence_field(analysis, source):
    assert any(e.startswith("schema:") for e in gate.gate_notes(_notes(confidence=0.9), analysis, source))


def test_gate_notes_non_dict_body(analysis, source):
    errs = gate.gate_notes([], analysis, source)
    assert errs and all(e.startswith("schema:") for e in errs)
