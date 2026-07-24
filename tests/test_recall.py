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
