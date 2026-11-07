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

AXES = (("直說", "迂迴"), ("讀得快", "讀得慢"), ("先聽聲音", "先看結構"), ("溫和", "尖銳"))
COUNT = 3
MIN_AXES_APART = 2
RUN = RunConfig()
TIMEOUT = 180

_ROOT = Path(__file__).resolve().parent.parent / "marrow"
SCHEMA = json.loads((_ROOT / "schemas" / "candidates.v1.schema.json").read_text(encoding="utf-8"))
PASSAGE = (_ROOT / "prompts" / "sample_passage.md").read_text(encoding="utf-8").strip()


class Failed(Exception):
    """reason = runner 的 outcome,或 gate(修補一次後仍不合格)。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@cache
def _prompt():
    return assemble("candidates", SCHEMA)


def positions(seed: int) -> list[tuple[str, ...]]:
    combos = list(itertools.product(*AXES))
    random.Random(seed).shuffle(combos)
    picked: list[tuple[str, ...]] = []
    for combo in combos:
        if all(sum(a != b for a, b in zip(combo, p)) >= MIN_AXES_APART for p in picked):
            picked.append(combo)
    return picked[:COUNT]


def to_card(candidate: dict) -> dict:
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": candidate["name"]["zh-Hant"], "description": "", "tags": [], "creator": "hyenovel",
        "character_version": "", "mes_example": candidate["sample"], "system_prompt": "",
        "post_history_instructions": "", "first_mes": "", "alternate_greetings": [],
        "group_only_greetings": [], "personality": candidate["reading"], "scenario": "",
        "creator_notes": candidate["line"]["zh-Hant"],
        "extensions": {"hyenovel": {"name": candidate["name"], "line": candidate["line"]}},
    }}


def _errors(body: dict) -> list[str]:
    bad = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(SCHEMA).iter_errors(body)]
    if bad:
        return bad
    items = body["candidates"]
    for label, values in (("名字重複", [c["name"][k].strip() for k in ("zh-Hant", "en") for c in items]),
                          ("試讀重複", [c["sample"].strip() for c in items])):
        if len(set(values)) < len(values):
            bad.append(label)
    for i, c in enumerate(items, 1):
        bad += [f"候選 {i}: {code}" for code in cards.scan(to_card(c))["errors"]]
    return bad


def _input(brief: str, picked: list[tuple[str, ...]]) -> str:
    lines = "\n".join(f"候選 {i}:{'、'.join(pos)}" for i, pos in enumerate(picked, 1))
    return f"<brief>\n{brief}\n</brief>\n<positions>\n{lines}\n</positions>\n<passage>\n{PASSAGE}\n</passage>"


def _repair(first: str, previous: str, errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    return (f"{first}\n<previous_output>\n{previous}\n</previous_output>\n"
            f"上一份輸出沒通過驗證,逐條錯誤如下。修正這些問題後重交整份 JSON,其餘內容保持不變:\n{listed}")


async def _attempt(run, prompt: str):
    r = await run(_prompt().text, prompt, SCHEMA, config=RUN, timeout=TIMEOUT)
    pipeline.check_anomaly(None, "candidates", r)
    if r.outcome != "ok":
        log.info("event=candidates-failed reason=%s", r.outcome)
        raise Failed(r.outcome)
    if r.parsed is None:
        return None, (r.text or "")[:MAX_PREVIOUS_CHARS], ["輸出無法解析成單一 JSON 物件"]
    return r.parsed, canonical_json(r.parsed), _errors(r.parsed)


def _shown(candidate: dict, pos: tuple[str, ...]) -> dict:
    card = to_card(candidate)
    return {**candidate, "axes": list(pos), "card": card, "warnings": cards.scan(card)["warnings"]}


async def generate(run, brief: str, seed: int) -> dict:
    picked = positions(seed)
    first = _input(brief, picked)
    body, previous, errors = await _attempt(run, first)
    if errors:
        log.info("event=candidates-repair errors=%d", len(errors))
        body, _, errors = await _attempt(run, _repair(first, previous, errors))
    if errors:
        log.info("event=candidates-failed reason=gate errors=%d", len(errors))
        raise Failed("gate")
    return {"seed": seed, "candidates": [_shown(c, pos) for c, pos in zip(body["candidates"], picked, strict=True)]}
