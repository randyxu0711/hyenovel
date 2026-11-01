"""角色登記表:角色 ≠ 模式。"""
import copy

import pytest

from den import characters, companion, themes


def test_builtins_three_with_distinct_modes():
    cs = characters.builtins()
    assert {c["id"]: c["mode"] for c in cs} == {"buffalo": "direct", "deer": "imaginative", "hyena": "slow"}
    assert {c["mode"] for c in cs} == set(companion.MODES)
    assert characters.DEFAULT_CHARACTER == "hyena"
    assert characters.get("deer")["name"]["en"] == "Deer" and characters.get("nope") is None


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
    msgs = characters.check_colors(characters.get("hyena")["colors"])
    assert any(m.startswith("weird light text/desk") for m in msgs)


def test_resolve_precedence():
    assert characters.resolve("deer", "direct", "buffalo")["id"] == "deer"
    assert characters.resolve(None, "direct", "deer")["id"] == "buffalo"
    assert characters.resolve(None, None, "deer")["id"] == "deer"
    assert characters.resolve(None, None, None)["id"] == "hyena"
    assert characters.resolve(None, None, "gone")["id"] == "hyena"


def test_resolve_unknown_character():
    with pytest.raises(characters.UnknownCharacter):
        characters.resolve("dragon", None, None)


def test_persona_appends_voice_only_when_present():
    base = characters.persona(characters.get("hyena"))
    assert base == companion.persona("slow")
    assert characters.persona({**characters.get("hyena"), "voice": "角色層一句"}).endswith("\n角色層一句\n")


def test_load_rejects_broken_files(tmp_path, monkeypatch):
    good = (characters._DIR / "hyena.json").read_text(encoding="utf-8")
    monkeypatch.setattr(characters, "_DIR", tmp_path)
    for files, why in (({"a.json": good, "b.json": good}, "重複"),
                       ({"a.json": good.replace('"voice"', '"v"')}, "欄位"),
                       ({"a.json": good.replace('"slow"', '"fast"')}, "mode"),
                       ({"a.json": good.replace('"hyena"', '"x"', 1)}, "預設")):
        for p in tmp_path.iterdir():
            p.unlink()
        for n, t in files.items():
            (tmp_path / n).write_text(t, encoding="utf-8")
        characters._load.cache_clear()
        with pytest.raises(ValueError, match=why):
            characters.builtins()
    characters._load.cache_clear()
