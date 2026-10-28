"""discuss.md 人格不能對使用者說假話(#18):這段對話不會被存成結論。"""
from pathlib import Path

DISCUSS = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "discuss.md"


def test_discuss_prompt_promises_no_saving():
    text = DISCUSS.read_text(encoding="utf-8")
    assert "收束保存" not in text
    assert "不會被存成結論" in text
