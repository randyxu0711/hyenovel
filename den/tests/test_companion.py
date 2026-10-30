"""companion 人格:底層 + 行為模式(spec §6)。"""
import pytest

from den.companion import MODE_LABELS, MODES, persona


def test_persona_each_mode_has_base_and_its_own_rules():
    for m in MODES:
        p = persona(m)
        assert "不幫他寫句子" in p
        assert f"你的讀法:{MODE_LABELS[m]}" in p
    assert "你的讀法:慢讀" not in persona("direct")


def test_persona_unknown_mode():
    with pytest.raises(ValueError):
        persona("doubt")


def test_persona_text_is_channel_agnostic():   # spec §4:人格不提管道
    for m in MODES:
        for word in ("talk", "submit_work", "mcp", "tool"):
            assert word not in persona(m)


def test_consent_rule_only_in_non_direct_modes():   # spike v1:先徵詢會變閃躲
    assert "想聽嗎" not in persona("direct")
    assert "先老實講你讀到的" in persona("slow") and "先老實講你讀到的" in persona("imaginative")
