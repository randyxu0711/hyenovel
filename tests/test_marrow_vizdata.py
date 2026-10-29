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
