"""render 契約:json → 人讀的 md(Obsidian 友善)。

確定性渲染:同 json 進、同 md 出。它服務「人讀」,不是前端的資料來源(那是 viz.json),
所以壞掉只是輸出難看、不危及分析可信度 —— 故只釘骨幹與分支,不做 snapshot。
"""
import json

import pytest

import render


def _analysis(base):
    return json.loads((base / "analysis.json").read_text(encoding="utf-8"))


# ── parse_slug:三種輸入形式 ─────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("mini", "mini"),
    ("stories/mini", "mini"),
    ("stories/mini/", "mini"),
    ("stories/mini/source.md", "mini"),
    ("stories/mini/analysis.json", "mini"),
    ("stories/mini/feedback.json", "mini"),
])
def test_parse_slug_forms(raw, want):
    assert render.parse_slug(raw) == want


# ── read_json:壞 JSON 給乾淨訊息,不吐 traceback ────────────────────

def test_read_json_bad_json_exits_cleanly(tmp_path):
    p = tmp_path / "analysis.json"
    p.write_text("{ 這不是 JSON", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        render.read_json(p)
    assert "不是合法 JSON" in str(e.value)


# ── render_analysis ─────────────────────────────────────────────────

def test_analysis_md_has_frontmatter_and_sections(story):
    slug, base = story
    md = render.render_analysis(_analysis(base))

    assert md.startswith("---\n"), "Obsidian frontmatter 要在最前面"
    assert 'title: "極小合成樣本"' in md
    assert "# 極小合成樣本 — 結構分析" in md
    assert "> 測試用的契約樣本,不是真故事。" in md      # synopsis
    for cn in ("主題", "技法", "效果", "節拍"):
        assert f"## {cn}" in md


def test_analysis_md_renders_quotes_and_intensity(story):
    slug, base = story
    md = render.render_analysis(_analysis(base))

    assert "「像在等誰」" in md                    # evidence quote
    assert "·強度 0.6" in md                       # effect 的 intensity
    assert "·強度 0.3" in md                       # beat 的 intensity


def test_analysis_md_renders_intent_chain(story):
    """意圖鏈是核心:technique →produces→ effect →serves→ theme。"""
    slug, base = story
    md = render.render_analysis(_analysis(base))
    assert "## 意圖鏈" in md
    assert "物件擬人 →produces→ 空缺感 →serves→ [[等待的落空]]" in md


def test_intent_chain_without_serves_still_renders():
    """effect 沒 serves 到任何主題 → 只印半條鏈,不得漏掉。"""
    a = {
        "slug": "x",
        "nodes": [
            {"id": "k1", "type": "technique", "label": "技"},
            {"id": "e1", "type": "effect", "label": "效"},
        ],
        "edges": [{"type": "produces", "from": "k1", "to": "e1"}],
    }
    md = render.render_analysis(a)
    assert "- 技 →produces→ 效" in md
    assert "→serves→" not in md


def test_intent_chain_skips_dangling_edge():
    """edge 指向不存在的 node → 跳過,不得炸。"""
    a = {
        "slug": "x",
        "nodes": [{"id": "k1", "type": "technique", "label": "技"}],
        "edges": [{"type": "produces", "from": "k1", "to": "nope"}],
    }
    assert render.render_analysis(a)          # 不拋


def test_linked_themes_on_motif():
    """意象 →manifests→ 主題 要標關聯主題(Obsidian 雙鏈)。"""
    a = {
        "slug": "x",
        "nodes": [
            {"id": "m1", "type": "motif", "label": "燈"},
            {"id": "t1", "type": "theme", "label": "等待"},
        ],
        "edges": [{"type": "manifests", "from": "m1", "to": "t1"}],
    }
    md = render.render_analysis(a)
    assert "關聯主題:[[等待]]" in md


def test_analysis_md_with_note(story):
    slug, base = story
    a = _analysis(base)
    a["nodes"][0]["note"] = "這個節拍很短。"
    a["nodes"][0]["evidence"][0]["note"] = "開場就把人抽走。"
    md = render.render_analysis(a)
    assert "這個節拍很短。" in md
    assert "— 開場就把人抽走。" in md


def test_analysis_md_minimal_input():
    """只有必要欄位(無 title/synopsis/nodes)→ 不得炸。"""
    md = render.render_analysis({"slug": "x", "nodes": [], "edges": []})
    assert "結構分析" in md


# ── render_feedback ─────────────────────────────────────────────────

def test_feedback_md_full(story, feedback_json):
    md = render.render_feedback(feedback_json, "極小合成樣本")

    assert "# 給作者的話 —〈極小合成樣本〉" in md
    assert "## 這篇在做什麼(我讀到的)" in md
    assert "## 最有效的地方" in md
    assert "### 燈的用法" in md
    assert "> 「像在等誰」" in md                             # quote 用引言塊
    assert "### 1. 收尾太快" in md                           # key_points 有編號
    assert "**留給作者的問題**:關燈之後,他站在黑暗裡多久?" in md
    assert "## 枝節" in md
    assert "如果只能改一件事:**節制,但收得太急。**" in md


def test_feedback_md_optional_sections_omitted():
    """沒有 strengths/minor/experiment → 那些段落整段不出現(不留空殼標題)。"""
    fb = {"slug": "x", "read": "讀到的。",
          "key_points": [{"title": "點", "quotes": ["q"], "body": "b"}],
          "one_line": "改這個。"}
    md = render.render_feedback(fb, "標題")
    assert "## 最有效的地方" not in md
    assert "## 枝節" not in md
    assert "可以試的實驗" not in md


def test_feedback_md_with_experiment():
    fb = {"slug": "x", "read": "r",
          "key_points": [{"title": "點", "quotes": ["q"], "body": "b",
                          "experiment": "把結尾刪掉試試。"}],
          "one_line": "o"}
    md = render.render_feedback(fb, "標題")
    assert "**可以試的實驗**:把結尾刪掉試試。" in md


# ── main():出檔行為 ────────────────────────────────────────────────

def test_main_writes_analysis_md_only_when_no_feedback(story, monkeypatch, capsys):
    slug, base = story
    monkeypatch.setattr(render.sys, "argv", ["render.py", slug])
    render.main()

    assert (base / "analysis.md").exists()
    assert not (base / "feedback.md").exists()
    assert "無 feedback.json" in capsys.readouterr().out


def test_main_writes_both_when_feedback_exists(story, monkeypatch, feedback_json):
    slug, base = story
    (base / "feedback.json").write_text(json.dumps(feedback_json, ensure_ascii=False),
                                        encoding="utf-8")
    monkeypatch.setattr(render.sys, "argv", ["render.py", slug])
    render.main()

    assert (base / "analysis.md").exists()
    assert (base / "feedback.md").exists()
    assert "給作者的話" in (base / "feedback.md").read_text(encoding="utf-8")


def test_main_analysis_only_skips_feedback(story, monkeypatch, feedback_json):
    slug, base = story
    (base / "feedback.json").write_text(json.dumps(feedback_json, ensure_ascii=False),
                                        encoding="utf-8")
    monkeypatch.setattr(render.sys, "argv", ["render.py", slug, "--analysis-only"])
    render.main()

    assert (base / "analysis.md").exists()
    assert not (base / "feedback.md").exists(), "--analysis-only 不該出 feedback.md"


def test_main_missing_analysis_exits(story, monkeypatch):
    slug, base = story
    (base / "analysis.json").unlink()
    monkeypatch.setattr(render.sys, "argv", ["render.py", slug])
    with pytest.raises(SystemExit) as e:
        render.main()
    assert "找不到" in str(e.value)


def test_main_without_args_exits(monkeypatch):
    monkeypatch.setattr(render.sys, "argv", ["render.py"])
    with pytest.raises(SystemExit):
        render.main()


def test_main_with_only_flags_exits(monkeypatch):
    """只給 flag 沒給 slug → 乾淨退出。"""
    monkeypatch.setattr(render.sys, "argv", ["render.py", "--analysis-only"])
    with pytest.raises(SystemExit) as e:
        render.main()
    assert "缺 slug" in str(e.value)
