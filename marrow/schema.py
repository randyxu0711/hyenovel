"""strict schema v1 與 v0→v1 轉換(spec §8 R5)。

strict 是給 runner 的硬需求:Codex `--output-schema` / OpenAI strict 要每個 object
`additionalProperties: false` 且所有 property 都 required,可選改成「可為 null」。
v0(`schemas/`)仍是舊 analyst 閘門在用的契約,不動;v1 只活在 marrow 裡。
"""
import json
from functools import cache
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator

SCHEMA_VERSION = 1
_DIR = Path(__file__).resolve().parent / "schemas"

Kind = Literal["analysis", "feedback"]


@cache
def _schema(kind: str) -> dict:
    return json.loads((_DIR / f"{kind}.v1.schema.json").read_text(encoding="utf-8"))


def load_schema(kind: Kind) -> dict:
    return json.loads(json.dumps(_schema(kind)))    # 給呼叫者一份可改的拷貝,快取那份不外流


def strict_violations(schema: dict) -> list[str]:
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            if "properties" in node:
                if node.get("additionalProperties") is not False:
                    out.append(f"{path or '/'}: additionalProperties 不是 false")
                missing = sorted(set(node["properties"]) - set(node.get("required", [])))
                if missing:
                    out.append(f"{path or '/'}: 非 required:{','.join(missing)}")
            for k, v in node.items():
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(schema, "")
    return out


def to_v1(kind: Kind, body: dict) -> dict:
    """依 v1 schema 遞迴補齊缺欄(補 None)。不改原物件、不刪多餘欄位(讓 validate 去擋)。"""
    root = _schema(kind)

    def resolve(s):
        ref = s.get("$ref")
        return root["$defs"][ref.rsplit("/", 1)[1]] if ref else s

    def conv(value, s):
        s = resolve(s)
        if isinstance(value, dict) and "properties" in s:
            out = {k: conv(v, s["properties"][k]) if k in s["properties"] else v
                   for k, v in value.items()}
            for k in s["properties"]:
                out.setdefault(k, None)
            return out
        if isinstance(value, list) and "items" in s:
            return [conv(v, s["items"]) for v in value]
        return value

    return conv(body, root)


def validate_v1(kind: Kind, body: dict) -> list[str]:
    return [e.message for e in Draft202012Validator(_schema(kind)).iter_errors(body)]
