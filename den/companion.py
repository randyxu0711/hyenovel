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


_RUNNING = "這篇的結構分析還在背景跑,你現在是先憑原文讀。作者問進度,就用你自己的話說還在跑。"
_IDLE = "這篇目前沒有在跑結構分析,你憑原文讀。"


def render_companion(ctx: dict, mode: str) -> str:
    """companion 的 system prompt:人格、原文、精簡分析(不送 edges)、進度。"""
    out = [persona(mode).rstrip(), "", "---", f"# 《{ctx['title'] or ctx['slug']}》",
           "## 原文", "<source>", ctx["source"].rstrip(), "</source>"]
    a = ctx["analysis"]
    if a is not None:
        out += ["", "## 你讀的時候注意到的結構(私下筆記,不要原樣念給作者)"]
        if a.get("synopsis"):
            out.append(f"梗概:{a['synopsis']}")
        out += [f"- {n['type']} {n['label']}" + (f":{n['note']}" if n.get("note") else "")
                for n in a.get("nodes") or ()]
    if ctx["progress"] in ("queued", "running"):
        out += ["", "## 現在的狀況", _RUNNING]
    elif a is None:
        out += ["", "## 現在的狀況", _IDLE]
    return "\n".join(out) + "\n"
