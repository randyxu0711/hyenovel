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


def _ok_mapping():
    """一份會過全部閘門的地圖(對應 fixtures/multi)。"""
    return {
        "built_at": 1753900000.0,
        "analysis_fps": {"s01": "a", "s02": "b", "s03": "c"},
        "source_node_count": 9,
        "concepts": [{
            "id": "L001", "canonical": "等待", "node_type": "theme",
            "members": [
                {"slug": "s01", "node": "t1", "label": "等不到的人",
                 "why": "把等待寫成一個沒有終點的動作。",
                 "evidence_index": 0, "quote": "他一直沒來。"},
                {"slug": "s02", "node": "t1", "label": "等待的落空",
                 "why": "門始終沒開,等待被結構性地否定。",
                 "evidence_index": 0, "quote": "門一直是關的。"},
            ]}]}


def test_validate_passes_clean_mapping(monkeypatch):
    _use_fixtures(monkeypatch)
    assert label_map.validate(_ok_mapping(), label_map.collect()) == []


def test_validate_blocks_schema_violation(monkeypatch):
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["id"] = "belonging"          # 不合 ^L[0-9]{3,}$
    errs = label_map.validate(m, label_map.collect())
    assert any("id" in e for e in errs)


def test_validate_blocks_unknown_node(monkeypatch):
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["members"][0]["node"] = "t99"
    errs = label_map.validate(m, label_map.collect())
    assert any("s01/t99" in e for e in errs)


def test_validate_blocks_type_mismatch(monkeypatch):
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["node_type"] = "motif"       # t1 是 theme
    errs = label_map.validate(m, label_map.collect())
    assert any("型別" in e for e in errs)


def test_validate_blocks_tampered_label(monkeypatch):
    """label 逐字閘門 —— 引用閘門在標籤層的同構物。"""
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["members"][0]["label"] = "等不到的人們"
    errs = label_map.validate(m, label_map.collect())
    assert any("label" in e for e in errs)


def test_validate_blocks_evidence_index_out_of_range(monkeypatch):
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["members"][0]["evidence_index"] = 5   # s01/t1 只有 1 條
    errs = label_map.validate(m, label_map.collect())
    assert any("evidence_index" in e for e in errs)


def test_validate_blocks_blank_why(monkeypatch):
    _use_fixtures(monkeypatch)
    m = _ok_mapping()
    m["concepts"][0]["members"][0]["why"] = "   "
    errs = label_map.validate(m, label_map.collect())
    assert errs


def test_validate_reports_missing_schema_file(monkeypatch):
    _use_fixtures(monkeypatch)
    monkeypatch.setattr(label_map, "ROOT", Path("/nonexistent"))
    errs = label_map.validate(_ok_mapping(), label_map.collect())
    assert len(errs) == 1 and "schema" in errs[0]


def test_validate_survives_garbage_shapes(monkeypatch):
    """閘門自己絕不拋例外 —— 炸掉的閘門等於沒有閘門。"""
    _use_fixtures(monkeypatch)
    table = label_map.collect()
    assert label_map.validate({"concepts": "不是陣列"}, table)
    assert label_map.validate({"concepts": ["不是 dict"]}, table)
    assert label_map.validate(
        {"built_at": 1.0, "analysis_fps": {}, "source_node_count": 0,
         "concepts": [{"id": "L001", "canonical": "x", "node_type": "theme",
                       "members": ["不是 dict"]}]}, table)
