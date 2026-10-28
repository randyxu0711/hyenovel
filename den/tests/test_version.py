"""den.version.fingerprint 行為契約(在 tmp_path 造目錄樹)。"""
from den import version


def _tree(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    (a / "tests").mkdir(parents=True)
    (b / "__pycache__").mkdir(parents=True)
    (a / "x.py").write_text("x = 1\n")
    (b / "y.py").write_text("y = 2\n")
    return (a, b)


def test_fingerprint_stable(tmp_path):
    roots = _tree(tmp_path)
    fp = version.fingerprint(roots)
    assert fp == version.fingerprint(roots)
    assert len(fp) == 12


def test_fingerprint_changes_on_edit(tmp_path):
    roots = _tree(tmp_path)
    before = version.fingerprint(roots)
    (roots[0] / "x.py").write_text("x = 2\n")
    assert version.fingerprint(roots) != before


def test_fingerprint_ignores_tests_and_pycache(tmp_path):
    roots = _tree(tmp_path)
    before = version.fingerprint(roots)
    (roots[0] / "tests" / "t.py").write_text("t")
    (roots[1] / "__pycache__" / "y.pyc").write_text("c")
    assert version.fingerprint(roots) == before


def test_fingerprint_default_roots():
    assert len(version.fingerprint()) == 12
