"""CCv3 角色卡與程式用的角色 dict 之間的轉換。"""


def from_builtin(profile: dict, reading: str) -> dict:
    """內建角色(.json 的內容 + 讀法原文)→ CCv3 卡。"""
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": profile["name"]["zh-Hant"], "description": "", "tags": [], "creator": "hyenovel",
        "character_version": "", "mes_example": "", "system_prompt": "", "post_history_instructions": "",
        "first_mes": "", "alternate_greetings": [], "group_only_greetings": [], "personality": reading,
        "scenario": "", "creator_notes": profile["line"]["zh-Hant"],
        "extensions": {"hyenovel": {k: profile[k] for k in ("name", "line", "avatar", "colors", "voice", "mark")}},
    }}


def view(card: dict, character_id: str, version: int) -> dict:
    data = card["data"]
    ext = data["extensions"]["hyenovel"]
    reading = "\n\n".join(x for x in (data.get("personality"), data.get("description")) if x and x.strip())
    return {"id": character_id, "version": version, "name": ext["name"], "line": ext["line"],
            "avatar": ext["avatar"], "colors": ext["colors"], "voice": ext["voice"], "mark": ext["mark"],
            "reading": reading}
