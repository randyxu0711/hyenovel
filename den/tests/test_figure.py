"""角色長相的機械閘門、色鉛筆盒的名字色、內建角色的長相。"""
import json
from pathlib import Path

import pytest

from den import cards, characters, figure

ROOT = Path(__file__).resolve().parents[2]
OK = {"pose": "mound", "parts": [], "main": "olive", "second": "bark"}


def _with(**kw):
    return {**OK, **kw}


def _part(d="M10 10 L20 20 Z", **kw):
    return {"group": "ears", "d": d, "fill": "main", **kw}


def test_pose_only_figure_is_fine():
    assert figure.errors(OK) == []


def test_web_copy_of_the_grammar_is_identical():
    assert (ROOT / "web/src/dash/figure/grammar.json").read_text(encoding="utf-8") == \
        (ROOT / "marrow/figure.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("bad, code", [
    ("x", "bad-figure"),
    (_with(extra=1), "bad-figure"),
    (_with(main="gold"), "bad-pen"),
    (_with(second=None), "bad-pen"),
    (_with(pose="dragon"), "bad-pose"),
    (_with(pose=["mound"]), "bad-pose"),
    (_with(main=["olive"]), "bad-pen"),
    (_with(tempo={"x": 1}), "bad-tempo"),
    (_with(tempo="fast"), "bad-tempo"),
    (_with(move="spin"), "bad-move"),
    (_with(parts="M0 0"), "bad-parts"),
    (_with(parts=[_part()] * 25), "bad-parts"),
    (_with(eyes=[[1, 2]]), "bad-eyes"),
    (_with(mouth=[[1, 2], [3, 4], [5, 999]]), "bad-mouth"),
    ({"parts": [_part()], "main": "olive", "second": "bark"}, "no-eyes"),
    ({"parts": [], "eyes": [[1, 1], [2, 2]], "mouth": [[1, 1], [2, 2], [3, 3]], "main": "olive", "second": "bark"}, "no-parts"),
])
def test_bad_figures_are_named(bad, code):
    assert code in figure.errors(bad)


@pytest.mark.parametrize("part", [
    _part(group="wing"), _part(fill="gold"), _part(group=["ears"]), _part(fill=["main"]), _part(line="yes"), {"group": "ears", "d": "M0 0"},
    {**_part(), "style": "x"},
])
def test_bad_parts_are_rejected(part):
    assert figure.errors(_with(parts=[part])) == ["parts/0: bad-part"]


@pytest.mark.parametrize("d, code", [
    ("L10 10", "bad-path"),
    ("M10 10 l5 5", "bad-path"),
    ("M10 10 L5", "bad-path"),
    ("M10 10 L5 Z", "bad-path"),
    ("M10 10 H20", "bad-path"),
    ("M--5 5 L20 20", "bad-path"),
    ("M10 10 L-.-5 3", "bad-path"),
    ("M10 10 L20 20 ..", "bad-path"),
    ("M10 10 L20 20\"/><script>", "bad-path"),
    ("", "bad-path"),
    ("M" + "1" * 700, "bad-path"),
    ("M10 10 L200 10", "out-of-bounds"),
    ("M10 10 L10 -11", "out-of-bounds"),
    ("M10 10 A5 5 0 2 0 20 10", "out-of-bounds"),
    ("M10 10 A500 5 0 1 0 20 10", "out-of-bounds"),
    ("M0 0" + " L1 1" * 24, "too-many-commands"),
])
def test_paths_take_only_absolute_commands_inside_the_view(d, code):
    assert figure.errors(_with(parts=[_part(d)])) == [f"parts/0: {code}"]


def test_curves_arcs_decimals_and_compact_numbers_pass():
    d = "M10 10 C12.5 3 20 3 22 10 Q30 18 22 20 A4 4 0 1 0 14 20 L-10 130 Z"
    assert figure.path_errors(d) == []
    assert figure.path_errors("M10,10L20-5L30 .5Z") == []


def test_hostile_imported_figure_is_a_warning_not_a_crash():
    card = cards.from_builtin(json.loads((ROOT / "marrow/prompts/characters/deer.json").read_text(encoding="utf-8")), "讀")
    broken = cards._with_ext(card, {"figure": {"pose": ["x"], "main": ["olive"], "second": {}, "parts": [{"group": [], "d": 1, "fill": None}]}})
    assert cards.view(broken, "x", 1)["figure"] is None
    assert "bad-figure" in cards.scan(broken)["warnings"]


def test_every_pen_has_a_name_color_that_reads_on_every_theme():
    for pen in figure.GRAMMAR["pens"]:
        assert cards.check_colors(figure.pen_colors(pen)) == [], pen


@pytest.mark.parametrize("pose", list(figure.GRAMMAR["poses"]))
def test_every_library_pose_passes_the_gate_on_its_own(pose):
    lib = figure.GRAMMAR["poses"][pose]
    assert figure.errors({**lib, "main": "olive", "second": "bark"}) == []


def test_builtins_carry_a_drawable_figure_with_their_own_parts_tempo_and_move():
    for c in characters.builtins():
        assert figure.errors(c["figure"]) == [], c["id"]
        assert "pose" not in c["figure"]
        assert {"tempo", "move"} <= set(c["figure"])


def test_builtin_figure_reaches_the_view():
    profile = json.loads((ROOT / "marrow/prompts/characters/deer.json").read_text(encoding="utf-8"))
    shown = cards.view(cards.from_builtin(profile, "讀"), "deer", 1)
    assert shown["figure"] == profile["figure"]


def test_card_without_figure_shows_none_and_bad_figure_is_a_warning():
    card = cards.from_builtin({**json.loads((ROOT / "marrow/prompts/characters/deer.json").read_text(encoding="utf-8"))}, "讀")
    plain = {**card, "data": {**card["data"], "extensions": {}}}
    assert cards.view(plain, "x", 1)["figure"] is None
    assert "bad-figure" not in cards.scan(plain)["warnings"]
    broken = cards._with_ext(card, {"figure": _with(main="gold")})
    assert cards.view(broken, "x", 1)["figure"] is None
    assert "bad-figure" in cards.scan(broken)["warnings"]
