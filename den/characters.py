"""角色登記表:DB 的 character_version.card 是正本;內建角色的 <id>.json(長相)+ <id>.md(讀法)啟動時同步成新版本。"""
import json
from functools import cache
from pathlib import Path

from den import cards, companion, themes
from marrow import repo

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


def sync_builtins(conn, now: float) -> None:
    """內建檔和最新版不同才加版;呼叫者持 transaction。"""
    for profile in _load():
        cid = profile["id"]
        card = cards.from_builtin(profile, (_DIR / f"{cid}.md").read_text(encoding="utf-8"))
        latest = repo.latest_character(conn, cid)
        if latest is None:
            repo.add_character(conn, cid, "builtin", now)
        if latest is None or latest["card"] != card:
            repo.add_character_version(conn, cid, card, now)


def _view(row: dict) -> dict:
    return cards.view(row["card"], row["id"], row["n"])


def all_(conn) -> list[dict]:
    return [_view(r) for r in repo.latest_characters(conn)]


def get(conn, character_id: str) -> dict | None:
    row = repo.latest_character(conn, character_id)
    return row and _view(row)


def resolve(conn, character: str | None, last: str | None) -> dict:
    """指定角色 > 該局上一位 > 預設。"""
    if character is not None:
        found = get(conn, character)
        if found is None:
            raise UnknownCharacter(character)
        return found
    return (last and get(conn, last)) or get(conn, DEFAULT_CHARACTER)


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
    return companion.persona(character["reading"], character["voice"])
