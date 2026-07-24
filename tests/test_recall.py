import json as _json

import recall


def test_est_tokens_counts_chars():
    assert recall.est_tokens("關燈") == 2
    assert recall.est_tokens("") == 0
    assert recall.est_tokens(None) == 0


def test_layer_observation_only_sees_observation():
    assert recall._layer_allows("observation", "observation") is True
    assert recall._layer_allows("judgment", "observation") is False
    assert recall._layer_allows("question", "observation") is False


def test_layer_judgment_sees_all_three():
    for kind in ("observation", "judgment", "question"):
        assert recall._layer_allows(kind, "judgment") is True


def test_layer_unknown_layer_allows_nothing():
    assert recall._layer_allows("observation", "bogus") is False


def test_stale_true_when_invalidated():
    c = {"invalidated_at": 123.0, "provenance": {"analysis_fp": "abc"}}
    assert recall._stale(c, "abc") is True


def test_stale_true_when_fp_mismatch():
    c = {"invalidated_at": None, "provenance": {"analysis_fp": "old"}}
    assert recall._stale(c, "new") is True


def test_stale_false_when_fp_matches():
    c = {"invalidated_at": None, "provenance": {"analysis_fp": "same"}}
    assert recall._stale(c, "same") is False


def test_stale_false_when_no_current_fp():
    """cur_fp 空('' = 無無從指紋)→ 無從判斷,不誤標 stale。"""
    c = {"invalidated_at": None, "provenance": {"analysis_fp": "whatever"}}
    assert recall._stale(c, "") is False


def _edges():
    # k1 --produces--> e1 --serves--> t1   (權重 1.0 / 1.0)
    return [{"type": "produces", "from": "k1", "to": "e1"},
            {"type": "serves", "from": "e1", "to": "t1"}]


def test_expand_anchor_itself_is_zero_hop():
    r = recall._expand(["e1"], _edges(), hops=0)
    assert r == {"e1": (0, 1.0)}


def test_expand_one_hop_reaches_neighbours_both_directions():
    r = recall._expand(["e1"], _edges(), hops=1)
    assert r["e1"] == (0, 1.0)
    assert r["k1"] == (1, 1.0), "沿 produces 反向也走得到(無向)"
    assert r["t1"] == (1, 1.0), "沿 serves 正向"


def test_expand_two_hops_reaches_further_with_correct_distance():
    r = recall._expand(["k1"], _edges(), hops=2)
    assert r["k1"] == (0, 1.0)
    assert r["e1"] == (1, 1.0)
    assert r["t1"] == (2, 1.0), "k1→e1→t1 是兩跳,不能被誤算成一跳"


def test_expand_unknown_edge_type_weight_zero():
    edges = [{"type": "relates_to", "from": "a", "to": "b"},
             {"type": "bogus", "from": "b", "to": "c"}]
    r = recall._expand(["a"], edges, hops=2)
    assert r["b"] == (1, 0.3)
    assert r["c"] == (2, 0.0), "未知邊型權重 0,但仍可走"


def test_expand_stops_when_no_new_nodes():
    r = recall._expand(["e1"], _edges(), hops=99)
    assert set(r) == {"e1", "k1", "t1"}, "走完就停,不無限跑"


def _nodes():
    return {"e1": {"id": "e1", "type": "effect", "intensity": 0.6},
            "t1": {"id": "t1", "type": "theme"}}


def _c(cid, refs, ts, fp="fp1", inval=None, text="x"):
    return {"id": cid, "kind": "judgment", "text": text, "refs": refs, "ts": ts,
            "provenance": {"analysis_fp": fp}, "invalidated_at": inval}


def test_rank_exact_anchor_hit_wins():
    reached = recall._expand(["e1"], _edges(), hops=1)
    exact = _c("c1", ["e1"], ts=1.0)      # 命中錨點 e1
    far = _c("c2", ["t1"], ts=9.0)        # 只是被擴張到,ts 更新
    out = recall._rank([far, exact], reached, ["e1"], _nodes(), "fp1")
    assert [c["id"] for c, _ in out] == ["c1", "c2"], "精確命中錨點排最前,壓過 ts"


def test_rank_stale_sorts_last_and_flagged():
    reached = recall._expand(["e1"], _edges(), hops=1)
    fresh = _c("c1", ["t1"], ts=1.0, fp="fp1")
    stale = _c("c2", ["e1"], ts=9.0, fp="OLD")   # 精確命中但 fp 不符 → 懸空
    out = recall._rank([stale, fresh], reached, ["e1"], _nodes(), "fp1")
    assert out[-1][0]["id"] == "c2" and out[-1][1] is True, "懸空排最後且標記"
    assert out[0][1] is False


def test_rank_closer_hop_beats_farther():
    reached = recall._expand(["k1"], _edges(), hops=2)   # e1=1跳, t1=2跳
    near = _c("c1", ["e1"], ts=1.0)
    far = _c("c2", ["t1"], ts=1.0)
    out = recall._rank([far, near], reached, ["k1"], _nodes(), "fp1")
    assert [c["id"] for c, _ in out] == ["c1", "c2"], "近跳優先於遠跳"


