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
    # 合法 JSON 但沒有 nodes 陣列 / 根本不是物件 —— 兩者都解得開,所以走的不是
    # JSONDecodeError 那條,是「nodes 不是 list」那條。少了它 collect() 湊不滿分支。
    (tmp_path / "no-nodes").mkdir()
    (tmp_path / "no-nodes" / "analysis.json").write_text("{}", encoding="utf-8")
    (tmp_path / "not-an-object").mkdir()
    (tmp_path / "not-an-object" / "analysis.json").write_text("[]", encoding="utf-8")
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


def _draft(canonical, node_type, pairs):
    return {"canonical": canonical, "node_type": node_type,
            "members": [{"slug": s, "node": n, "label": "x", "why": "y",
                         "evidence_index": 0} for s, n in pairs]}


def test_assign_ids_mints_from_001_when_no_prev():
    out = label_map.assign_ids(
        [_draft("等待", "theme", [("s01", "t1")]),
         _draft("水", "motif", [("s01", "m1")])], None)
    assert [c["id"] for c in out] == ["L001", "L002"]


def test_assign_ids_reuses_by_member_overlap_not_by_name():
    """族名整個換掉,但成員一樣 → 沿用舊 id。"""
    prev = {"concepts": [{"id": "L007", "canonical": "歸屬的不可抵達",
                          "node_type": "theme",
                          "members": [{"slug": "s01", "node": "t1"},
                                      {"slug": "s02", "node": "t1"}]}]}
    out = label_map.assign_ids(
        [_draft("永遠差一步的抵達", "theme", [("s01", "t1"), ("s02", "t1")])], prev)
    assert out[0]["id"] == "L007"


def test_assign_ids_mints_new_when_overlap_too_low():
    prev = {"concepts": [{"id": "L007", "canonical": "等待", "node_type": "theme",
                          "members": [{"slug": "s01", "node": "t1"},
                                      {"slug": "s02", "node": "t1"}]}]}
    out = label_map.assign_ids(
        [_draft("完全不同的族", "theme", [("s03", "e1")])], prev)
    assert out[0]["id"] == "L008"        # 不回收號碼:從既有最大值 +1


def test_assign_ids_split_gives_id_to_the_bigger_half():
    """一族裂成兩族 → 成員留得多的那支繼承 id,另一支鑄新號。"""
    prev = {"concepts": [{"id": "L003", "canonical": "大族", "node_type": "motif",
                          "members": [{"slug": "s01", "node": "m1"},
                                      {"slug": "s02", "node": "m1"},
                                      {"slug": "s03", "node": "m1"}]}]}
    out = label_map.assign_ids(
        [_draft("小的那支", "motif", [("s01", "m1")]),
         _draft("大的那支", "motif", [("s02", "m1"), ("s03", "m1")])], prev)
    ids = {c["canonical"]: c["id"] for c in out}
    assert ids["大的那支"] == "L003"
    assert ids["小的那支"] == "L004"


def test_assign_ids_never_reuses_one_old_id_twice():
    prev = {"concepts": [{"id": "L001", "canonical": "族", "node_type": "motif",
                          "members": [{"slug": "s01", "node": "m1"},
                                      {"slug": "s02", "node": "m1"}]}]}
    out = label_map.assign_ids(
        [_draft("甲", "motif", [("s01", "m1"), ("s02", "m1")]),
         _draft("乙", "motif", [("s01", "m1"), ("s02", "m1")])], prev)
    assert len({c["id"] for c in out}) == 2


def test_assign_ids_does_not_recycle_vanished_numbers():
    """已消失的族不回收號碼 —— 避免 id 被兩個不同的族先後用過。"""
    prev = {"concepts": [{"id": "L009", "canonical": "早就沒了", "node_type": "motif",
                          "members": [{"slug": "sX", "node": "m1"}]}]}
    out = label_map.assign_ids([_draft("新族", "motif", [("s01", "m1")])], prev)
    assert out[0]["id"] == "L010"


def test_assign_ids_survives_garbage_prev():
    for bad in (None, {}, {"concepts": "壞"}, {"concepts": [None]},
                {"concepts": [{"id": "不合格式", "members": []}]}):
        out = label_map.assign_ids([_draft("族", "motif", [("s01", "m1")])], bad)
        assert out[0]["id"].startswith("L")


