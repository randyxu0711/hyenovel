"""index 契約:以 analysis.json 是否存在過濾 —— 孤兒故事「隱形無害」。

這條政策是刻意的,而且據此否決過 orphan-sweep(2026-07-11):
沒跑完 critique 的目錄不該出現在列表裡,但也不必去掃它、刪它。
「消費端本就在 check 狀態」比「反應式填洞」乾淨。
"""
import json

import pytest

import index


def test_story_with_analysis_is_listed(story):
    slug, base = story
    data = index.build()

    assert data["count"] == 1
    e = data["stories"][0]
    assert e["slug"] == "mini"
    assert e["title"] == "極小合成樣本"
    assert e["nodes"] == 4 and e["edges"] == 2
    assert e["has_feedback"] is False
    assert e["has_viz"] is False
    assert e["updated"]                      # ISO 時間字串


def test_orphan_without_analysis_is_invisible(story):
    """只有 source.md 的孤兒目錄 → 不進列表。它不是破卡,是隱形。"""
    slug, base = story
    orphan = base.parent / "s99"
    orphan.mkdir()
    (orphan / "source.md").write_text("孤兒故事,沒跑過 critique。\n", encoding="utf-8")

    slugs = [s["slug"] for s in index.build()["stories"]]
    assert "s99" not in slugs, "孤兒不該出現在列表"
    assert slugs == ["mini"]


def test_broken_analysis_is_skipped_not_fatal(story, capsys):
    """單篇 analysis.json 壞掉 → 跳過該篇(印警告),不讓整份列表生不出來。

    這裡刻意「容錯跳過」而非 sys.exit —— 跟閘門(viz.py)的態度相反,
    因為一篇壞掉不該連累其他篇的列表。
    """
    slug, base = story
    (base / "analysis.json").write_text("{ 這不是 JSON", encoding="utf-8")

    data = index.build()
    assert data["count"] == 0
    assert "跳過" in capsys.readouterr().out


def test_has_feedback_and_viz_flags(story, feedback_json):
    slug, base = story
    (base / "feedback.json").write_text(json.dumps(feedback_json, ensure_ascii=False),
                                        encoding="utf-8")
    (base / "viz.json").write_text("{}", encoding="utf-8")

    e = index.build()["stories"][0]
    assert e["has_feedback"] is True
    assert e["has_viz"] is True


def test_updated_follows_newest_of_analysis_or_feedback(story, feedback_json):
    """feedback 較新 → updated 以它為準(列表要反映最後動過的時間)。"""
    import os
    import time

    slug, base = story
    fp = base / "feedback.json"
    fp.write_text(json.dumps(feedback_json, ensure_ascii=False), encoding="utf-8")

    future = time.time() + 3600
    os.utime(fp, (future, future))

    e = index.entry(base)
    assert e["updated"], "feedback 較新時要拿它的 mtime"


def test_slug_falls_back_to_dirname(story):
    """analysis.json 沒寫 slug → 用目錄名(列表不得出現空 slug)。"""
    slug, base = story
    data = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    del data["slug"]
    (base / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert index.entry(base)["slug"] == "mini"


def test_title_falls_back_to_slug(story):
    slug, base = story
    data = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    del data["title"]
    (base / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert index.entry(base)["title"] == "mini"


def test_entry_returns_none_without_analysis(tmp_path):
    d = tmp_path / "s99"
    d.mkdir()
    assert index.entry(d) is None


# ── main():--check 不寫檔、正常模式寫 index.json ────────────────────

def test_main_writes_index_json(story, monkeypatch, capsys):
    slug, base = story
    monkeypatch.setattr(index.sys, "argv", ["index.py"])
    index.main()

    out = base.parent / "index.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["count"] == 1 and data["stories"][0]["slug"] == "mini"


def test_main_check_writes_nothing(story, monkeypatch, capsys):
    slug, base = story
    monkeypatch.setattr(index.sys, "argv", ["index.py", "--check"])
    index.main()

    assert not (base.parent / "index.json").exists(), "--check 不該寫檔"
    assert "未寫檔" in capsys.readouterr().out