def test_truncate_keeps_under_budget_and_flags():
    ranked = [(_c("c1", [], 1.0, text="12345"), False),
              (_c("c2", [], 1.0, text="67890"), False),
              (_c("c3", [], 1.0, text="XXXXX"), False)]
    kept, truncated = recall._truncate(ranked, budget_tokens=10)
    assert [c["id"] for c, _ in kept] == ["c1", "c2"], "5+5=10 剛好,第三條溢出"
    assert truncated is True


def test_truncate_always_keeps_first_even_if_over():
    ranked = [(_c("c1", [], 1.0, text="超過預算的一長串文字"), False)]
    kept, truncated = recall._truncate(ranked, budget_tokens=1)
    assert [c["id"] for c, _ in kept] == ["c1"], "空手而回更無用,至少放第一條"
    assert truncated is False, "只有一條且放了,不算截斷"


def _seed(tmp_path, monkeypatch, conclusions_rows, feedback=None, fp_match=True):
    """在 tmp 造一篇 s01:analysis(k1→e1→t1)、conclusions.jsonl、可選 feedback。
    conclusions 的 provenance.analysis_fp 依 fp_match 對齊/不對齊當前 analysis 指紋。"""
    import conclusions
    S = tmp_path / "stories"
    (S / "s01").mkdir(parents=True)
    (S / "s01" / "source.md").write_text("他把燈關了。", encoding="utf-8")
    (S / "s01" / "analysis.json").write_text(_json.dumps({
        "slug": "s01",
        "nodes": [{"id": "k1", "type": "technique", "label": "擬人"},
                  {"id": "e1", "type": "effect", "label": "空缺感", "intensity": 0.6,
                   "evidence": [{"quote": "他把燈關了。"}]},
                  {"id": "t1", "type": "theme", "label": "落空"}],
        "edges": [{"type": "produces", "from": "k1", "to": "e1"},
                  {"type": "serves", "from": "e1", "to": "t1"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(recall, "STORIES", S)
    monkeypatch.setattr(conclusions, "STORIES", S)
    cur_fp = conclusions.analysis_fp("s01")
    fp = cur_fp if fp_match else "STALE"
    lines = []
    for row in conclusions_rows:
        row = {**row}
        row.setdefault("ts", 1.0)
        row.setdefault("invalidated_at", None)
        row["provenance"] = {"session": "s", "turns": [0, 0], "analysis_fp": fp}
        lines.append(_json.dumps(row, ensure_ascii=False))
    (S / "s01" / "conclusions.jsonl").write_text("\n".join(lines), encoding="utf-8")
    if feedback is not None:
        (S / "s01" / "feedback.json").write_text(_json.dumps(feedback, ensure_ascii=False), encoding="utf-8")


def test_recall_missing_story_returns_empty_payload(tmp_path, monkeypatch):
    import conclusions
    monkeypatch.setattr(recall, "STORIES", tmp_path / "stories")
    monkeypatch.setattr(conclusions, "STORIES", tmp_path / "stories")
    out = recall.recall("nope")
    assert out == {"anchors": [], "conclusions": [], "nodes": [], "feedback": [], "truncated": False}


def test_recall_observation_layer_never_returns_judgment(tmp_path, monkeypatch):
    """地基硬閘門:layer='observation' 在程式上取不到 judgment/question/feedback。"""
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "observation", "text": "觀察一句", "refs": ["e1"], "quotes": []},
        {"id": "c2", "kind": "judgment", "text": "判斷一句", "refs": ["e1"], "quotes": []},
        {"id": "c3", "kind": "question", "text": "一個提問", "refs": ["e1"], "quotes": []},
    ], feedback={"slug": "s01", "read": "r", "one_line": "o",
                 "key_points": [{"title": "kp", "body": "b", "refs": ["e1"], "quotes": ["他把燈關了。"]}]})
    out = recall.recall("s01", anchors=["e1"], layer="observation")
    kinds = {c["kind"] for c in out["conclusions"]}
    assert kinds == {"observation"}, f"observation 層只能有 observation,實際 {kinds}"
    assert out["feedback"] == [], "observation 層不得回 feedback"


def test_recall_judgment_layer_sees_all_and_feedback(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "observation", "text": "觀察", "refs": ["e1"], "quotes": []},
        {"id": "c2", "kind": "judgment", "text": "判斷", "refs": ["e1"], "quotes": []},
    ], feedback={"slug": "s01", "read": "r", "one_line": "o",
                 "key_points": [{"title": "kp", "body": "b", "refs": ["e1"], "quotes": ["他把燈關了。"]}]})
    out = recall.recall("s01", anchors=["e1"], layer="judgment")
    assert {c["kind"] for c in out["conclusions"]} == {"observation", "judgment"}
    assert out["feedback"] and out["feedback"][0]["title"] == "kp"