def test_fingerprints_covers_all_stories(monkeypatch):
    _use_fixtures(monkeypatch)
    fps = label_map.fingerprints()
    assert set(fps) == {"s01", "s02", "s03"}
    assert all(len(v) == 40 for v in fps.values())


def test_fingerprints_when_stories_dir_missing(monkeypatch, tmp_path):
    _use_fixtures(monkeypatch, tmp_path / "nope")
    assert label_map.fingerprints() == {}


def test_fingerprints_skips_what_cannot_be_fingerprinted(monkeypatch, tmp_path):
    """三種都要跳過,而且三種各是一條分支(缺一條就湊不滿 branch 覆蓋)。"""
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "analysis.json").write_text("{}", encoding="utf-8")
    (tmp_path / "no-analysis").mkdir()                    # 目錄在,但還沒分析
    (tmp_path / "notadir.txt").write_text("x", encoding="utf-8")
    # analysis.json 是「目錄」—— exists() 為真但 read_bytes() 拋 IsADirectoryError,
    # analysis_fp 吞掉回空字串。這是 `if fp:` 那條 False 分支唯一構造得出來的情形。
    (tmp_path / "weird").mkdir()
    (tmp_path / "weird" / "analysis.json").mkdir()
    _use_fixtures(monkeypatch, tmp_path)
    assert set(label_map.fingerprints()) == {"good"}


def test_load_returns_none_when_absent_or_broken(monkeypatch, tmp_path):
    _use_fixtures(monkeypatch, tmp_path)
    assert label_map.load() is None
    (tmp_path / "label-map.json").write_text("{ 壞", encoding="utf-8")
    assert label_map.load() is None
    (tmp_path / "label-map.json").write_text('["不是 dict"]', encoding="utf-8")
    assert label_map.load() is None


def test_is_stale_when_fingerprint_changed(monkeypatch):
    _use_fixtures(monkeypatch)
    fps = label_map.fingerprints()
    assert label_map.is_stale({"analysis_fps": fps}) is False
    bad = dict(fps, s01="0" * 40)
    assert label_map.is_stale({"analysis_fps": bad}) is True


def test_is_stale_when_story_added(monkeypatch):
    _use_fixtures(monkeypatch)
    fps = label_map.fingerprints()
    fps.pop("s03")
    assert label_map.is_stale({"analysis_fps": fps}) is True


def test_is_stale_when_story_deleted(monkeypatch):
    """篇被刪掉 —— 少了這條,member 會指向不存在的篇。"""
    _use_fixtures(monkeypatch)
    fps = dict(label_map.fingerprints(), sGONE="0" * 40)
    assert label_map.is_stale({"analysis_fps": fps}) is True


def test_is_stale_when_mapping_is_none_or_garbage(monkeypatch):
    _use_fixtures(monkeypatch)
    assert label_map.is_stale(None) is True
    assert label_map.is_stale({}) is True
    assert label_map.is_stale({"analysis_fps": "壞"}) is True


def _drafts_json():
    return json.dumps([{
        "canonical": "等待", "node_type": "theme",
        "members": [
            {"slug": "s01", "node": "t1", "label": "等不到的人",
             "why": "把等待寫成沒有終點的動作。", "evidence_index": 0},
            {"slug": "s02", "node": "t1", "label": "等待的落空",
             "why": "門始終沒開。", "evidence_index": 0}]}], ensure_ascii=False)


def _seed_multi(tmp_path):
    """把三篇合成樣本複製進 tmp_path —— build() 會寫檔,不可以寫進 fixtures 目錄。"""
    for name in ("s01", "s02", "s03"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "analysis.json").write_bytes(
            (FIXTURES / name / "analysis.json").read_bytes())
    return tmp_path


