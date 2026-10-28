"""工作包登錄表:analyst / criticizer 的 system prompt、輸出 schema、輸入組裝與閘門分派。

prompt 是 marrow 內唯一正本(無工具版:原文直接放在使用者訊息,schema 由 CLI 結構化輸出帶)。
"""
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from marrow import gate as _gate
from marrow import schema
from marrow.repo import canonical_json

_PROMPTS = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class WorkPack:
    name: str
    kind: Literal["analysis", "feedback"]
    system_prompt: str
    schema: dict


@cache
def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


WORKPACKS: dict[str, WorkPack] = {
    name: WorkPack(name, kind, _prompt(name), schema.load_schema(kind))
    for name, kind in (("analyst", "analysis"), ("criticizer", "feedback"))
}


def first_input(name: str, slug: str, source: str, analysis: dict | None) -> str:
    out = f"slug: {slug}\n<source>\n{source}\n</source>"
    if name == "criticizer":
        if analysis is None:
            raise ValueError("criticizer 需要 analysis")
        out += f"\n<analysis>\n{canonical_json(analysis)}\n</analysis>"
    return out


def repair_input(name: str, slug: str, source: str, analysis: dict | None,
                 previous: dict, errors: list[str]) -> str:
    return (first_input(name, slug, source, analysis)
            + f"\n<previous_output>\n{canonical_json(previous)}\n</previous_output>\n"
            + "上一份輸出沒通過驗證，逐條錯誤如下。請修正這些問題後重交整份 JSON，其餘內容保持不變：\n"
            + "\n".join(f"- {e}" for e in errors))


def gate(name: str, body: dict, source: str, analysis: dict | None) -> list[str]:
    if name == "analyst":
        return _gate.gate_analysis(body, source)
    return _gate.gate_feedback(body, analysis, source)
