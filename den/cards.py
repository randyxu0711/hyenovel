"""CCv3 角色卡與程式用的角色 dict 之間的轉換,以及匯入時的驗證與掃描。"""
import json
import re
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from den import themes
from marrow.repo import canonical_json, sha256_text

MAX_CARD_BYTES = 262144
MAX_READING = 6000
MAX_NAME = 64
MAX_LINE = 200
_FOREIGN_LINE = 40
MARKS = ("pencil", "highlighter", "circle")
FALLBACK_COLORS = {"light": {"fill": "#8a8378", "text": "#5f5a52"}, "dark": {"fill": "#b5ae9f", "text": "#c9c3b7"}}

_SCHEMA = Path(__file__).resolve().parent.parent / "marrow" / "schemas" / "card.v3.schema.json"
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_MACRO = re.compile(r"\{\{(char|user)\}\}", re.IGNORECASE)
_INSTRUCTIONS = re.compile(r"ignore (all |any )?(previous|prior)|system prompt|忽略.{0,8}(指示|指令|規則)"
                           r"|無視.{0,8}(指示|指令|規則)|不要遵守|you are now", re.IGNORECASE)
_IGNORED = ("system_prompt", "post_history_instructions", "character_book", "first_mes")


@cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA.read_text(encoding="utf-8")))


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


def _colors_ok(colors) -> bool:
    if not isinstance(colors, dict):
        return False
    for scheme in ("light", "dark"):
        pair = colors.get(scheme)
        if not isinstance(pair, dict):
            return False
        if not all(isinstance(pair.get(k), str) and _HEX.fullmatch(pair[k]) for k in ("fill", "text")):
            return False
    return not check_colors(colors)


def _ltext_ok(value, limit: int) -> bool:
    return (isinstance(value, dict)
            and all(isinstance(value.get(k), str) and len(value[k]) <= limit for k in ("zh-Hant", "en")))


def _ext(data: dict) -> dict:
    ext = data.get("extensions", {}).get("hyenovel")
    return ext if isinstance(ext, dict) else {}


def _voice(ext: dict) -> str:
    return ext["voice"] if isinstance(ext.get("voice"), str) else ""


def from_builtin(profile: dict, reading: str) -> dict:
    """內建角色(.json 的內容 + 讀法原文)→ CCv3 卡。"""
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": profile["name"]["zh-Hant"], "description": "", "tags": [], "creator": "hyenovel",
        "character_version": "", "mes_example": "", "system_prompt": "", "post_history_instructions": "",
        "first_mes": "", "alternate_greetings": [], "group_only_greetings": [], "personality": reading,
        "scenario": "", "creator_notes": profile["line"]["zh-Hant"],
        "extensions": {"hyenovel": {k: profile[k] for k in ("name", "line", "avatar", "colors", "voice", "mark")}},
    }}


def _reading(data: dict) -> str:
    who = {"char": data.get("nickname") or data["name"], "user": "作者"}
    text = "\n\n".join(x for x in (data.get("personality"), data.get("description")) if x and x.strip())
    return _MACRO.sub(lambda m: who[m[1].lower()], text)


def view(card: dict, character_id: str, version: int) -> dict:
    data = card["data"]
    ext = _ext(data)
    name, notes = data["name"], data.get("creator_notes", "")[:_FOREIGN_LINE]
    return {
        "id": character_id, "version": version,
        "name": ext["name"] if _ltext_ok(ext.get("name"), MAX_NAME) else {"zh-Hant": name, "en": name},
        "line": ext["line"] if _ltext_ok(ext.get("line"), MAX_LINE) else {"zh-Hant": notes, "en": notes},
        "avatar": ext["avatar"] if isinstance(ext.get("avatar"), dict) else {"kind": "blob", "seed": character_id},
        "colors": ext["colors"] if _colors_ok(ext.get("colors")) else FALLBACK_COLORS,
        "voice": _voice(ext),
        "mark": ext.get("mark") if ext.get("mark") in MARKS else "pencil",
        "reading": _reading(data),
    }


def _newer_spec(spec_version: str) -> bool:
    try:
        return float(spec_version) > 3.0
    except ValueError:
        return False


def scan(card) -> dict:
    """匯入前檢查:errors 擋匯入,warnings 要作者確認。字串是給 i18n 的代碼。"""
    if next(_validator().iter_errors(card), None) is not None:
        return {"errors": ["bad-schema"], "warnings": []}
    try:
        size = len(canonical_json(card).encode("utf-8"))
    except UnicodeEncodeError:
        return {"errors": ["bad-schema"], "warnings": []}
    data = card["data"]
    ext = _ext(data)
    personality, description, voice = data.get("personality", ""), data.get("description", ""), _voice(ext)
    errors = []
    if size > MAX_CARD_BYTES:
        errors.append("too-large")
    ext_name = ext.get("name")
    if len(data["name"]) > MAX_NAME or (isinstance(ext_name, dict) and not _ltext_ok(ext_name, MAX_NAME)):
        errors.append("name-too-long")
    if not (personality.strip() or description.strip()):
        errors.append("no-reading")
    if len(personality) + len(description) + len(voice) > MAX_READING:
        errors.append("reading-too-long")
    warnings = []
    if _newer_spec(card["spec_version"]):
        warnings.append("newer-spec")
    if any(_INSTRUCTIONS.search(x) for x in (personality, description, voice)):
        warnings.append("looks-like-instructions")
    if any(data.get(k) for k in _IGNORED):
        warnings.append("ignored-fields")
    if "colors" in ext and not _colors_ok(ext["colors"]):
        warnings.append("bad-colors")
    return {"errors": errors, "warnings": warnings}


def imported_id(card: dict) -> str:
    return "u" + sha256_text(canonical_json(card))[:8]