def test_recall_default_anchors_from_feedback_key_points(tmp_path, monkeypatch):
    """anchors 空 → 取 feedback key_points 的 refs 當預設錨點(spec §3-1)。"""
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "judgment", "text": "判斷", "refs": ["e1"], "quotes": []},
    ], feedback={"slug": "s01", "read": "r", "one_line": "o",
                 "key_points": [{"title": "kp", "body": "b", "refs": ["e1"], "quotes": ["他把燈關了。"]}]})
    out = recall.recall("s01", layer="judgment")   # 不給 anchors
    assert out["anchors"] == ["e1"], "預設錨點來自 feedback key_points 的 refs"


def test_recall_flags_stale_when_fp_moved(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "judgment", "text": "舊判斷", "refs": ["e1"], "quotes": []},
    ], fp_match=False)
    out = recall.recall("s01", anchors=["e1"], layer="judgment")
    assert out["conclusions"][0]["stale"] is True, "fp 不符 → 標記懸空"


def test_recall_nodes_carry_label_and_evidence_quotes(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "judgment", "text": "判斷", "refs": ["e1"], "quotes": []},
    ])
    out = recall.recall("s01", anchors=["e1"], layer="judgment")
    e1 = next(n for n in out["nodes"] if n["id"] == "e1")
    assert e1["label"] == "空缺感"
    assert e1["quotes"] == ["他把燈關了。"]


def test_recall_budget_truncates(tmp_path, monkeypatch):
    rows = [{"id": f"c{i}", "kind": "judgment", "text": "十個字十個字十", "refs": ["e1"], "quotes": []}
            for i in range(5)]
    _seed(tmp_path, monkeypatch, rows)
    out = recall.recall("s01", anchors=["e1"], layer="judgment", budget_tokens=15)
    assert out["truncated"] is True
    assert 0 < len(out["conclusions"]) < 5


def test_default_anchors_dedupes_repeated_refs():
    """同一個 ref 在多個 key_points 出現只收一次(純函式分支)。"""
    fb = {"key_points": [{"refs": ["e1"]}, {"refs": ["e1", "e2"]}]}
    assert recall._default_anchors(fb) == ["e1", "e2"]


def test_recall_skips_reached_node_missing_from_analysis(tmp_path, monkeypatch):
    """reached 節點若不在 analysis nodes(壞邊指到不存在節點)→ payload_nodes 跳過,不炸。"""
    import conclusions
    S = tmp_path / "stories"
    (S / "s01").mkdir(parents=True)
    (S / "s01" / "source.md").write_text("他把燈關了。", encoding="utf-8")
    (S / "s01" / "analysis.json").write_text(_json.dumps({
        "slug": "s01",
        "nodes": [{"id": "e1", "type": "effect", "label": "空缺感"}],
        "edges": [{"type": "relates_to", "from": "e1", "to": "ghost"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(recall, "STORIES", S)
    monkeypatch.setattr(conclusions, "STORIES", S)
    (S / "s01" / "conclusions.jsonl").write_text("", encoding="utf-8")
    out = recall.recall("s01", anchors=["e1"], layer="judgment")
    ids = {n["id"] for n in out["nodes"]}
    assert "ghost" not in ids, "壞邊指到的不存在節點不進 payload"
    assert "e1" in ids


def test_recall_feedback_filters_non_intersecting_key_points(tmp_path, monkeypatch):
    """feedback key_points 裡 refs 沒命中 reached 的那條被濾掉,不進 payload。"""
    _seed(tmp_path, monkeypatch, [
        {"id": "c1", "kind": "judgment", "text": "判斷", "refs": ["e1"], "quotes": []},
    ], feedback={"slug": "s01", "read": "r", "one_line": "o",
                 "key_points": [
                     {"title": "kp1", "body": "b1", "refs": ["e1"], "quotes": ["他把燈關了。"]},
                     {"title": "kp2", "body": "b2", "refs": ["nope"], "quotes": []},
                 ]})
    out = recall.recall("s01", anchors=["e1"], layer="judgment")
    titles = {f["title"] for f in out["feedback"]}
    assert titles == {"kp1"}, "不命中 reached 的 key_point 應被濾掉"


def test_format_recall_empty_when_no_conclusions():
    assert recall.format_recall({"conclusions": []}) == ""


def test_format_recall_lists_conclusions_and_marks_stale():
    payload = {"conclusions": [
        {"id": "c1", "kind": "judgment", "text": "收尾太快", "refs": ["e1"], "stale": False},
        {"id": "c2", "kind": "observation", "text": "舊觀察", "refs": ["t1"], "stale": True},
    ]}
    s = recall.format_recall(payload)
    assert "收尾太快" in s and "(e1)" in s
    assert "舊觀察" in s and "懸空" in s, "懸空結論要帶警示"
