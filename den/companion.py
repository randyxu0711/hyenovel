"""companion:陪讀角色的人格與素材(spec §3、§6)。

人格 = 共同底層 + 一個行為模式;id 穩定不改(agent 靠語意挑、DB 存它),顯示名在 MODE_LABELS。
"""
from functools import cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "companion"

MODES = ("direct", "slow", "imaginative")
DEFAULT_MODE = "slow"
MODE_LABELS = {"direct": "直說", "slow": "慢讀", "imaginative": "想像"}


@cache
def _read(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def persona(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    return _read("base").rstrip() + "\n\n" + _read(mode).rstrip() + "\n"
