"""角色登記表:DB 的 character_version.card 是正本;內建角色的 <id>.json(長相)+ <id>.md(讀法)+ <id>.examples.md(範例對話,可無)啟動時同步成新版本。"""
import json
import secrets
from functools import cache
from pathlib import Path

from den import cards, companion
from den.cards import MARKS, check_colors  # noqa: F401
from marrow import repo

_DIR = Path(__file__).resolve().parent.parent / "marrow" / "prompts" / "characters"

DEFAULT_CHARACTER = "hyena"
_DEFAULT_KEY = "default_character"
_FIELDS = {"id", "name", "line", "avatar", "colors", "voice", "figure"}


class UnknownCharacter(Exception):
    """指定的角色 id 不存在。"""


class BuiltinCharacter(Exception):
    """內建角色不能封存、不能編輯。"""


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
        examples = _DIR / f"{cid}.examples.md"
        card = cards.from_builtin(profile, (_DIR / f"{cid}.md").read_text(encoding="utf-8"),
                                  examples.read_text(encoding="utf-8") if examples.is_file() else "")
        latest = repo.latest_character(conn, cid)
        if latest is None:
            repo.add_character(conn, cid, "builtin", now)
        if latest is None or latest["card"] != card:
            repo.add_character_version(conn, cid, card, now)


def _view(row: dict) -> dict:
    return {**cards.view(row["card"], row["id"], row["n"]), "origin": row["origin"],
            "archived": row["archived_at"] is not None}


def all_(conn) -> list[dict]:
    return [_view(r) for r in repo.latest_characters(conn)]


def get(conn, character_id: str) -> dict | None:
    row = repo.latest_character(conn, character_id)
    return row and _view(row)


def _active(conn, character_id: str) -> dict | None:
    found = get(conn, character_id)
    return found if found and not found["archived"] else None


def default_id(conn) -> str:
    saved = repo.get_setting(conn, _DEFAULT_KEY)
    return saved if saved and _active(conn, saved) else DEFAULT_CHARACTER


def set_default(conn, character_id: str) -> None:
    if _active(conn, character_id) is None:
        raise UnknownCharacter(character_id)
    repo.set_setting(conn, _DEFAULT_KEY, character_id)


def resolve(conn, character: str | None, last: str | None) -> dict:
    """指定角色 > 該局上一位 > 預設。"""
    if character is not None:
        found = _active(conn, character)
        if found is None:
            raise UnknownCharacter(character)
        return found
    return (last and _active(conn, last)) or get(conn, default_id(conn))


def import_card(conn, card: dict, now: float) -> dict:
    """同一張卡再匯入 = 同一隻角色,封存過就拉回來,編輯過就換回這張。呼叫者持 transaction。"""
    cid = cards.imported_id(card)
    row = repo.latest_character(conn, cid)
    if row is None:
        repo.add_character(conn, cid, "imported", now)
        repo.add_character_version(conn, cid, card, now)
    else:
        repo.unarchive_character(conn, cid)
        if row["card"] != card:
            repo.add_character_version(conn, cid, card, now)
    return get(conn, cid)


def create(conn, card: dict, now: float) -> dict:
    cid = "c" + secrets.token_hex(8)
    repo.add_character(conn, cid, "created", now)
    repo.add_character_version(conn, cid, card, now)
    return get(conn, cid)


def copy(conn, character_id: str, now: float) -> dict:
    row = repo.latest_character(conn, character_id)
    if row is None or row["archived_at"] is not None:
        raise UnknownCharacter(character_id)
    return create(conn, cards.copied(row["card"], character_id), now)


def edited_card(conn, character_id: str, name: dict, line: dict, reading: str) -> dict:
    row = repo.latest_character(conn, character_id)
    if row is None or row["archived_at"] is not None:
        raise UnknownCharacter(character_id)
    if row["origin"] == "builtin":
        raise BuiltinCharacter(character_id)
    return cards.edited(row["card"], name, line, reading)


def edit(conn, character_id: str, name: dict, line: dict, reading: str, now: float) -> dict:
    """呼叫者持 transaction。名字、介紹、讀法都沒變就不加版。"""
    card = edited_card(conn, character_id, name, line, reading)
    shown = get(conn, character_id)
    if (shown["name"], shown["line"], shown["reading"]) != (name, line, reading):
        repo.add_character_version(conn, character_id, card, now)
    return get(conn, character_id)


def archive(conn, character_id: str, now: float) -> None:
    row = repo.latest_character(conn, character_id)
    if row is None:
        raise UnknownCharacter(character_id)
    if row["origin"] == "builtin":
        raise BuiltinCharacter(character_id)
    repo.archive_character(conn, character_id, now)


def persona(character: dict) -> str:
    return companion.persona(character["reading"], character["voice"], character.get("examples", ""))
