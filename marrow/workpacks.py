"""工作包登錄表:analyst / reviewer 的 system prompt、輸出 schema、輸入組裝與閘門分派。

prompt 是 marrow 內唯一正本(無工具版:原文直接放在使用者訊息)。輸出格式與 schema 由這裡
附在 system prompt 尾巴(穩定、可被快取);模型把 JSON 當文字吐,我們解析、閘門驗。
"""
import graphlib
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from marrow import gate as _gate
from marrow import schema
from marrow.repo import canonical_json

_PROMPTS = Path(__file__).resolve().parent / "prompts"


Inputs = Mapping[str, dict]


@dataclass(frozen=True)
class RunConfig:
    model: str = "sonnet"
    effort: str = "medium"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkPack:
    name: str
    kind: Literal["analysis", "notes"]
    system_prompt: str
    schema: dict
    needs: tuple[str, ...]
    gate: Callable[[dict, str, Inputs], list[str]]
    run: RunConfig = RunConfig()


# 修補時夾回去的原始輸出上限(解析不出的文字可能是一大段失控輸出)
MAX_PREVIOUS_CHARS = 20_000


@cache
def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _system_prompt(name: str, sch: dict) -> str:
    shown = {k: v for k, v in sch.items() if k != "$schema"}
    return (_prompt(name).rstrip()
            + "\n\n## 輸出格式\n"
            + "只輸出單一 JSON 物件：不要用程式碼框（```）包住，也不要任何前後說明文字。"
            + "這個物件必須符合下列 JSON Schema：\n"
            + canonical_json(shown) + "\n")


def _gate_analyst(body: dict, source: str, inputs: Inputs) -> list[str]:
    return _gate.gate_analysis(body, source)


def _gate_reviewer(body: dict, source: str, inputs: Inputs) -> list[str]:
    return _gate.gate_notes(body, inputs["analysis"], source)


WORKPACKS: dict[str, WorkPack] = {
    name: WorkPack(name, kind, _system_prompt(name, schema.load_schema(kind)),
                   schema.load_schema(kind), needs, check)
    for name, kind, needs, check in (("analyst", "analysis", (), _gate_analyst),
                                     ("reviewer", "notes", ("analysis",), _gate_reviewer))
}


def order(packs: Mapping[str, WorkPack] = WORKPACKS) -> tuple[str, ...]:
    producer = {p.kind: p.name for p in packs.values()}
    missing = {k for p in packs.values() for k in p.needs} - set(producer)
    if missing:
        raise ValueError(f"沒有步驟產出:{','.join(sorted(missing))}")
    graph = {p.name: {producer[k] for k in p.needs} for p in packs.values()}
    return tuple(graphlib.TopologicalSorter(graph).static_order())


def first_input(name: str, slug: str, source: str, inputs: Inputs) -> str:
    out = f"slug: {slug}\n<source>\n{source}\n</source>"
    for kind in WORKPACKS[name].needs:
        if kind not in inputs:
            raise ValueError(f"{name} 需要 {kind}")
        out += f"\n<{kind}>\n{canonical_json(inputs[kind])}\n</{kind}>"
    return out


def repair_input(name: str, slug: str, source: str, inputs: Inputs,
                 previous: dict | str, errors: list[str]) -> str:
    """previous 是上一份解析出的物件;解析不出時是原始文字(截前 MAX_PREVIOUS_CHARS 字)。"""
    if isinstance(previous, str):         # 解析不出來就沒有「其餘內容」可保留
        prev = previous[:MAX_PREVIOUS_CHARS]
        ask = ("上一份輸出無法解析成單一 JSON 物件（可能被截斷了），錯誤如下。"
               "請依輸出格式從頭重交完整的 JSON：\n")
    else:
        prev = canonical_json(previous)
        ask = "上一份輸出沒通過驗證，逐條錯誤如下。請修正這些問題後重交整份 JSON，修正連帶要改的地方之外，其餘內容保持不變：\n"
    return (first_input(name, slug, source, inputs)
            + f"\n<previous_output>\n{prev}\n</previous_output>\n"
            + ask
            + "\n".join(f"- {e}" for e in errors))


def gate(name: str, body: dict, source: str, inputs: Inputs) -> list[str]:
    return WORKPACKS[name].gate(body, source, inputs)