def test_parse_drafts_strips_fence_and_prose():
    assert label_map.parse_drafts("```json\n[]\n```")[0] == []
    assert label_map.parse_drafts("以下是結果:\n[{}]")[0] == [{}]
    assert label_map.parse_drafts("完全不是 JSON")[1] is not None
    assert label_map.parse_drafts('{"不是": "陣列"}')[1] is not None
    # 元素不是物件要在入口擋掉:下游 assign_ids 的 dict(d) 對字串會拋 ValueError,
    # 那會讓閘門從「回錯誤」變成「炸例外」。
    assert label_map.parse_drafts('["字串"]')[1] is not None
    # 圍欄裡的東西壞掉、以及只有一行圍欄的退化情形
    assert label_map.parse_drafts("```\n不是 JSON\n```")[1] is not None
    assert label_map.parse_drafts("```")[1] is not None
    # 前後有散文包著一個合法陣列 → 撈中間那段
    assert label_map.parse_drafts("結果如下:[{}] 以上")[0] == [{}]
    assert label_map.parse_drafts("開頭 [壞掉 結尾]")[1] is not None


def test_build_writes_and_stamps(monkeypatch, tmp_path):
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    mapping, errs = label_map.build(_drafts_json(), now=123.0)
    assert errs == []
    assert mapping["built_at"] == 123.0
    assert mapping["source_node_count"] == len(label_map.collect())
    assert set(mapping["analysis_fps"]) == {"s01", "s02", "s03"}
    c = mapping["concepts"][0]
    assert c["id"] == "L001"
    # quote 是確定性層照 evidence_index 取的,LLM 沒寫這欄
    assert c["members"][0]["quote"] == "他一直沒來。"
    assert label_map.load() == mapping


def test_build_stamps_time_when_now_omitted(monkeypatch, tmp_path):
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    mapping, errs = label_map.build(_drafts_json())
    assert errs == [] and mapping["built_at"] > 0


def test_build_reuses_id_across_rebuilds(monkeypatch, tmp_path):
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    label_map.build(_drafts_json(), now=1.0)
    renamed = json.loads(_drafts_json())
    renamed[0]["canonical"] = "換了個名字的同一族"
    mapping, errs = label_map.build(json.dumps(renamed, ensure_ascii=False), now=2.0)
    assert errs == []
    assert mapping["concepts"][0]["id"] == "L001"


def test_build_writes_nothing_when_a_gate_fails(monkeypatch, tmp_path):
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    bad = json.loads(_drafts_json())
    bad[0]["members"][0]["label"] = "被竄改的 label"
    mapping, errs = label_map.build(json.dumps(bad, ensure_ascii=False), now=1.0)
    assert mapping is None and errs
    assert label_map.load() is None          # 全過才寫:一道不過就整份不落地


def test_build_reports_parse_error(monkeypatch, tmp_path):
    _use_fixtures(monkeypatch, tmp_path)
    mapping, errs = label_map.build("完全不是 JSON")
    assert mapping is None and len(errs) == 1


def test_build_rejects_empty_drafts(monkeypatch, tmp_path):
    _use_fixtures(monkeypatch, tmp_path)
    mapping, errs = label_map.build("[]")
    assert mapping is None and errs


def test_build_survives_garbage_inside_a_concept(monkeypatch, tmp_path):
    """members 不是陣列 / 成員不是物件 —— parse_drafts 擋不到這兩層,
    _stamp_quotes 必須跨過去而不是炸,再由 schema 報一個看得懂的錯。"""
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    for members in ("不是陣列", ["不是 dict"]):
        mapping, errs = label_map.build(json.dumps(
            [{"canonical": "x", "node_type": "theme", "members": members}],
            ensure_ascii=False))
        assert mapping is None and errs
        assert label_map.load() is None


def test_build_stamps_empty_quote_when_index_out_of_range(monkeypatch, tmp_path):
    """evidence_index 越界 → quote 蓋空字串,交給閘門報錯,不在 _stamp_quotes 炸,
    也不悄悄改成看起來合法的東西(例如夾到最後一條)。"""
    _seed_multi(tmp_path)
    _use_fixtures(monkeypatch, tmp_path)
    bad = json.loads(_drafts_json())
    bad[0]["members"][0]["evidence_index"] = 99      # s01/t1 只有 1 條
    mapping, errs = label_map.build(json.dumps(bad, ensure_ascii=False))
    assert mapping is None
    assert any("evidence_index" in e for e in errs)
    assert label_map.load() is None
