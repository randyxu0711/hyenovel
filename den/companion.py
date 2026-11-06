"""companion:陪讀角色的人格與素材(spec §3、§6)。

人格 = 共同底層 base.md + 角色讀法 characters/<id>.md,靠角色 id 對應。
"""
from functools import cache
from pathlib import Path

from marrow.prompt import Layer, Prompt
from marrow.workpacks import RunConfig

CHAT_RUN = RunConfig()
_PROMPTS = Path(__file__).resolve().parent.parent / "marrow" / "prompts"


@cache
def _read(rel: str) -> str:
    return (_PROMPTS / rel).read_text(encoding="utf-8")


def _persona_layers(character_id: str, voice: str) -> tuple[Layer, ...]:
    out = [Layer("base", _read("companion/base.md").rstrip() + "\n\n"),
           Layer("character", _read(f"characters/{character_id}.md").rstrip() + "\n\n")]
    if voice.strip():
        out.append(Layer("voice", voice.rstrip() + "\n\n"))
    return tuple(out)


def persona(character_id: str, voice: str = "") -> str:
    """共同底層 + 角色讀法;voice 非空時接在後面。"""
    return Prompt(_persona_layers(character_id, voice)).text.rstrip() + "\n"


_RUNNING = "這篇的結構分析還在背景跑,你現在是先憑原文讀。作者問進度,就用你自己的話說還在跑。"
_IDLE = "這篇目前沒有在跑結構分析,你憑原文讀。"


def assemble(ctx: dict, character: dict) -> Prompt:
    """companion 的 system prompt:人格、原文、精簡分析(不送 edges)、進度。"""
    layers = list(_persona_layers(character["id"], character["voice"]))
    layers.append(Layer("work", f"---\n# 《{ctx['title'] or ctx['slug']}》\n## 原文\n<source>\n"
                                f"{ctx['source'].rstrip()}\n</source>\n", material=True))
    a = ctx["analysis"]
    if a is not None:
        layers.append(Layer("analysis_header", "\n## 你讀的時候注意到的結構(私下筆記,不要原樣念給作者)\n"))
        lines = [f"梗概:{a['synopsis']}"] if a.get("synopsis") else []
        lines += [f"- {n['type']} {n['label']}" + (f":{n['note']}" if n.get("note") else "")
                  for n in a.get("nodes") or ()]
        layers.append(Layer("analysis", "".join(x + "\n" for x in lines), material=True))
    else:   # 有分析時在跑的是 reviewer
        status = _RUNNING if ctx["progress"] in ("queued", "running") else _IDLE
        layers.append(Layer("status", f"\n## 現在的狀況\n{status}\n"))
    return Prompt(tuple(layers))
