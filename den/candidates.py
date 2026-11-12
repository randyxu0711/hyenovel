"""角色候選:在人格軸上抽 3 個夠不同的位置,請工人各寫一張卡和一句試讀。不寫 DB。"""
import itertools
import json
import logging
import random
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from den import cards, figure, pipeline
from marrow.repo import canonical_json
from marrow.workpacks import MAX_PREVIOUS_CHARS, RunConfig, assemble

log = logging.getLogger("hyenovel")

AXES = (("直說", "迂迴"), ("讀得快", "讀得慢"), ("先聽聲音", "先看結構"), ("溫和", "尖銳"))
COUNT = 3
MIN_AXES_APART = 2
RUN = RunConfig()
TIMEOUT = 180
OPENING_CHARS = 200
MAX_PARTS = 8
MAX_COMMANDS = 80
FAMILIES = {
    "綠": ("pine", "olive", "moss"),
    "黃褐": ("sand", "ochre", "apricot", "bark", "bone"),
    "紅": ("rust", "rose"),
    "紫": ("plum",),
    "藍灰": ("slate",),
}

_ROOT = Path(__file__).resolve().parent.parent / "marrow"
SCHEMA = json.loads((_ROOT / "schemas" / "candidates.v1.schema.json").read_text(encoding="utf-8"))
_FIG = SCHEMA["$defs"]["figure"]["properties"]
_FIG["main"]["enum"] = _FIG["second"]["enum"] = list(figure.GRAMMAR["pens"])
_FIG["tempo"]["enum"] = figure.GRAMMAR["tempos"]
_FIG["move"]["enum"] = figure.GRAMMAR["moves"]
_FIG["parts"]["maxItems"] = MAX_PARTS
_FIG["parts"]["items"]["properties"]["group"]["enum"] = figure.GRAMMAR["groups"]
_FIG["parts"]["items"]["properties"]["fill"]["enum"] = figure.GRAMMAR["fills"]
_FIG["eyes"]["items"]["items"]["minimum"] = _FIG["mouth"]["items"]["items"]["minimum"] = figure.LIMITS["coord"][0]
_FIG["eyes"]["items"]["items"]["maximum"] = _FIG["mouth"]["items"]["items"]["maximum"] = figure.LIMITS["coord"][1]
ONE = {**SCHEMA["properties"]["candidates"]["items"], "$defs": SCHEMA["$defs"]}
STORY = (_ROOT / "prompts" / "example_story.md").read_text(encoding="utf-8").strip()
STORY_HEADER = f"那幾段聊的是{STORY}"
SITUATIONS = ("讀伴先開口,說讀到的一處反應。", "作者對自己的某個寫法沒把握。", "作者想加一段或改一段。")
_SPEAKER = {"author": "{{user}}", "char": "{{char}}"}


