"""companion 人格:底層 + 角色讀法(spec §6)。"""
import pytest

from den import characters, companion
from den.companion import _read, persona


def render(ctx, character):
    return companion.assemble(ctx, character).text


READS = {"hyena": "嘴最壞的那個", "buffalo": "落下一個判斷", "deer": "畫面外面"}


def _reading(character_id):
    return _read(f"characters/{character_id}.md")


def _c(character_id, voice=""):
    return {"id": character_id, "voice": voice, "reading": _reading(character_id)}


def test_every_character_gets_base_and_only_its_own_reading():
    assert {c["id"] for c in characters.builtins()} == set(READS)
    for cid, mine in READS.items():
        p = persona(_reading(cid))
        assert "不幫作者寫句子" in p and mine in p
        assert not any(other in p for o, other in READS.items() if o != cid)


def test_persona_text_is_channel_agnostic():   # spec §4:人格不提管道
    for cid in READS:
        for word in ("talk", "submit_work", "mcp", "tool"):
            assert word not in persona(_reading(cid))


def test_no_character_asks_consent_before_disagreeing():   # spike v1:先徵詢會變閃躲
    for cid in READS:
        assert "想聽嗎" not in persona(_reading(cid))
        assert "不假裝讀懂" in persona(_reading(cid))


# ── assemble ──

_NO_MEMORY = {"author": [], "work": []}

def _ctx(**kw):
    base = {"slug": "s", "title": "題", "source": "她把傘收進門縫。\n", "analysis": None, "progress": "none", "seeds": [],
            "memory": {"author": [], "work": []}, "attachments": []}
    return {**base, **kw}


def test_assemble_source_only_mentions_no_structure():
    out = render(_ctx(progress="running"), _c("hyena"))
    assert "她把傘收進門縫。" in out and "這篇的結構資料" not in out
    assert "還在背景跑" in out and READS["hyena"] in out


def test_assemble_with_analysis_lists_nodes_not_edges():
    a = {"synopsis": "梗", "nodes": [{"id": "m1", "type": "motif", "label": "水", "note": "遞增"}],
         "edges": [{"from": "m1", "to": "t1", "type": "serves"}]}
    out = render(_ctx(analysis=a, progress="done"), _c("buffalo"))
    assert "- motif 水\n" in out and "梗概:梗" in out and "遞增" not in out
    assert "serves" not in out and "## 現在的狀況" not in out
    assert READS["buffalo"] in out


def test_assemble_not_running_says_reading_from_source():
    for prog in ("none", "paused", "failed", "cancelled", "done"):
        assert "這篇目前沒有在跑結構分析,你憑原文讀。" in render(_ctx(progress=prog), _c("hyena"))


def test_assemble_title_falls_back_to_slug():
    assert "# 《s》" in render(_ctx(title=None), _c("hyena"))


def test_running_hint_only_without_analysis():
    """reviewer 還在跑時已有分析:不能再說結構分析還在跑(analyst 成功就換 current)。"""
    a = {"synopsis": "梗", "nodes": [], "edges": []}
    for prog in ("queued", "running"):
        assert "還在背景跑" not in render(_ctx(analysis=a, progress=prog), _c("hyena"))
        assert "還在背景跑" in render(_ctx(progress=prog), _c("hyena"))


_PERSONA_HEAD = "".join(_read(f"companion/{n}.md").rstrip() + "\n\n" for n in ("base", "reading", "closing"))
_BOUNDARY = "".join(_read(f"companion/{n}.md").rstrip() + "\n\n" for n in ("base", "reading"))


