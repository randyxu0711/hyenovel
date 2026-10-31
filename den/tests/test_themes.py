"""佈景主題登記表與對比規則。"""
import copy

import pytest

from den import themes


def test_contrast_known_values():
    assert themes.contrast("#ffffff", "#000000") == pytest.approx(21)
    assert themes.contrast("#000000", "#000000") == pytest.approx(1)


def test_builtins_have_default_and_all_keys():
    ts = themes.builtins()
    assert themes.DEFAULT_THEME in {t["id"] for t in ts} and len(ts) == 2
    for t in ts:
        assert set(t["light"]) == set(t["dark"]) == set(themes.KEYS)


def test_every_builtin_theme_passes_check_theme():
    for t in themes.builtins():
        assert themes.check_theme(t) == []


def test_check_theme_rejects_pure_white_on_black():
    t = copy.deepcopy(themes.builtins()[0])
    t["dark"]["ui-ink"], t["dark"]["desk"] = "#ffffff", "#000000"
    assert any("dark ui-ink/desk" in m for m in themes.check_theme(t))


def test_load_rejects_broken_files(tmp_path, monkeypatch):
    good = (themes._DIR / "olive.json").read_text(encoding="utf-8")
    monkeypatch.setattr(themes, "_DIR", tmp_path)
    for files, why in (({"a.json": good, "b.json": good}, "重複"),
                       ({"a.json": good.replace('"muzzle"', '"nose"', 1)}, "鍵不齊"),
                       ({"a.json": good.replace('"olive"', '"x"', 1)}, "預設")):
        for p in tmp_path.iterdir():
            p.unlink()
        for n, t in files.items():
            (tmp_path / n).write_text(t, encoding="utf-8")
        themes._load.cache_clear()
        with pytest.raises(ValueError, match=why):
            themes.builtins()
    themes._load.cache_clear()
