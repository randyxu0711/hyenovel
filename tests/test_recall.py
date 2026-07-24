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