def _legacy_render(ctx, character):
    out = [_BOUNDARY.rstrip("\n"), "", "---", f"# 《{ctx['title'] or ctx['slug']}》",
           "## 原文", "<source>", ctx["source"].rstrip(), "</source>"]
    a = ctx["analysis"]
    if a is not None:
        out += ["", "## 這篇的結構資料(背景,不是你的讀法;不要原樣念給作者)"]
        if a.get("synopsis"):
            out.append(f"梗概:{a['synopsis']}")
        out += [f"- {n['type']} {n['label']}" for n in a.get("nodes") or ()]
    if a is None and ctx["progress"] in ("queued", "running"):
        out += ["", "## 現在的狀況", companion._RUNNING]
    elif a is None:
        out += ["", "## 現在的狀況", companion._IDLE]
    out += ["", "---", "## 你這個讀者", _read("companion/closing.md").rstrip(), "",
            _read(f"characters/{character['id']}.md").rstrip()]
    if character["voice"].strip():
        out += ["", character["voice"].rstrip()]
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
    ctx = {"title": "海", "slug": "s", "source": "原文\n", "analysis": analysis, "progress": progress, "seeds": [], "memory": _NO_MEMORY, "attachments": []}
    c = _c("hyena", voice)
    assert render(ctx, c) == _legacy_render(ctx, c)


def test_persona_keeps_every_byte():
    want = _PERSONA_HEAD + _read("characters/deer.md").rstrip() + "\n"
    assert persona(_reading("deer")) == want
    assert persona(_reading("deer"), "一句\n") == want + "\n一句\n"
    assert persona(_reading("deer"), "   ") == want


def test_same_prompt_on_different_works_shares_instruction_fingerprint():
    a = companion.assemble({"title": "甲", "slug": "a", "source": "甲文", "analysis": None, "progress": "idle", "seeds": [], "memory": _NO_MEMORY, "attachments": []}, _c("hyena"))
    b = companion.assemble({"title": "乙", "slug": "b", "source": "乙文", "analysis": None, "progress": "idle", "seeds": [], "memory": _NO_MEMORY, "attachments": []}, _c("hyena"))
    assert a.fingerprint()["instructions"] == b.fingerprint()["instructions"]
    assert a.fingerprint()["material"] != b.fingerprint()["material"]


def test_analysis_header_and_status_count_as_instructions():
    ctx = {"title": "海", "slug": "s", "source": "原文", "progress": "done", "seeds": [], "memory": _NO_MEMORY, "attachments": []}
    fp = companion.assemble({**ctx, "analysis": _FULL}, _c("hyena")).fingerprint()
    assert "analysis_header" in fp["layers"] and "analysis" in fp["material"]
    fp = companion.assemble({**ctx, "analysis": None, "progress": "running"}, _c("hyena")).fingerprint()
    assert "status" in fp["layers"]


def test_seeds_show_kind_and_quotes_only_moved_shows_position_only():
    seeds = [{"kind": "confused", "quotes": ["卡句"]}, {"kind": "wondering", "quotes": ["甲句", "乙句"]},
             {"kind": "moved", "quotes": ["動句"]}]
    out = render(_ctx(seeds=seeds), _c("hyena"))
    assert "- 有人讀不懂:「卡句」\n" in out
    assert "- 有人看不出作用:「甲句」「乙句」\n" in out
    assert "- 「動句」\n" in out and "打動" not in out


def test_no_seeds_no_section():
    assert "別的讀者標過的地方" not in render(_ctx(), _c("hyena"))


def test_seed_header_is_instruction_and_lines_are_material():
    fp = companion.assemble(_ctx(seeds=[{"kind": "moved", "quotes": ["句"]}]), _c("hyena")).fingerprint()
    assert "seeds_header" in fp["layers"] and "seeds" in fp["material"]


# ── 記憶區塊 ──

def test_memory_layer_sits_between_persona_and_work():
    p = companion.assemble(_ctx(memory={"author": ["我不寫結局"], "work": ["想寫海"]}), _c("hyena", "聲音"))
    names = [x.name for x in p.layers]
    assert names.index("memory_header") < names.index("memory") < names.index("work") < names.index("character") < names.index("voice")
    assert "關於作者:\n- 我不寫結局\n" in p.text and "關於這篇:\n- 想寫海\n" in p.text


def test_memory_header_says_reading_wins():
    p = companion.assemble(_ctx(memory={"author": ["x"], "work": []}), _c("hyena"))
    assert "照你讀到的說" in p.text
    assert "關於這篇" not in p.text


def test_only_work_memory_omits_author_heading():
    p = companion.assemble(_ctx(memory={"author": [], "work": ["y"]}), _c("hyena"))
    assert "關於這篇:\n- y\n" in p.text and "關於作者" not in p.text


