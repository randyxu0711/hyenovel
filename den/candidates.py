"""角色候選:在人格軸上抽 3 個夠不同的位置,請工人各寫一張卡和一句試讀。不寫 DB。"""
import itertools
import json
import logging
import random
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from den import cards, pipeline
from marrow.repo import canonical_json
from marrow.workpacks import MAX_PREVIOUS_CHARS, RunConfig, assemble

log = logging.getLogger("hyenovel")

VOICE_AXIS = ("先聽聲音", "先看結構")
AXES = (("直說", "迂迴"), ("讀得快", "讀得慢"), VOICE_AXIS, ("溫和", "尖銳"))
COUNT = 3
MIN_AXES_APART = 2
RUN = RunConfig()
TIMEOUT = 180

_ROOT = Path(__file__).resolve().parent.parent / "marrow"
SCHEMA = json.loads((_ROOT / "schemas" / "candidates.v1.schema.json").read_text(encoding="utf-8"))
ONE = {**SCHEMA["properties"]["candidates"]["items"], "$defs": SCHEMA["$defs"]}
PASSAGE = (_ROOT / "prompts" / "sample_passage.md").read_text(encoding="utf-8").strip()


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


def positions(seed: int, drop_voice: bool = False) -> list[tuple[str, ...]]:
    combos = list(itertools.product(*(a for a in AXES if not (drop_voice and a == VOICE_AXIS))))
    random.Random(seed).shuffle(combos)
    return list(next(filter(_apart, itertools.combinations(combos, COUNT))))


def brief_from(answers: dict) -> str:
    form = answers.get("form")
    lines = [f"形體:{form}" if form else "形體:作者沒有定。三個候選各提一種不同類別的形體。"]
    clues = [answers.get("attention"), answers.get("returns") and f"讀完一篇先交回:{answers['returns']}", answers.get("response")]
    if any(clues):
        lines.append("作者對這類反應有興趣,是線索,不是角色定義:")
        lines += [f"- {c}" for c in clues if c]
    if answers.get("instance"):
        lines.append(f"作者覺得有用過的話,不要照用:{answers['instance']}")
    return "\n".join(lines)


def to_card(candidate: dict) -> dict:
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": candidate["name"]["zh-Hant"], "description": "", "tags": [], "creator": "hyenovel",
        "character_version": "", "mes_example": candidate["sample"], "system_prompt": "",
        "post_history_instructions": "", "first_mes": "", "alternate_greetings": [],
        "group_only_greetings": [], "personality": candidate["reading"], "scenario": "",
        "creator_notes": candidate["line"]["zh-Hant"],
        "extensions": {"hyenovel": {"name": candidate["name"], "line": candidate["line"], "form": candidate["form"]}},
    }}


def core(candidate) -> dict | None:
    """只留卡要用的欄位;不合 schema 回 None。前端帶來的 card、warnings 不會被用到。"""
    if not isinstance(candidate, dict):
        return None
    body = {k: candidate[k] for k in ONE["required"] if k in candidate}
    return body if Draft202012Validator(ONE).is_valid(body) else None


def _schema_errors(schema: dict, body: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(body)]


def _one_errors(body: dict) -> list[str]:
    return _schema_errors(ONE, body) or cards.scan(to_card(body))["errors"]


def _errors(body: dict) -> list[str]:
    bad = _schema_errors(SCHEMA, body)
    if bad:
        return bad
    items = body["candidates"]
    for label, values in (("名字重複", [c["name"]["zh-Hant"].strip() for c in items]),
                          ("名字重複", [c["name"]["en"].strip() for c in items]),
                          ("試讀重複", [c["sample"].strip() for c in items])):
        if len(set(values)) < len(values):
            bad.append(label)
    for i, c in enumerate(items, 1):
        bad += [f"候選 {i}: {code}" for code in cards.scan(to_card(c))["errors"]]
    return bad


def _input(brief: str, picked: list[tuple[str, ...]], lang: str) -> str:
    lines = "\n".join(f"候選 {i}:{'、'.join(pos)}" for i, pos in enumerate(picked, 1))
    return (f"<brief>\n{brief}\n</brief>\n<positions>\n{lines}\n</positions>\n<passage>\n{PASSAGE}\n</passage>\n"
            f"<interface_language>\n{lang}\n</interface_language>")


def _revise_input(candidate: dict, feedback: str, lang: str) -> str:
    return (f"<candidate>\n{canonical_json(candidate)}\n</candidate>\n<feedback>\n{feedback}\n</feedback>\n"
            f"<passage>\n{PASSAGE}\n</passage>\n<interface_language>\n{lang}\n</interface_language>")


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
    card = to_card(candidate)
    return {**candidate, "axes": list(pos), "card": card, "warnings": cards.scan(card)["warnings"]}


async def generate(run, answers: dict, lang: str, seed: int) -> dict:
    picked = positions(seed, drop_voice=bool(answers.get("attention")))
    body = await _gated(run, _prompt().text, SCHEMA, _errors, _input(brief_from(answers), picked, lang))
    return {"seed": seed, "candidates": [_shown(c, pos) for c, pos in zip(body["candidates"], picked, strict=True)]}


async def revise(run, candidate: dict, feedback: str, lang: str) -> dict:
    axes = candidate.get("axes")
    first = _revise_input(core(candidate), feedback, lang)
    body = await _gated(run, _revise_prompt().text, ONE, _one_errors, first)
    return _shown(body, axes if isinstance(axes, list) else ())
