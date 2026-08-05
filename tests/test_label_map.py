"""label_map.py —— 跨篇概念地圖的確定性層(純函式,吃 100% 覆蓋門檻)。

這個模組不認識 SDK、不認識 server/。LLM 的草稿由呼叫端(server/align.py)餵進來。
分工同 conclusions.py / settled.py。
"""
import json
from pathlib import Path

import conclusions
import label_map

FIXTURES = Path(__file__).parent / "fixtures" / "multi"


def _use_fixtures(monkeypatch, path=FIXTURES):
    """label_map 與 conclusions 兩邊的 STORIES 都要指到同一處。

    fingerprints() 走 conclusions.analysis_fp(指紋的單一正本),而那支讀的是
    conclusions.STORIES —— 只換一邊,測試會看到真實 stories/ 底下的東西。
    同 server/tests/test_settle.py 的 _tmp_stories 一次換三個。
    """
    monkeypatch.setattr(label_map, "STORIES", path)
    monkeypatch.setattr(conclusions, "STORIES", path)


def test_collect_takes_only_four_types(monkeypatch):
    _use_fixtures(monkeypatch)
    rows = label_map.collect()
    types = {r["type"] for r in rows}
    assert types == {"motif", "theme", "technique", "effect"}
    # beat / character 被排除:跨篇沒有對應物 / 會產生垃圾族
    assert not any(r["node"] in ("b1", "c1") and r["slug"] == "s01" for r in rows)


def test_collect_carries_quotes_and_sorts(monkeypatch):
    _use_fixtures(monkeypatch)
    rows = label_map.collect()
    assert [(r["slug"], r["node"]) for r in rows] == sorted(
        (r["slug"], r["node"]) for r in rows)
    s01m1 = next(r for r in rows if r["slug"] == "s01" and r["node"] == "m1")
    assert s01m1["label"] == "水窪"
    assert s01m1["quotes"] == ["地上積了一窪水。", "水面晃了一下。"]


def test_collect_skips_unreadable_story(monkeypatch, tmp_path):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "analysis.json").write_text(json.dumps({
        "nodes": [{"id": "m1", "type": "motif", "label": "光",
                   "evidence": [{"quote": "亮著。"}]}]}), encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "analysis.json").write_text("{ 壞掉", encoding="utf-8")
    (tmp_path / "no-analysis").mkdir()
    (tmp_path / "notadir.txt").write_text("x", encoding="utf-8")
    _use_fixtures(monkeypatch, tmp_path)
    rows = label_map.collect()
    assert [r["slug"] for r in rows] == ["good"]


def test_collect_skips_malformed_nodes(monkeypatch, tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "analysis.json").write_text(json.dumps({
        "nodes": [
            {"id": "m1", "type": "motif", "label": "光", "evidence": [{"quote": "亮"}]},
            {"type": "motif", "label": "無 id"},
            {"id": "m3", "type": "motif"},
            "不是 dict",
            {"id": "m4", "type": "motif", "label": "無 evidence"},
        ]}), encoding="utf-8")
    _use_fixtures(monkeypatch, tmp_path)
    rows = label_map.collect()
    assert [r["node"] for r in rows] == ["m1", "m4"]
    assert next(r for r in rows if r["node"] == "m4")["quotes"] == []


def test_collect_when_stories_dir_missing(monkeypatch, tmp_path):
    _use_fixtures(monkeypatch, tmp_path / "nope")
    assert label_map.collect() == []
