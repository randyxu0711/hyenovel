"""den.estimate:字數 × 每步 attempt 歷史平均。"""
from den.estimate import estimate


def _h(chars, ms, out):
    return {"chars": chars, "duration_ms": ms, "tokens": {"output": out}}


def test_no_history_returns_none():
    assert estimate({"analyst": [_h(1000, 60_000, 500)], "criticizer": []}, 2000) is None
    assert estimate({}, 2000) is None


def test_scales_by_chars():
    hist = {"analyst": [_h(1000, 60_000, 500)], "criticizer": [_h(1000, 30_000, 100)]}
    assert estimate(hist, 2000) == {"seconds": 180, "output_tokens": 1200, "basis": 1}


def test_basis_is_min_samples():
    hist = {"analyst": [_h(1000, 60_000, 500), _h(2000, 60_000, 500)],
            "criticizer": [_h(1000, 30_000, 100)]}
    assert estimate(hist, 1000)["basis"] == 1
    # analyst 每字中位數 = (60 + 30)/2 ms → 1000 字 45 秒;criticizer 30 秒
    assert estimate(hist, 1000)["seconds"] == 75


def test_missing_tokens_are_skipped_not_zeroed():
    hist = {"analyst": [_h(1000, 60_000, 500), {"chars": 1000, "duration_ms": 60_000,
                                                 "tokens": None}]}
    assert estimate(hist, 1000) == {"seconds": 60, "output_tokens": 500, "basis": 2}


def test_zero_char_rows_skipped_no_division_by_zero():
    hist = {"analyst": [_h(0, 1000, 5), _h(1000, 60_000, 500)], "criticizer": [_h(1000, 30_000, 100)]}
    assert estimate(hist, 1000)["seconds"] == 90
    assert estimate({"analyst": [_h(0, 1000, 5)]}, 1000) is None


def test_median_resists_outlier():
    """舊配方一筆 588s 離群值不能把約 1.5 分鐘的預估拉到 6 分鐘(平均會)。"""
    hist = {"analyst": [_h(1000, 60_000, 500), _h(1000, 70_000, 600), _h(1000, 588_000, 9000)]}
    assert estimate(hist, 1000) == {"seconds": 70, "output_tokens": 600, "basis": 3}
