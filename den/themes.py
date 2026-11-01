"""佈景主題登記表(spec §4.7):內建主題是 marrow/themes/*.json,對比規則 check_theme 是純函式。"""
import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "marrow" / "themes"

DEFAULT_THEME = "olive"
KEYS = ("desk", "desk-2", "paper", "paper-ink", "paper-ink-2", "ink", "ink-2",
        "line", "accent", "accent-ink", "spot", "sheen")


def _lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    """WCAG 對比值,兩個 #rrggbb。"""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def check_theme(theme: dict) -> list[str]:
    """鍵集合與對比規則(spec §4.5、改版 §6.1);回傳不合格的描述,空 list = 合格。line/spot/sheen 帶透明度,不驗。"""
    bad = []
    for scheme in ("light", "dark"):
        t = theme[scheme]
        extra, missing = sorted(set(t) - set(KEYS)), sorted(set(KEYS) - set(t))
        if extra or missing:
            bad.append(f"{theme['id']} {scheme} 鍵不符: 多 {extra} 少 {missing}")
            continue

        def need(ink: str, bg: str, lo: float, hi: float = float("inf")):
            r = contrast(t[ink], t[bg])
            if not lo <= r <= hi:
                bad.append(f"{theme['id']} {scheme} {ink}/{bg} = {r:.2f}")
        need("ink", "desk", 10, 13)
        need("ink-2", "desk", 4.5)
        need("ink-2", "desk-2", 4.5)
        need("paper-ink", "paper", 9.5)
        need("paper-ink-2", "paper", 4.5)
        need("accent-ink", "accent", 4.5)
    return bad


@cache
def _load() -> tuple[dict, ...]:
    out = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_DIR.glob("*.json"))]
    ids = [t["id"] for t in out]
    if len(set(ids)) != len(ids):
        raise ValueError(f"theme id 重複: {ids}")
    for t in out:
        for scheme in ("light", "dark"):
            if set(t[scheme]) != set(KEYS):
                raise ValueError(f"theme {t['id']} {scheme} 鍵不齊")
    if DEFAULT_THEME not in ids:
        raise ValueError("缺預設主題")
    return tuple(out)


def builtins() -> list[dict]:
    return list(_load())
