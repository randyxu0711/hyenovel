"""companion 人格:底層 + 角色讀法(spec §6)。"""
import pytest

from den import characters, companion
from den.companion import _read, persona, render_companion

READS = {"hyena": "照閱讀的順序", "buffalo": "最強的感覺", "deer": "世界撐開"}


def _c(character_id, voice=""):
    return {"id": character_id, "voice": voice}


def test_every_character_gets_base_and_only_its_own_reading():
    assert {c["id"] for c in characters.builtins()} == set(READS)
    for cid, mine in READS.items():
        p = persona(cid)
        assert "不幫作者寫句子" in p and mine in p
        assert not any(other in p for o, other in READS.items() if o != cid)


def test_persona_unknown_character():
    with pytest.raises(FileNotFoundError):
        persona("doubt")


def test_persona_text_is_channel_agnostic():   # spec §4:人格不提管道
    for cid in READS:
        for word in ("talk", "submit_work", "mcp", "tool"):
            assert word not in persona(cid)


def test_no_character_asks_consent_before_disagreeing():   # spike v1:先徵詢會變閃躲
    for cid in READS:
        assert "想聽嗎" not in persona(cid)
        assert "老實講你讀到的" in persona(cid)


# ── render_companion ──

def _ctx(**kw):
    base = {"slug": "s", "title": "題", "source": "她把傘收進門縫。\n", "analysis": None, "progress": "none"}
    return {**base, **kw}


def test_render_companion_source_only_mentions_no_structure():
    out = render_companion(_ctx(progress="running"), _c("hyena"))
    assert "她把傘收進門縫。" in out and "你讀的時候注意到的結構" not in out
    assert "還在背景跑" in out and READS["hyena"] in out


def test_render_companion_with_analysis_lists_nodes_not_edges():
    a = {"synopsis": "梗", "nodes": [{"id": "m1", "type": "motif", "label": "水", "note": "遞增"}],
         "edges": [{"from": "m1", "to": "t1", "type": "serves"}]}
    out = render_companion(_ctx(analysis=a, progress="done"), _c("buffalo"))
    assert "- motif 水:遞增" in out and "梗概:梗" in out
    assert "serves" not in out and "## 現在的狀況" not in out
    assert READS["buffalo"] in out


def test_render_companion_not_running_says_reading_from_source():
    for prog in ("none", "paused", "failed", "cancelled", "done"):
        assert "這篇目前沒有在跑結構分析,你憑原文讀。" in render_companion(_ctx(progress=prog), _c("hyena"))


def test_render_companion_title_falls_back_to_slug():
    assert "# 《s》" in render_companion(_ctx(title=None), _c("hyena"))


def test_running_hint_only_without_analysis():
    """reviewer 還在跑時已有分析:不能再說結構分析還在跑(analyst 成功就換 current)。"""
    a = {"synopsis": "梗", "nodes": [], "edges": []}
    for prog in ("queued", "running"):
        assert "還在背景跑" not in render_companion(_ctx(analysis=a, progress=prog), _c("hyena"))
        assert "還在背景跑" in render_companion(_ctx(progress=prog), _c("hyena"))


def _legacy_render(ctx, character):
    persona_text = _read("companion/base.md").rstrip() + "\n\n" + _read(f"characters/{character['id']}.md").rstrip() + "\n"
    if character["voice"].strip():
        persona_text += "\n" + character["voice"].rstrip() + "\n"
    out = [persona_text.rstrip(), "", "---", f"# 《{ctx['title'] or ctx['slug']}》",
           "## 原文", "<source>", ctx["source"].rstrip(), "</source>"]
    a = ctx["analysis"]
    if a is not None:
        out += ["", "## 你讀的時候注意到的結構(私下筆記,不要原樣念給作者)"]
        if a.get("synopsis"):
            out.append(f"梗概:{a['synopsis']}")
        out += [f"- {n['type']} {n['label']}" + (f":{n['note']}" if n.get("note") else "")
                for n in a.get("nodes") or ()]
    if a is None and ctx["progress"] in ("queued", "running"):
        out += ["", "## 現在的狀況", companion._RUNNING]
    elif a is None:
        out += ["", "## 現在的狀況", companion._IDLE]
    return "\n".join(out) + "\n"


_FULL = {"synopsis": "梗", "nodes": [{"type": "theme", "label": "海", "note": "鹹"},
                                    {"type": "motif", "label": "鹽", "note": None}]}


@pytest.mark.parametrize("analysis,progress,voice", [
    (_FULL, "done", ""),
    ({"synopsis": None, "nodes": []}, "done", ""),
    (None, "running", ""),
    (None, "idle", ""),
    (None, "queued", "角色層一句"),
    (_FULL, "running", "角色層一句\n"),
])
def test_assembled_prompt_keeps_every_byte(analysis, progress, voice):
    ctx = {"title": "海", "slug": "s", "source": "原文\n", "analysis": analysis, "progress": progress}
    c = _c("hyena", voice)
    assert render_companion(ctx, c) == _legacy_render(ctx, c)


def test_persona_keeps_every_byte():
    want = _read("companion/base.md").rstrip() + "\n\n" + _read("characters/deer.md").rstrip() + "\n"
    assert persona("deer") == want
    assert persona("deer", "一句\n") == want + "\n一句\n"
    assert persona("deer", "   ") == want


def test_same_prompt_on_different_works_shares_instruction_fingerprint():
    a = companion.assemble({"title": "甲", "slug": "a", "source": "甲文", "analysis": None, "progress": "idle"}, _c("hyena"))
    b = companion.assemble({"title": "乙", "slug": "b", "source": "乙文", "analysis": None, "progress": "idle"}, _c("hyena"))
    assert a.fingerprint()["instructions"] == b.fingerprint()["instructions"]
    assert a.fingerprint()["material"] != b.fingerprint()["material"]


def test_analysis_header_and_status_count_as_instructions():
    ctx = {"title": "海", "slug": "s", "source": "原文", "progress": "done"}
    fp = companion.assemble({**ctx, "analysis": _FULL}, _c("hyena")).fingerprint()
    assert "analysis_header" in fp["layers"] and "analysis" in fp["material"]
    fp = companion.assemble({**ctx, "analysis": None, "progress": "running"}, _c("hyena")).fingerprint()
    assert "status" in fp["layers"]
