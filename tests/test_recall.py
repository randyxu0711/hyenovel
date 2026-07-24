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
