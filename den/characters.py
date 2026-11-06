"""角色登記表:內建角色是 marrow/prompts/characters/<id>.json(長相)+ <id>.md(讀法)。"""
import json
from functools import cache
from pathlib import Path

from den import companion, themes

_DIR = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "characters"

DEFAULT_CHARACTER = "hyena"
_FIELDS = {"id", "name", "line", "avatar", "colors", "voice"}
MARKS = ("pencil", "highlighter", "circle")


class UnknownCharacter(Exception):
    """指定的角色 id 不存在。"""


@cache
def _load() -> tuple[dict, ...]:
    out = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_DIR.glob("*.json"))]
    ids = [c.get("id") for c in out]
    if len(set(ids)) != len(ids):
        raise ValueError(f"character id 重複: {ids}")
    for c in out:
        if not (_FIELDS <= set(c) <= _FIELDS | {"mark"}):
            raise ValueError(f"character {c.get('id')} 欄位不齊")
        if c.get("mark") not in MARKS:
            c["mark"] = "pencil"
    if DEFAULT_CHARACTER not in ids:
        raise ValueError("缺預設角色")
    for i in ids:
        if not (_DIR / f"{i}.md").is_file():
            raise ValueError(f"character {i} 缺讀法檔")
    return tuple(out)


def builtins() -> list[dict]:
    return list(_load())


def get(character_id: str) -> dict | None:
    return next((c for c in _load() if c["id"] == character_id), None)


def resolve(character: str | None, last: str | None) -> dict:
    """指定角色 > 該局上一位 > 預設。"""
    if character is not None:
        found = get(character)
        if found is None:
            raise UnknownCharacter(character)
        return found
    return (last and get(last)) or get(DEFAULT_CHARACTER)


def check_colors(colors: dict) -> list[str]:
    """名字色(text)在每一套內建主題的晝夜、對話欄與桌面上都要 ≥ 4.5:1。fill 是毛色(頭像有墨色輪廓),不驗。"""
    bad = []
    for theme in themes.builtins():
        for scheme in ("light", "dark"):
            for bg in ("desk-2", "desk"):
                r = themes.contrast(colors[scheme]["text"], theme[scheme][bg])
                if r < 4.5:
                    bad.append(f"{theme['id']} {scheme} text/{bg} = {r:.2f}")
    return bad


def persona(character: dict) -> str:
    return companion.persona(character["id"], character["voice"])
