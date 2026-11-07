"""角色登記表。"""
import copy
import json
from pathlib import Path

import pytest

from den import candidates, cards, characters, companion, themes
from marrow import db, repo


@pytest.fixture
def conn():
    c = db.connect("sqlite:///:memory:")
    db.migrate(c, None)
    characters.sync_builtins(c, 1.0)
    yield c
    c.close()


def test_builtin_lookup(conn):
    assert characters.DEFAULT_CHARACTER == "hyena"
    assert characters.get(conn, "deer")["name"]["en"] == "Deer" and characters.get(conn, "nope") is None


def test_every_builtin_passes_check_colors():
    for c in characters.builtins():
        assert characters.check_colors(c["colors"]) == [], c["id"]


def test_check_colors_rejects_low_contrast_text():
    low = {"light": {"fill": "#000000", "text": "#e0e0e0"}, "dark": {"fill": "#000000", "text": "#e0e0e0"}}
    assert characters.check_colors(low)


def test_check_colors_covers_every_theme(monkeypatch):
    t = copy.deepcopy(themes.builtins()[0])
    t["id"] = "weird"
    t["light"]["desk"] = t["light"]["desk-2"] = "#000000"
    monkeypatch.setattr(themes, "builtins", lambda: [t])
    msgs = characters.check_colors(next(c for c in characters.builtins() if c["id"] == "hyena")["colors"])
    assert any(m.startswith("weird light text/desk") for m in msgs)


def test_resolve_precedence(conn):
    assert characters.resolve(conn, "deer", "buffalo")["id"] == "deer"
    assert characters.resolve(conn, None, "deer")["id"] == "deer"
    assert characters.resolve(conn, None, None)["id"] == "hyena"
    assert characters.resolve(conn, None, "gone")["id"] == "hyena"


def test_resolve_unknown_character(conn):
    with pytest.raises(characters.UnknownCharacter):
        characters.resolve(conn, "dragon", None)


def test_persona_appends_voice_only_when_present(conn):
    hyena = characters.get(conn, "hyena")
    base = characters.persona(hyena)
    assert base == companion.persona(hyena["reading"])
    assert characters.persona({**hyena, "voice": "角色層一句"}).endswith("\n角色層一句\n")


def test_default_pointing_at_missing_character_falls_back(conn):
    repo.set_setting(conn, "default_character", "gone")
    assert characters.default_id(conn) == "hyena"
    assert characters.resolve(conn, None, None)["id"] == "hyena"


def test_set_default_is_used_when_nothing_else_given(conn):
    characters.set_default(conn, "deer")
    assert characters.default_id(conn) == "deer"
    assert characters.resolve(conn, None, None)["id"] == "deer"
    assert characters.resolve(conn, None, "buffalo")["id"] == "buffalo"


def test_set_default_rejects_unknown(conn):
    with pytest.raises(characters.UnknownCharacter):
        characters.set_default(conn, "dragon")
    assert characters.default_id(conn) == "hyena"


def test_sync_is_idempotent(conn):
    characters.sync_builtins(conn, 2.0)
    assert {c["id"]: c["version"] for c in characters.all_(conn)} == {"buffalo": 1, "deer": 1, "hyena": 1}


def test_db_reading_matches_file_bytes(conn):
    for c in characters.all_(conn):
        assert c["reading"] == (characters._DIR / f"{c['id']}.md").read_text(encoding="utf-8")


def test_sync_appends_version_when_file_changes(tmp_path, monkeypatch):
    profile = (characters._DIR / "hyena.json").read_text(encoding="utf-8")
    monkeypatch.setattr(characters, "_DIR", tmp_path)
    characters._load.cache_clear()
    (tmp_path / "hyena.json").write_text(profile, encoding="utf-8")
    (tmp_path / "hyena.md").write_text("舊讀法", encoding="utf-8")
    c = db.connect("sqlite:///:memory:")
    db.migrate(c, None)
    characters.sync_builtins(c, 1.0)
    (tmp_path / "hyena.md").write_text("新讀法", encoding="utf-8")
    characters.sync_builtins(c, 2.0)
    now = characters.get(c, "hyena")
    assert now["version"] == 2 and now["reading"] == "新讀法"
    assert repo.latest_character(c, "hyena")["origin"] == "builtin"
    c.close()
    characters._load.cache_clear()


def test_load_rejects_broken_files(tmp_path, monkeypatch):
    good = (characters._DIR / "hyena.json").read_text(encoding="utf-8")
    monkeypatch.setattr(characters, "_DIR", tmp_path)
    for files, why in (({"a.json": good, "b.json": good}, "重複"),
                       ({"a.json": good.replace('"voice"', '"v"')}, "欄位"),
                       ({"a.json": good.replace('"hyena"', '"x"', 1)}, "預設"),
                       ({"hyena.json": good}, "讀法")):
        for p in tmp_path.iterdir():
            p.unlink()
        for n, t in files.items():
            (tmp_path / n).write_text(t, encoding="utf-8")
        characters._load.cache_clear()
        with pytest.raises(ValueError, match=why):
            characters.builtins()
    characters._load.cache_clear()


