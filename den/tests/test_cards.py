"""CCv3 角色卡與角色 dict 的轉換。"""
import json

from den import cards, characters


def _builtin_files():
    out = []
    for p in sorted(characters._DIR.glob("*.json")):
        out.append((json.loads(p.read_text(encoding="utf-8")), p.with_suffix(".md").read_text(encoding="utf-8")))
    return out


def test_builtin_roundtrip_is_byte_identical():
    for profile, reading in _builtin_files():
        c = cards.view(cards.from_builtin(profile, reading), profile["id"], 1)
        assert c["reading"] == reading and c["id"] == profile["id"] and c["version"] == 1
        assert {k: c[k] for k in ("name", "line", "avatar", "colors", "voice", "mark")} == \
               {k: profile[k] for k in ("name", "line", "avatar", "colors", "voice", "mark")}


def test_builtin_card_has_required_v3_fields():
    card = cards.from_builtin(*_builtin_files()[0])
    assert card["spec"] == "chara_card_v3" and card["spec_version"] == "3.0"
    assert card["data"]["group_only_greetings"] == []
    assert {"name", "description", "tags", "creator", "character_version", "mes_example", "extensions",
            "system_prompt", "post_history_instructions", "first_mes", "alternate_greetings",
            "personality", "scenario", "creator_notes"} <= set(card["data"])
