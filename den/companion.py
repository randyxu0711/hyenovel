"""companion:陪讀角色的人格與素材(spec §3、§6)。

人格 = 共同底層 base.md + 角色讀法 characters/<id>.md,靠角色 id 對應。
"""
from functools import cache
from pathlib import Path

from marrow.workpacks import RunConfig

CHAT_RUN = RunConfig()
_PROMPTS = Path(__file__).resolve().parent.parent / "marrow" / "prompts"


@cache
def _read(rel: str) -> str:
    return (_PROMPTS / rel).read_text(encoding="utf-8")


def persona(character_id: str, voice: str = "") -> str:
    """共同底層 + 角色讀法;voice 非空時接在後面。"""
    out = _read("companion/base.md").rstrip() + "\n\n" + _read(f"characters/{character_id}.md").rstrip() + "\n"
    return out + "\n" + voice.rstrip() + "\n" if voice.strip() else out


_RUNNING = "這篇的結構分析還在背景跑,你現在是先憑原文讀。作者問進度,就用你自己的話說還在跑。"
_IDLE = "這篇目前沒有在跑結構分析,你憑原文讀。"


def render_companion(ctx: dict, character: dict) -> str:
    """companion 的 system prompt:人格、原文、精簡分析(不送 edges)、進度。"""
    out = [persona(character["id"], character["voice"]).rstrip(), "", "---", f"# 《{ctx['title'] or ctx['slug']}》",
           "## 原文", "<source>", ctx["source"].rstrip(), "</source>"]
    a = ctx["analysis"]
    if a is not None:
        out += ["", "## 你讀的時候注意到的結構(私下筆記,不要原樣念給作者)"]
        if a.get("synopsis"):
            out.append(f"梗概:{a['synopsis']}")
        out += [f"- {n['type']} {n['label']}" + (f":{n['note']}" if n.get("note") else "")
                for n in a.get("nodes") or ()]
    if a is None and ctx["progress"] in ("queued", "running"):   # 有分析時在跑的是 reviewer
        out += ["", "## 現在的狀況", _RUNNING]
    elif a is None:
        out += ["", "## 現在的狀況", _IDLE]
    return "\n".join(out) + "\n"
