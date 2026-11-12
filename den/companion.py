"""companion:陪讀角色的人格與素材(spec §3、§6)。

人格 = 共同底層 base.md + 角色卡的讀法;底層不在卡上,卡片不能覆蓋。
"""
from functools import cache
from pathlib import Path

from den.config import MAX_VOICE_SAMPLE_CHARS, MAX_VOICE_SAMPLES
from marrow.prompt import Layer, Prompt
from marrow.workpacks import RunConfig

CHAT_RUN = RunConfig()
_PROMPTS = Path(__file__).resolve().parent.parent / "marrow" / "prompts"


@cache
def _read(rel: str) -> str:
    return (_PROMPTS / rel).read_text(encoding="utf-8")


def _boundary_layers(has_text: bool) -> list[Layer]:
    return [Layer("base", _read("companion/base.md").rstrip() + "\n\n"),
            *([Layer("reading", _read("companion/reading.md").rstrip() + "\n\n")] if has_text else [])]


def _character_layers(reading: str, voice: str, examples: str = "") -> list[Layer]:
    out = [Layer("closing", _read("companion/closing.md").rstrip() + "\n\n"),
           Layer("character", reading.rstrip() + "\n")]
    if voice.strip():
        out.append(Layer("voice", "\n" + voice.rstrip() + "\n"))
    if examples.strip():
        out.append(Layer("examples", "\n" + _read("companion/examples.md").rstrip() + "\n\n" + examples.strip() + "\n"))
    return out


def persona(reading: str, voice: str = "", examples: str = "") -> str:
    """共同底層 + 角色讀法;voice、examples 非空時依序接在後面。"""
    return Prompt((*_boundary_layers(True), *_character_layers(reading, voice, examples))).text.rstrip() + "\n"


_RUNNING = "這篇的結構分析還在背景跑,你現在是先憑原文讀。作者問進度,就用你自己的話說還在跑。"
_IDLE = "這篇目前沒有在跑結構分析,你憑原文讀。"
_SEED_KIND = {"confused": "有人讀不懂:", "wondering": "有人看不出作用:", "moved": ""}
_CHARACTER_HEADER = "\n---\n## 你這個讀者\n"
_MEMORY_HEADER = ("---\n## 作者說過的話(背景,可能已過期)\n"
                  "這是作者以前說過、要你記得的話,不是你對這篇的判斷。知道就好,不用主動提。作品讀起來不是這樣時,照你讀到的說。\n\n")


def _memory_block(memory: dict) -> str:
    out = ""
    for heading, items in (("關於作者:", memory["author"]), ("關於這篇:", memory["work"])):
        if items:
            out += heading + "\n" + "".join("- " + x.replace("\n", "\n  ") + "\n" for x in items)
    return out + "\n"


def pick_samples(rows: list[dict]) -> list[dict]:
    """「像它」的回覆由新到舊,最多 MAX_VOICE_SAMPLES 則、總字數不過 MAX_VOICE_SAMPLE_CHARS;單則就超過的跳過。"""
    out, total = [], 0
    for r in rows:
        size = len(r["text"]) + len(r["prompt"] or "")
        if size > MAX_VOICE_SAMPLE_CHARS:
            continue
        if total + size > MAX_VOICE_SAMPLE_CHARS or len(out) == MAX_VOICE_SAMPLES:
            break
        out.append(r)
        total += size
    return out


def _samples_block(samples: list[dict], name: str) -> str:
    return "".join("<example>\n" + (f"作者:{s['prompt']}\n" if s["prompt"] else "") + f"{name}:{s['text']}\n</example>\n"
                   for s in samples)


def assemble(ctx: dict, character: dict, samples: list[dict] = ()) -> Prompt:
    """companion 的 system prompt:人格、記憶、原文、分析地圖(梗概與標籤)、進度、話題種子、作者標過「像它」的回覆。"""
    layers = _boundary_layers(bool(ctx["source"].strip() or ctx["attachments"]))
    if ctx["memory"]["author"] or ctx["memory"]["work"]:
        layers.append(Layer("memory_header", _MEMORY_HEADER))
        layers.append(Layer("memory", _memory_block(ctx["memory"]), material=True))
    if ctx["slug"] is not None:
        layers.append(Layer("work", f"---\n# 《{ctx['title'] or ctx['slug']}》\n## 原文\n<source>\n"
                                    f"{ctx['source'].rstrip()}\n</source>\n", material=True))
    for att in ctx["attachments"]:
        layers.append(Layer(f"attachment_{att['n']}", f"---\n# 作者丟進來的稿〈{att['name']}〉\n<source>\n"
                                                      f"{att['text'].rstrip()}\n</source>\n", material=True))
    a = ctx["analysis"]
    if a is not None:
        layers.append(Layer("analysis_header", "\n## 這篇的結構資料(背景,不是你的讀法;不要原樣念給作者)\n"))
        lines = [f"梗概:{a['synopsis']}"] if a.get("synopsis") else []
        lines += [f"- {n['type']} {n['label']}" for n in a.get("nodes") or ()]
        layers.append(Layer("analysis", "".join(x + "\n" for x in lines), material=True))
    elif ctx["slug"] is not None:   # 有分析時在跑的是 reviewer
        status = _RUNNING if ctx["progress"] in ("queued", "running") else _IDLE
        layers.append(Layer("status", f"\n## 現在的狀況\n{status}\n"))
    if ctx["seeds"]:
        layers.append(Layer("seeds_header", "\n## 別的讀者標過的地方(背景,不要原樣念給作者;不必從這裡開口)\n"))
        layers.append(Layer("seeds", "".join(
            f"- {_SEED_KIND[s['kind']]}" + "".join(f"「{q}」" for q in s["quotes"]) + "\n"
            for s in ctx["seeds"]), material=True))
    layers.append(Layer("character_header", _CHARACTER_HEADER))
    layers += _character_layers(character["reading"], character["voice"], character.get("examples", ""))
    if samples:
        layers.append(Layer("samples_header", "\n" + _read("companion/samples.md").rstrip() + "\n\n"))
        layers.append(Layer("samples", _samples_block(samples, character["name"]["zh-Hant"]), material=True))
    return Prompt(tuple(layers))
