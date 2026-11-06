"""companion:陪讀角色的人格與素材(spec §3、§6)。

人格 = 共同底層 base.md + 角色卡的讀法;底層不在卡上,卡片不能覆蓋。
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


def _persona_layers(reading: str, voice: str) -> tuple[Layer, ...]:
    out = [Layer("base", _read("companion/base.md").rstrip() + "\n\n"),
           Layer("character", reading.rstrip() + "\n\n")]
    if voice.strip():
        out.append(Layer("voice", voice.rstrip() + "\n\n"))
    return tuple(out)


def persona(reading: str, voice: str = "") -> str:
    """共同底層 + 角色讀法;voice 非空時接在後面。"""
    return Prompt(_persona_layers(reading, voice)).text.rstrip() + "\n"


_RUNNING = "這篇的結構分析還在背景跑,你現在是先憑原文讀。作者問進度,就用你自己的話說還在跑。"
_IDLE = "這篇目前沒有在跑結構分析,你憑原文讀。"
_SEED_KIND = {"confused": "讀到卡住:", "wondering": "看不出作用:", "moved": ""}
_MEMORY_HEADER = ("---\n## 作者說過的話(背景,可能已過期)\n"
                  "這是作者以前說過、要你記得的話,不是你對這篇的判斷。知道就好,不用主動提。作品讀起來不是這樣時,照你讀到的說。\n\n")


def _memory_block(memory: dict) -> str:
    out = ""
    for heading, items in (("關於作者:", memory["author"]), ("關於這篇:", memory["work"])):
        if items:
            out += heading + "\n" + "".join("- " + x.replace("\n", "\n  ") + "\n" for x in items)
    return out + "\n"


def assemble(ctx: dict, character: dict) -> Prompt:
    """companion 的 system prompt:人格、記憶、原文、分析地圖(梗概與標籤)、進度、話題種子。"""
    layers = list(_persona_layers(character["reading"], character["voice"]))
    if ctx["memory"]["author"] or ctx["memory"]["work"]:
        layers.append(Layer("memory_header", _MEMORY_HEADER))
        layers.append(Layer("memory", _memory_block(ctx["memory"]), material=True))
    layers.append(Layer("work", f"---\n# 《{ctx['title'] or ctx['slug']}》\n## 原文\n<source>\n"
                                f"{ctx['source'].rstrip()}\n</source>\n", material=True))
    a = ctx["analysis"]
    if a is not None:
        layers.append(Layer("analysis_header", "\n## 你讀的時候注意到的結構(私下筆記,不要原樣念給作者)\n"))
        lines = [f"梗概:{a['synopsis']}"] if a.get("synopsis") else []
        lines += [f"- {n['type']} {n['label']}" for n in a.get("nodes") or ()]
        layers.append(Layer("analysis", "".join(x + "\n" for x in lines), material=True))
    else:   # 有分析時在跑的是 reviewer
        status = _RUNNING if ctx["progress"] in ("queued", "running") else _IDLE
        layers.append(Layer("status", f"\n## 現在的狀況\n{status}\n"))
    if ctx["seeds"]:
        layers.append(Layer("seeds_header", "\n## 可以聊的地方(私下筆記,不要原樣念給作者)\n"))
        layers.append(Layer("seeds", "".join(
            f"- {_SEED_KIND[s['kind']]}" + "".join(f"「{q}」" for q in s["quotes"]) + "\n"
            for s in ctx["seeds"]), material=True))
    return Prompt(tuple(layers))
