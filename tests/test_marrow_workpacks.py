"""marrow.workpacks:登錄表、無工具 prompt、輸入組裝、閘門分派。"""
import copy
import json
from pathlib import Path

import pytest

from marrow import schema, workpacks
from marrow.repo import canonical_json

MINI = Path(__file__).parent / "fixtures" / "mini"


@pytest.fixture
def source():
    return (MINI / "source.md").read_text(encoding="utf-8")


@pytest.fixture
def analysis():
    return schema.to_v1("analysis", json.loads((MINI / "analysis.json").read_text(encoding="utf-8")))


def test_registry_shape():
    assert set(workpacks.WORKPACKS) == {"analyst", "reviewer"}
    assert workpacks.WORKPACKS["analyst"].kind == "analysis"
    assert workpacks.WORKPACKS["reviewer"].kind == "notes"


@pytest.mark.parametrize("name", ["analyst", "reviewer"])
def test_registry_schemas_are_strict(name):
    wp = workpacks.WORKPACKS[name]
    assert wp.schema == schema.load_schema(wp.kind)
    assert schema.strict_violations(wp.schema) == []


@pytest.mark.parametrize("name", ["analyst", "reviewer"])
def test_prompts_are_toolless(name):
    # 只查人格段;附上的 schema 的 description 會提到 stories/<slug>/(那是說明,不是工具指示)
    p = workpacks.WORKPACKS[name].system_prompt.split("\n## 輸出格式\n")[0]
    for banned in ("Write", "stories/", "schemas/", "docs/", "回報"):
        assert banned not in p


def test_prompts_keep_persona():
    assert "絕不評價好壞" in workpacks.WORKPACKS["analyst"].system_prompt
    r = workpacks.WORKPACKS["reviewer"].system_prompt
    assert "第一條放最重要的一件" in r and "中性的讀者" in r and "不准寫「文筆優美」" in r


@pytest.mark.parametrize("name,key", [("analyst", "edges"), ("reviewer", "points")])
def test_system_prompt_appends_output_format(name, key):
    wp = workpacks.WORKPACKS[name]
    raw = (Path(workpacks.__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    assert wp.system_prompt.startswith(raw.rstrip())            # 人格原文一字不動,只在後面附
    tail = wp.system_prompt[len(raw.rstrip()):]
    assert "## 輸出格式" in tail and "單一 JSON 物件" in tail and "程式碼框" in tail
    assert key in wp.schema["required"] and f'"{key}"' in tail
    assert "$schema" not in tail
    for banned in ("Write", "Read", "回報", "寫入", "schemas/", "docs/"):   # 附加段也不准有工具味
        assert banned not in tail
    assert tail.rstrip().endswith(canonical_json({k: v for k, v in wp.schema.items()
                                                  if k != "$schema"}))


@pytest.mark.parametrize("name", ["analyst", "reviewer"])
def test_prompt_files_have_no_code_fence(name):
    # 輸出格式要求「不要程式碼框」,示例自己就不能帶框
    raw = (Path(workpacks.__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    assert "```" not in raw


def test_first_input_wraps_source(source, analysis):
    assert workpacks.first_input("analyst", "mini", source, None) == f"slug: mini\n<source>\n{source}\n</source>"
    got = workpacks.first_input("reviewer", "mini", source, analysis)
    assert got == (f"slug: mini\n<source>\n{source}\n</source>"
                   f"\n<analysis>\n{canonical_json(analysis)}\n</analysis>")


def test_repair_input_lists_errors_without_answers(source, analysis):
    prev = {"slug": "mini", "title": "x"}
    errors = ["引文找不到:甲", "node id 重複:乙"]
    out = workpacks.repair_input("analyst", "mini", source, None, prev, errors)
    assert out.startswith(workpacks.first_input("analyst", "mini", source, None))
    assert f"<previous_output>\n{canonical_json(prev)}\n</previous_output>" in out
    assert "- 引文找不到:甲\n- node id 重複:乙" in out
    assert "無法解析" not in out
    rest = out.replace(source, "").replace(canonical_json(prev), "")
    for e in errors:
        rest = rest.replace(e, "")
    assert rest == ("slug: mini\n<source>\n\n</source>"
                    "\n<previous_output>\n\n</previous_output>\n"
                    "上一份輸出沒通過驗證，逐條錯誤如下。請修正這些問題後重交整份 JSON，其餘內容保持不變：\n"
                    "- \n- ")


def test_repair_input_with_unparsable_text_truncates(source):
    raw = "前言" + "字" * 25_000
    out = workpacks.repair_input("analyst", "mini", source, None, raw, ["輸出不是單一 JSON 物件"])
    assert f"<previous_output>\n{raw[:20_000]}\n</previous_output>" in out
    assert raw[:20_001] not in out
    assert "- 輸出不是單一 JSON 物件" in out
    assert "其餘內容保持不變" not in out
    assert "無法解析成單一 JSON 物件" in out and "從頭重交完整的 JSON" in out


def test_gate_dispatch(source, analysis):
    assert workpacks.gate("analyst", analysis, source, None) == []
    bad = copy.deepcopy(analysis)
    bad["nodes"][0]["evidence"][0]["quote"] = "原文裡不存在的句子"
    assert workpacks.gate("analyst", bad, source, None) != []


def test_reviewer_registered():
    wp = workpacks.WORKPACKS["reviewer"]
    assert wp.kind == "notes"
    tail = wp.system_prompt.split("\n## 輸出格式\n")[1]
    assert '"moved"' in tail and '"confused"' in tail


def test_reviewer_first_input_needs_analysis(source, analysis):
    with pytest.raises(ValueError):
        workpacks.first_input("reviewer", "mini", source, None)


def test_gate_dispatch_reviewer(source, analysis):
    notes = {"slug": "mini", "read": "r", "one_line": "o", "points": [
        {"kind": "opinion", "title": "t", "quotes": ["像在等誰"], "refs": ["t99"], "body": "b",
         "question": None}]}
    assert workpacks.gate("reviewer", notes, source, analysis) == ["筆記「t」: refs t99 不是存在的 node id"]


def test_criticizer_retired():
    assert "criticizer" not in workpacks.WORKPACKS
    assert not (Path(workpacks.__file__).parent / "prompts" / "criticizer.md").exists()
