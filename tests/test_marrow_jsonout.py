"""marrow.jsonout:從工人的文字輸出抽出單一 JSON 物件;抽不出回 None、不拋。"""
import pytest

from marrow.jsonout import extract_json


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '  \n{"a": 1}\n  ',
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
    '```{"a": 1}```',
    '好的,以下是結果:\n{"a": 1}\n以上。',
])
def test_extracts_object(text):
    assert extract_json(text) == {"a": 1}


def test_nested_string_with_braces():
    text = '說明 {"q": "他說}了{又", "n": {"k": "}"}} 結尾'
    assert extract_json(text) == {"q": "他說}了{又", "n": {"k": "}"}}


@pytest.mark.parametrize("text", [
    "", "   ", "[1, 2]", '```json\n[{"a": 1}]\n```', '{"a": [1, 2',
    "沒有 JSON", "} 反過來 {", '"字串"', "前言 [1] 後記",
])
def test_returns_none(text):
    assert extract_json(text) is None