class Failed(Exception):
    """reason = runner 的 outcome,或 gate(修補一次後仍不合格)。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@cache
def _prompt():
    return assemble("candidates", SCHEMA)


@cache
def _revise_prompt():
    return assemble("candidate_revise", ONE)


def _apart(trio: tuple[tuple[str, ...], ...]) -> bool:
    return all(sum(x != y for x, y in zip(a, b)) >= MIN_AXES_APART for a, b in itertools.combinations(trio, 2))


def positions(seed: int) -> list[tuple[str, ...]]:
    combos = list(itertools.product(*AXES))
    random.Random(seed).shuffle(combos)
    return list(next(filter(_apart, itertools.combinations(combos, COUNT))))


def palettes(seed: int) -> list[str]:
    """三個候選各配一個主色色系,彼此不同。"""
    families = list(FAMILIES)
    random.Random(seed).shuffle(families)
    return families[:COUNT]


def _palette_error(candidate: dict, family: str) -> list[str]:
    main = candidate["figure"]["main"]
    return [] if main in FAMILIES[family] else [f"main 要從{family}色系挑:{'、'.join(FAMILIES[family])}"]


def brief_from(answers: dict) -> str:
    form = answers.get("form")
    lines = [f"形體:{form}" if form else "形體:作者沒有定。三個候選各提一種不同類別、具體有形的形體。"]
    if answers.get("wish"):
        lines.append(f"作者想要它這樣讀:{answers['wish']}")
    return "\n".join(lines)


def opening(works: list[dict]) -> str | None:
    """作者最近交的那篇的開頭;還沒有稿就是 None。"""
    latest = max(works, key=lambda w: w["submitted_at"], default=None)
    return latest["latest_text"][:OPENING_CHARS] if latest else None


def spec(fig: dict) -> dict:
    return {"parts": fig["parts"], "eyes": fig["eyes"], "mouth": fig["mouth"], "main": fig["main"],
            "second": fig["second"], "tempo": fig["tempo"], "move": fig["move"]}


def _inside(point, box) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= point[0] <= x1 and y0 <= point[1] <= y1


def _shape_error(fig: dict) -> list[str]:
    body = [p["d"] for p in fig["parts"] if p["group"] == "body"]
    if not body:
        return ["figure 要有 group 是 body 的部件"]
    boxes = [figure.bbox(d) for d in body]
    bad = [] if all(any(_inside(e, b) for b in boxes) for e in fig["eyes"]) else ["figure 的 eyes 要落在 body 裡"]
    if sum(figure.command_count(p["d"]) for p in fig["parts"]) > MAX_COMMANDS:
        bad.append(f"figure 全部部件加起來最多 {MAX_COMMANDS} 個指令")
    return bad


def _figure_error(candidate: dict) -> list[str]:
    fig = candidate["figure"]
    same = ["main 和 second 要是不同的筆"] if fig["main"] == fig["second"] else []
    drawn = [f"figure {e}" for e in figure.errors(spec(fig))]
    return same + (drawn or _shape_error(fig))


def mes_example(examples: list[list[dict]]) -> str:
    blocks = ["<example>\n" + "\n".join(f"{_SPEAKER[t['who']]}:{t['text'].strip()}" for t in turns) + "\n</example>"
              for turns in examples]
    return "\n\n".join([STORY_HEADER, *blocks]) + "\n"


def to_card(candidate: dict) -> dict:
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": candidate["name"]["zh-Hant"], "description": "", "tags": [], "creator": "hyenovel",
        "character_version": "", "mes_example": mes_example(candidate["examples"]), "system_prompt": "",
        "post_history_instructions": "", "first_mes": "", "alternate_greetings": [],
        "group_only_greetings": [], "personality": candidate["reading"], "scenario": "",
        "creator_notes": candidate["line"]["zh-Hant"],
        "extensions": {"hyenovel": {"name": candidate["name"], "line": candidate["line"], "form": candidate["form"],
                                    "figure": spec(candidate["figure"]),
                                    "colors": figure.pen_colors(candidate["figure"]["main"])}},
    }}


def core(candidate) -> dict | None:
    """只留卡要用的欄位;不合 schema 回 None。前端帶來的 card、warnings 不會被用到。"""
    if not isinstance(candidate, dict):
        return None
    body = {k: candidate[k] for k in ONE["required"] if k in candidate}
    return body if Draft202012Validator(ONE).is_valid(body) else None


def _schema_errors(schema: dict, body: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(body)]


def _sample_error(candidate: dict, passage: str | None) -> list[str]:
    if passage and not candidate["sample"].strip():
        return ["有 <passage> 時 sample 不能空白"]
    if not passage and candidate["sample"]:
        return ["沒有 <passage> 時 sample 要留空"]
    return []


def _examples_error(candidate: dict) -> list[str]:
    bad = []
    for i, turns in enumerate(candidate["examples"], 1):
        if not any(t["who"] == "char" for t in turns):
            bad.append(f"examples 第 {i} 段沒有 char 說的話")
        if any("<example" in t["text"] or "</example" in t["text"] for t in turns):
            bad.append(f"examples 第 {i} 段的 text 不能含 <example> 標籤")
    return bad


def _one_errors(body: dict, passage: str | None) -> list[str]:
    return (_schema_errors(ONE, body) or _sample_error(body, passage) + _examples_error(body) or _figure_error(body)
            or cards.scan(to_card(body))["errors"])


def _errors(body: dict, passage: str | None, picked_palettes: list[str], named: bool) -> list[str]:
    bad = _schema_errors(SCHEMA, body)
    if bad:
        return bad
    items = body["candidates"]
    names = [] if named else [("名字重複", [c["name"]["zh-Hant"].strip() for c in items]),
                              ("名字重複", [c["name"]["en"].strip() for c in items])]
    for label, values in (*names,
                          ("試讀重複", [c["sample"].strip() for c in items if c["sample"].strip()]),
                          ("主色重複", [c["figure"]["main"] for c in items])):
        if len(set(values)) < len(values):
            bad.append(label)
    for i, (c, family) in enumerate(zip(items, picked_palettes), 1):
        bad += [f"候選 {i}: {code}" for code in _sample_error(c, passage) + _examples_error(c) + _figure_error(c)
                + _palette_error(c, family) + cards.scan(to_card(c))["errors"]]
    return bad


def _library() -> str:
    pens = {k: v["light"] for k, v in figure.GRAMMAR["pens"].items()}
    return f"<pens>\n{canonical_json(pens)}\n</pens>\n"


def _story_block() -> str:
    lines = "\n".join(f"{i}. {s}" for i, s in enumerate(SITUATIONS, 1))
    return f"<example_story>\n{STORY}\n</example_story>\n<example_situations>\n{lines}\n</example_situations>\n"


def _passage_block(passage: str | None) -> str:
    return f"<passage>\n{passage}\n</passage>\n" if passage else ""


def _again_block(again: dict | None, named: bool) -> str:
    if not again or not again.get("previous"):
        return ""
    listed = "\n".join(f"{i}. {p['line']}" if named else f"{i}. {p['name']}:{p['line']}"
                       for i, p in enumerate(again["previous"], 1))
    reaction = again.get("reaction", "").strip()
    return f"<previous>\n{listed}\n</previous>\n" + (f"<reaction>\n{reaction}\n</reaction>\n" if reaction else "")


def _input(brief: str, picked: list[tuple[str, ...]], picked_palettes: list[str], passage: str | None,
           lang: str, again: dict | None = None, named: bool = False) -> str:
    lines = "\n".join(f"候選 {i}:{'、'.join(pos)}" for i, pos in enumerate(picked, 1))
    colors = "\n".join(f"候選 {i}:{family}色系,{'、'.join(FAMILIES[family])}"
                       for i, family in enumerate(picked_palettes, 1))
    return (f"<brief>\n{brief}\n</brief>\n{_again_block(again, named)}<positions>\n{lines}\n</positions>\n"
            f"<colors>\n{colors}\n</colors>\n{_library()}{_story_block()}{_passage_block(passage)}"
            f"<interface_language>\n{lang}\n</interface_language>")


def _revise_input(candidate: dict, feedback: str, passage: str | None, lang: str) -> str:
    return (f"<candidate>\n{canonical_json(candidate)}\n</candidate>\n<feedback>\n{feedback}\n</feedback>\n"
            f"{_library()}{_story_block()}{_passage_block(passage)}<interface_language>\n{lang}\n</interface_language>")


def _repair(first: str, previous: str, errors: list[str], parsed: bool) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    ask = ("上一份輸出沒通過驗證,逐條錯誤如下。修正這些問題後重交整份 JSON,其餘內容保持不變:" if parsed
           else "上一份輸出無法解析成單一 JSON 物件(可能被截斷了)。請依輸出格式從頭重交完整的 JSON:")
    return f"{first}\n<previous_output>\n{previous}\n</previous_output>\n{ask}\n{listed}"


async def _attempt(run, system: str, schema: dict, check, prompt: str):
    r = await run(system, prompt, schema, config=RUN, timeout=TIMEOUT)
    pipeline.check_anomaly(None, "candidates", r)
    if r.outcome != "ok":
        log.info("event=candidates-failed reason=%s", r.outcome)
        raise Failed(r.outcome)
    if r.parsed is None:
        return None, (r.text or "")[:MAX_PREVIOUS_CHARS], ["輸出無法解析成單一 JSON 物件"]
    return r.parsed, canonical_json(r.parsed), check(r.parsed)


async def _gated(run, system: str, schema: dict, check, first: str) -> dict:
    body, previous, errors = await _attempt(run, system, schema, check, first)
    if errors:
        log.info("event=candidates-repair errors=%d", len(errors))
        body, _, errors = await _attempt(run, system, schema, check, _repair(first, previous, errors, body is not None))
    if errors:
        log.info("event=candidates-failed reason=gate errors=%d", len(errors))
        raise Failed("gate")
    return body


def _shown(candidate: dict, pos) -> dict:
    candidate = {**candidate, "figure": figure.fit(candidate["figure"])}
    card = to_card(candidate)
    return {**candidate, "axes": list(pos), "card": card, "warnings": cards.scan(card)["warnings"]}


async def generate(run, answers: dict, passage: str | None, lang: str, seed: int, again: dict | None = None) -> dict:
    picked, picked_palettes = positions(seed), palettes(seed)
    named = bool((answers.get("form") or "").strip())
    check = lambda body: _errors(body, passage, picked_palettes, named)
    first = _input(brief_from(answers), picked, picked_palettes, passage, lang, again, named)
    body = await _gated(run, _prompt().text, SCHEMA, check, first)
    items = [{**c, "name": dict(c["form"])} if named else c for c in body["candidates"]]
    return {"seed": seed, "candidates": [_shown(c, pos) for c, pos in zip(items, picked, strict=True)]}


async def revise(run, candidate: dict, feedback: str, passage: str | None, lang: str) -> dict:
    axes = candidate.get("axes")
    first = _revise_input(core(candidate), feedback, passage, lang)
    check = lambda body: _one_errors(body, passage)
    body = await _gated(run, _revise_prompt().text, ONE, check, first)
    return _shown(body, axes if isinstance(axes, list) else ())
