"""companion 人格:底層 + 行為模式(spec §6)。"""
import pytest

from den.companion import MODE_LABELS, MODES, persona, render_companion


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


# ── render_companion ──

def _ctx(**kw):
    base = {"slug": "s", "title": "題", "source": "她把傘收進門縫。\n", "analysis": None, "progress": "none"}
    return {**base, **kw}


def test_render_companion_source_only_mentions_no_structure():
    out = render_companion(_ctx(progress="running"), "slow")
    assert "她把傘收進門縫。" in out and "你讀的時候注意到的結構" not in out
    assert "還在背景跑" in out and "你的讀法:慢讀" in out


def test_render_companion_with_analysis_lists_nodes_not_edges():
    a = {"synopsis": "梗", "nodes": [{"id": "m1", "type": "motif", "label": "水", "note": "遞增"}],
         "edges": [{"from": "m1", "to": "t1", "type": "serves"}]}
    out = render_companion(_ctx(analysis=a, progress="done"), "direct")
    assert "- motif 水:遞增" in out and "梗概:梗" in out
    assert "serves" not in out and "## 現在的狀況" not in out
    assert "你的讀法:直說" in out


def test_render_companion_not_running_says_reading_from_source():
    for prog in ("none", "paused", "failed", "cancelled", "done"):
        assert "這篇目前沒有在跑結構分析,你憑原文讀。" in render_companion(_ctx(progress=prog), "slow")


def test_render_companion_title_falls_back_to_slug():
    assert "# 《s》" in render_companion(_ctx(title=None), "slow")


def test_running_hint_only_without_analysis():
    """reviewer 還在跑時已有分析:不能再說結構分析還在跑(analyst 成功就換 current)。"""
    a = {"synopsis": "梗", "nodes": [], "edges": []}
    for prog in ("queued", "running"):
        assert "還在背景跑" not in render_companion(_ctx(analysis=a, progress=prog), "slow")
        assert "還在背景跑" in render_companion(_ctx(progress=prog), "slow")
