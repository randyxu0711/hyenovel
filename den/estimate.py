"""開跑前預估(§3.3):字數 × 每步 attempt 歷史的「每字」平均。純函式。

訂閱 runner 不給金額,只給時間與 output token。
"""


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def estimate(history: dict[str, list[dict]], chars: int) -> dict | None:
    """history = {step: repo.attempt_history(step)};任一步沒歷史 → None。"""
    history = {s: [r for r in h if r["chars"]] for s, h in history.items()}   # 空原文不能當分母
    if not history or any(not h for h in history.values()):
        return None
    ms = toks = 0.0
    for rows in history.values():
        ms += _mean([r["duration_ms"] / r["chars"] for r in rows]) * chars
        # 沒 token 紀錄的樣本略過,不當 0 拉低平均
        toks += _mean([r["tokens"]["output"] / r["chars"] for r in rows
                       if (r["tokens"] or {}).get("output") is not None]) * chars
    return {"seconds": round(ms / 1000), "output_tokens": round(toks),
            "basis": min(len(h) for h in history.values())}
