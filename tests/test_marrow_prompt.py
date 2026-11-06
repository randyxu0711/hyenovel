"""marrow.prompt:分層串接與指紋。"""
from marrow.prompt import Layer, Prompt, recipe
from marrow.repo import sha256_text


def test_text_concatenates_layers_in_order():
    assert Prompt((Layer("a", "x"), Layer("b", "y"))).text == "xy"


def test_material_does_not_move_instruction_fingerprint():
    a = Prompt((Layer("base", "規則"), Layer("work", "甲篇", material=True)))
    b = Prompt((Layer("base", "規則"), Layer("work", "乙篇", material=True)))
    assert a.fingerprint()["instructions"] == b.fingerprint()["instructions"]
    assert a.fingerprint()["material"] != b.fingerprint()["material"]


def test_instruction_change_moves_fingerprint():
    a = Prompt((Layer("base", "規則"),))
    b = Prompt((Layer("base", "新規則"),))
    assert a.fingerprint()["instructions"] != b.fingerprint()["instructions"]


def test_fingerprint_shape():
    p = Prompt((Layer("base", "規則"), Layer("work", "甲篇", material=True), Layer("status", "跑")))
    assert p.fingerprint() == {
        "instructions": sha256_text("規則跑")[:12],
        "layers": {"base": sha256_text("規則")[:12], "status": sha256_text("跑")[:12]},
        "material": {"work": sha256_text("甲篇")[:12]},
    }


def test_recipe_bundles_prompt_and_run():
    p = Prompt((Layer("base", "規則"),))
    run = {"model": "sonnet", "effort": "medium"}
    assert recipe(p, run) == {"prompt": p.fingerprint(), "run": run}