def test_builtin_marks():
    assert {c["id"]: c["mark"] for c in characters.builtins()} == {
        "hyena": "pencil", "buffalo": "highlighter", "deer": "circle"}
    assert characters.MARKS == ("pencil", "highlighter", "circle")


@pytest.fixture
def custom_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "_DIR", tmp_path)
    characters._load.cache_clear()
    yield tmp_path
    characters._load.cache_clear()


def _write_hyena(dirpath, mark):
    import json
    d = json.loads((Path(__file__).resolve().parents[2] / "marrow/prompts/characters/hyena.json").read_text(encoding="utf-8"))
    d.pop("mark", None)
    if mark is not None:
        d["mark"] = mark
    (dirpath / "hyena.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (dirpath / "hyena.md").write_text("讀法", encoding="utf-8")


def test_mark_default(custom_dir):
    _write_hyena(custom_dir, None)
    assert characters.builtins()[0]["mark"] == "pencil"


def test_mark_unknown_falls_back(custom_dir):
    _write_hyena(custom_dir, "crayon")
    assert characters.builtins()[0]["mark"] == "pencil"


def _imported(conn, **data):
    card = {"spec": "chara_card_v3", "spec_version": "3.0",
            "data": {"name": "老讀", "personality": "讀", "description": "再讀", "first_mes": "嗨",
                     "extensions": {"other": 1}, **data}}
    return characters.import_card(conn, card, 1.0)["id"]


NEW = ({"zh-Hant": "新名", "en": "New"}, {"zh-Hant": "新介紹", "en": "New line"}, "新讀法")


def test_edited_card_replaces_text_and_keeps_the_rest(conn):
    cid = _imported(conn)
    data = cards.edited(repo.latest_character(conn, cid)["card"], *NEW)["data"]
    assert data["name"] == "新名" and data["personality"] == "新讀法" and data["description"] == ""
    assert data["creator_notes"] == "新介紹" and data["first_mes"] == "嗨"
    assert data["extensions"]["other"] == 1
    assert data["extensions"]["hyenovel"]["name"] == NEW[0] and data["extensions"]["hyenovel"]["line"] == NEW[1]


def test_edit_adds_a_version_and_old_one_stays(conn):
    cid = _imported(conn)
    first = repo.latest_character(conn, cid)["card"]
    assert characters.edit(conn, cid, *NEW, 2.0)["version"] == 2
    row = conn.execute("SELECT card FROM character_version WHERE character_id = ? AND n = 1", (cid,)).fetchone()
    assert json.loads(row[0]) == first
    assert characters.get(conn, cid)["reading"] == "新讀法"


def test_edit_unchanged_adds_no_version_even_when_card_has_description(conn):
    cid = _imported(conn)
    now = characters.get(conn, cid)
    same = characters.edit(conn, cid, now["name"], now["line"], now["reading"], 2.0)
    assert same["version"] == 1


def test_edit_refuses_builtin_and_unknown(conn):
    with pytest.raises(characters.BuiltinCharacter):
        characters.edit(conn, "hyena", *NEW, 2.0)
    with pytest.raises(characters.UnknownCharacter):
        characters.edit(conn, "nobody", *NEW, 2.0)


def test_create_is_origin_created_with_a_fresh_id(conn):
    card = candidates.to_card({"name": NEW[0], "form": NEW[0], "line": NEW[1], "reading": "讀", "sample": "試"})
    a, b = characters.create(conn, card, 2.0), characters.create(conn, card, 2.0)
    assert a["id"] != b["id"] and a["origin"] == "created" and a["id"][0] == "c" and len(a["id"]) == 17


def test_copy_keeps_look_and_adds_suffix(conn):
    source = characters.get(conn, "buffalo")
    got = characters.copy(conn, "buffalo", 2.0)
    assert got["origin"] == "created" and got["id"] != "buffalo" and got["version"] == 1
    assert got["name"]["zh-Hant"] == source["name"]["zh-Hant"] + "(副本)"
    assert got["name"]["en"] == source["name"]["en"] + " (copy)"
    for k in ("colors", "avatar", "voice", "mark", "reading", "line"):
        assert got[k] == source[k]
    assert characters.get(conn, "buffalo") == source


def test_copy_keeps_the_blob_of_a_card_without_avatar(conn):
    cid = _imported(conn)
    assert characters.copy(conn, cid, 2.0)["avatar"] == characters.get(conn, cid)["avatar"]


def test_copy_stays_within_the_name_limit(conn):
    cid = _imported(conn, name="長" * cards.MAX_NAME)
    got = characters.copy(conn, cid, 2.0)
    assert len(got["name"]["zh-Hant"]) == cards.MAX_NAME and got["name"]["zh-Hant"].endswith("(副本)")
    assert len(got["name"]["en"]) == cards.MAX_NAME and got["name"]["en"].endswith(" (copy)")


def test_copy_refuses_archived_and_unknown(conn):
    cid = _imported(conn)
    characters.archive(conn, cid, 2.0)
    for gone in (cid, "nobody"):
        with pytest.raises(characters.UnknownCharacter):
            characters.copy(conn, gone, 3.0)
