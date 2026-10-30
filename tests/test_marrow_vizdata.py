"""marrow.vizdata:viz 純組裝。golden 是搬家前由舊 viz.py 路徑產出的 viz.expected.json。"""
import copy
import json
from pathlib import Path

from marrow import vizdata
from marrow.repo import canonical_json

MINI = Path(__file__).parent / "fixtures" / "mini"


def _load():
    analysis = json.loads((MINI / "analysis.json").read_text(encoding="utf-8"))
    feedback = json.loads((MINI / "feedback.vizdata.json").read_text(encoding="utf-8"))
    source = (MINI / "source.md").read_text(encoding="utf-8")
    return analysis, feedback, source


def test_viz_payload_matches_golden():
    analysis, feedback, source = _load()
    expected = json.loads((MINI / "viz.expected.json").read_text(encoding="utf-8"))
    assert vizdata.viz_payload("mini", analysis, feedback, source) == expected


def test_viz_payload_does_not_mutate_inputs():
    analysis, feedback, source = _load()
    before = (canonical_json(analysis), canonical_json(feedback))
    vizdata.viz_payload("mini", analysis, feedback, source)
    assert (canonical_json(analysis), canonical_json(feedback)) == before


def test_viz_payload_without_feedback():
    analysis, _, source = _load()
    assert vizdata.viz_payload("mini", analysis, None, source)["feedback"] is None


NOTES = {"slug": "mini", "read": "一個人回到空屋。", "one_line": "燈等的是誰。", "points": [
    {"kind": "confused", "title": "燈為誰亮", "quotes": ["像在等誰"], "refs": ["k1"],
     "body": "以為有人要回來。", "question": "燈在等的是誰?"},
    {"kind": "moved", "title": "關燈", "quotes": ["他把燈關了。"], "refs": None,
     "body": "一個動作收掉整篇。", "question": None}]}


def test_notes_as_feedback_splits_moved():
    fb = vizdata.notes_as_feedback(NOTES)
    assert fb["read"] == "一個人回到空屋。" and fb["one_line"] == "燈等的是誰。" and fb["minor"] == []
    assert [p["title"] for p in fb["key_points"]] == ["燈為誰亮"]
    assert [p["title"] for p in fb["strengths"]] == ["關燈"]
    assert fb["key_points"][0]["experiment"] is None
    assert fb["key_points"][0]["question"] == "燈在等的是誰?" and fb["key_points"][0]["refs"] == ["k1"]
    assert "kind" not in fb["key_points"][0]


def _art(sv, body):
    return {"source_version_id": sv, "body": body}


def test_pick_judgment_prefers_same_version_notes():
    fb = {"read": "舊"}
    assert vizdata.pick_judgment(_art(2, {}), _art(2, NOTES), _art(2, fb)) == vizdata.notes_as_feedback(NOTES)


def test_pick_judgment_skips_stale_notes_falls_back_to_same_version_feedback():
    fb = {"read": "舊"}
    assert vizdata.pick_judgment(_art(2, {}), _art(1, NOTES), _art(2, fb)) == fb


def test_pick_judgment_none_when_both_stale_or_missing():
    assert vizdata.pick_judgment(_art(2, {}), _art(1, NOTES), _art(1, {"read": "舊"})) is None
    assert vizdata.pick_judgment(_art(2, {}), None, None) is None
