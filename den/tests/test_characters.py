"""角色登記表。"""
import copy
from pathlib import Path

import pytest

from den import characters, companion, themes
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
