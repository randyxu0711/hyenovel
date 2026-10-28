"""marrow.schema:strict v1(spec §8 R5)與 v0→v1 轉換。

strict = 每個 object `additionalProperties: false` 且所有 property 都在 `required`;
v0 的可選欄位在 v1 改成可為 null,轉換時缺的補 None。
"""
import json
from pathlib import Path

import pytest

from marrow import schema

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

MINIMAL_FEEDBACK = {
    "slug": "mini", "read": "讀", "one_line": "改一件",
    "key_points": [{"title": "點", "quotes": ["引"], "body": "說"}],
}


def _mini():
    return json.loads((FIXTURES / "mini/analysis.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["analysis", "feedback"])
def test_v1_schemas_are_strict(kind):
    assert schema.strict_violations(schema.load_schema(kind)) == []


def test_strict_checker_catches_optional_and_open_objects():
    bad = {"type": "object", "properties": {"a": {}, "b": {}}, "required": ["a"],
           "$defs": {"d": {"type": "object", "properties": {"x": {}}, "required": ["x"],
                           "additionalProperties": False}}}
    assert len(schema.strict_violations(bad)) == 2          # 缺 additionalProperties + b 非 required


def test_v0_is_not_strict():                                 # 鎖住 R5 查證的事實:v0 確實需要轉換
    v0 = json.loads((REPO / "schemas/analysis.schema.json").read_text(encoding="utf-8"))
    assert schema.strict_violations(v0) != []


def test_fixture_analysis_converts_and_validates():
    v0 = _mini()
    v1 = schema.to_v1("analysis", v0)
    assert schema.validate_v1("analysis", v1) == []
    assert "title" in v1 and all("note" in n and "evidence" in n for n in v1["nodes"])
    assert all("note" in ev for n in v1["nodes"] for ev in (n["evidence"] or []))
    assert all("note" in e for e in v1["edges"])
    assert v0 == _mini()                                     # 不改原物件


def test_multi_fixtures_convert():
    paths = sorted((FIXTURES / "multi").glob("*/analysis.json"))
    assert paths
    for p in paths:
        v1 = schema.to_v1("analysis", json.loads(p.read_text(encoding="utf-8")))
        assert schema.validate_v1("analysis", v1) == []


def test_feedback_minimal_converts():
    v1 = schema.to_v1("feedback", MINIMAL_FEEDBACK)
    assert v1["strengths"] is None and v1["minor"] is None
    assert v1["key_points"][0]["refs"] is None
    assert schema.validate_v1("feedback", v1) == []


def test_existing_values_kept():
    v1 = schema.to_v1("feedback", {**MINIMAL_FEEDBACK, "minor": ["枝節"]})
    assert v1["minor"] == ["枝節"]


def test_v1_rejects_missing_key():
    v1 = schema.to_v1("analysis", _mini())
    del v1["synopsis"]
    assert schema.validate_v1("analysis", v1) != []


def test_v1_rejects_unknown_key():                           # to_v1 不刪多餘欄位,讓 validate 擋
    v1 = schema.to_v1("feedback", {**MINIMAL_FEEDBACK, "extra": 1})
    assert v1["extra"] == 1 and schema.validate_v1("feedback", v1) != []
