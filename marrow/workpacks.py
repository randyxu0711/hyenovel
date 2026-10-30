"""工作包登錄表:analyst / criticizer 的 system prompt、輸出 schema、輸入組裝與閘門分派。

prompt 是 marrow 內唯一正本(無工具版:原文直接放在使用者訊息)。輸出格式與 schema 由這裡
附在 system prompt 尾巴(穩定、可被快取);模型把 JSON 當文字吐,我們解析、閘門驗。
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
    kind: Literal["analysis", "feedback", "notes"]
    system_prompt: str
    schema: dict


# 修補時夾回去的原始輸出上限(解析不出的文字可能是一大段失控輸出)
MAX_PREVIOUS_CHARS = 20_000


@cache
def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _system_prompt(name: str, sch: dict) -> str:
    shown = {k: v for k, v in sch.items() if k != "$schema"}
    return (_prompt(name).rstrip()
            + "\n\n## 輸出格式\n"
            + "只輸出**單一 JSON 物件**：不要用程式碼框（```）包住，也不要任何前後說明文字。"
            + "這個物件必須符合下列 JSON Schema：\n"
            + canonical_json(shown) + "\n")


WORKPACKS: dict[str, WorkPack] = {
    name: WorkPack(name, kind, _system_prompt(name, schema.load_schema(kind)),
                   schema.load_schema(kind))
    for name, kind in (("analyst", "analysis"), ("criticizer", "feedback"), ("reviewer", "notes"))
}


_NEEDS_ANALYSIS = ("criticizer", "reviewer")


def first_input(name: str, slug: str, source: str, analysis: dict | None) -> str:
    out = f"slug: {slug}\n<source>\n{source}\n</source>"
    if name in _NEEDS_ANALYSIS:
        if analysis is None:
            raise ValueError(f"{name} 需要 analysis")
        out += f"\n<analysis>\n{canonical_json(analysis)}\n</analysis>"
    return out


def repair_input(name: str, slug: str, source: str, analysis: dict | None,
                 previous: dict | str, errors: list[str]) -> str:
    """previous 是上一份解析出的物件;解析不出時是原始文字(截前 MAX_PREVIOUS_CHARS 字)。"""
    if isinstance(previous, str):         # 解析不出來就沒有「其餘內容」可保留
        prev = previous[:MAX_PREVIOUS_CHARS]
        ask = ("上一份輸出無法解析成單一 JSON 物件（可能被截斷了），錯誤如下。"
               "請依輸出格式從頭重交完整的 JSON：\n")
    else:
        prev = canonical_json(previous)
        ask = "上一份輸出沒通過驗證，逐條錯誤如下。請修正這些問題後重交整份 JSON，其餘內容保持不變：\n"
    return (first_input(name, slug, source, analysis)
            + f"\n<previous_output>\n{prev}\n</previous_output>\n"
            + ask
            + "\n".join(f"- {e}" for e in errors))


def gate(name: str, body: dict, source: str, analysis: dict | None) -> list[str]:
    if name == "analyst":
        return _gate.gate_analysis(body, source)
    fn = _gate.gate_notes if name == "reviewer" else _gate.gate_feedback
    return fn(body, analysis, source)