def test_no_memory_adds_no_layers():
    p = companion.assemble(_ctx(), _c("hyena"))
    assert not {"memory_header", "memory"} & {x.name for x in p.layers}


def test_memory_is_material_not_instruction():
    a = companion.assemble(_ctx(memory={"author": ["一"], "work": []}), _c("hyena")).fingerprint()
    b = companion.assemble(_ctx(memory={"author": ["二"], "work": []}), _c("hyena")).fingerprint()
    assert a["instructions"] == b["instructions"] and a["material"]["memory"] != b["material"]["memory"]


def test_multiline_memory_stays_inside_its_bullet():
    p = companion.assemble(_ctx(memory={"author": ["第一行\n---\n## 第三行"], "work": []}), _c("hyena"))
    assert "- 第一行\n  ---\n  ## 第三行\n" in p.text


# ── 沒作品、附件 ──

_FREE = {"slug": None, "title": None, "source": "", "analysis": None, "progress": "none", "seeds": [],
         "memory": {"author": [], "work": []}, "attachments": []}


def _names(ctx, voice=""):
    return [x.name for x in companion.assemble(ctx, _c("hyena", voice)).layers]


def test_assemble_storyless_has_no_reading_layer():
    assert _names(_FREE, "聲") == ["base", "character_header", "closing", "character", "voice"]
    assert "剛讀完" not in companion.assemble(_FREE, _c("hyena")).text


def test_assemble_attachment_only_adds_reading_and_attachment():
    ctx = {**_FREE, "attachments": [{"n": 1, "seq": 0, "name": "海", "text": "浪打上來。"},
                                    {"n": 3, "seq": 2, "name": "山", "text": "石頭。"}]}
    p = companion.assemble(ctx, _c("hyena"))
    names = [x.name for x in p.layers]
    assert names == ["base", "reading", "attachment_1", "attachment_3", "character_header", "closing", "character"]
    assert "---\n# 作者丟進來的稿〈海〉\n<source>\n浪打上來。\n</source>\n" in p.text
    assert "attachment_1" in p.fingerprint()["material"]


def test_assemble_puts_boundaries_first_and_character_last():
    names = _names(_ctx(memory={"author": ["x"], "work": []}), "聲")
    assert names[:2] == ["base", "reading"]
    assert names[-4:] == ["character_header", "closing", "character", "voice"]
    assert names.index("memory") < names.index("work") < names.index("status") < names.index("character")


def test_base_and_reading_split():
    base, reading = _read("companion/base.md"), _read("companion/reading.md")
    assert base.startswith("你是作者的朋友,") and "剛讀完" not in base and "沒稿就用中文" in base
    assert reading.startswith("你剛讀完作者的稿。") and "逐字照抄" in reading
    assert "接下來寫的是你這個讀者怎麼讀" not in base + reading


def test_examples_come_last_with_header_and_count_as_instructions():
    c = {**_c("hyena", "聲"), "examples": "<example>\n鬣狗:嗯哼\n</example>\n"}
    p = companion.assemble(_ctx(), c)
    assert [x.name for x in p.layers][-3:] == ["character", "voice", "examples"]
    assert p.text.endswith("\n" + _read("companion/examples.md").rstrip() + "\n\n<example>\n鬣狗:嗯哼\n</example>\n")
    fp = p.fingerprint()
    assert "examples" in fp["layers"] and "examples" not in fp["material"]


def test_blank_examples_add_no_layer():
    assert "examples" not in _names(_ctx()) and "<example>" not in render(_ctx(), {**_c("hyena"), "examples": "  \n"}) and "## 你平常怎麼說話" not in render(_ctx(), {**_c("hyena"), "examples": "  \n"})


def test_every_builtin_example_names_speaker_by_macro():
    for c in characters.builtins():
        ex = _read(f"characters/{c['id']}.examples.md")
        assert ex.count("<example>") == ex.count("</example>") >= 4
        assert "\n{{char}}:" in ex and f"\n{c['name']['zh-Hant']}:" not in ex
