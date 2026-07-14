"""viz 的檔案層閘門:schema、feedback 存在性、--check 不出檔。

測的是我們的「決策」(不合契約就擋下、不出檔),
**不是** jsonschema 這個 lib 對不對 —— 那不是我們的事。
"""
import json

import pytest

import viz


def _write(base, name, data):
    (base / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _analysis(base):
    return json.loads((base / "analysis.json").read_text(encoding="utf-8"))


# ── schema 閘門:我們的決策是「不合就擋」 ──────────────────────────────

def test_valid_fixture_passes_schema_gate(story):
    slug, base = story
    assert viz.validate_schemas(base) == [], "合法樣本不該被擋"


def test_missing_required_field_is_blocked(story):
    slug, base = story
    data = _analysis(base)
    del data["nodes"]
    _write(base, "analysis.json", data)
    errors = viz.validate_schemas(base)
    assert errors and any("nodes" in e for e in errors)


def test_wrong_type_is_blocked(story):
    """intensity 應為 number,給字串要擋。"""
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["intensity"] = "很高"
    _write(base, "analysis.json", data)
    assert viz.validate_schemas(base) != []


def test_unknown_field_is_blocked(story):
    """additionalProperties:false → 多塞欄位要擋(防 schema 悄悄漂移)。"""
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["vibes"] = "good"
    _write(base, "analysis.json", data)
    assert viz.validate_schemas(base) != []


def test_bad_enum_is_blocked(story):
    """node type 不在 enum 裡 → 擋(id 慣例 t*/m*/k*/e*/c*/b* 的型別基礎)。"""
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["type"] = "vibe"
    _write(base, "analysis.json", data)
    assert viz.validate_schemas(base) != []


def test_missing_analysis_is_blocked(story):
    slug, base = story
    (base / "analysis.json").unlink()
    errors = viz.validate_schemas(base)
    assert any("analysis.json" in e and "不存在" in e for e in errors)


def test_feedback_is_optional_for_schema_gate(story):
    """feedback.json 不存在時 schema 閘門不報錯(對 analyst 階段它是可選的)。

    ⚠️ 這正是那個曾經讓 criticizer「空過」的坑:
    schema 閘門放行 ≠ criticizer 成功。
    「feedback.json 必須真的存在」是 orchestrator 的 _gate_feedback 在守,
    不是這裡。這條測試把兩者的分工釘死,免得日後有人以為這裡該擋。
    """
    slug, base = story
    assert not (base / "feedback.json").exists()
    assert viz.validate_schemas(base) == []


def test_invalid_feedback_is_blocked(story, feedback_json):
    """feedback.json 存在但不合 schema → 擋(point 缺 quotes)。"""
    slug, base = story
    del feedback_json["key_points"][0]["quotes"]
    _write(base, "feedback.json", feedback_json)
    assert viz.validate_schemas(base) != []


# ── feedback 的引用也要過閘門 ────────────────────────────────────────

def test_feedback_quotes_are_gated_too(story, feedback_json):
    slug, base = story
    source = (base / "source.md").read_text(encoding="utf-8")
    feedback_json["strengths"][0]["quotes"] = ["這句是我編的,原文沒有"]
    _write(base, "feedback.json", feedback_json)

    fb, errors = viz.load_feedback(base, source)
    assert fb is not None
    assert errors, "feedback 的幻覺引用沒被抓到"


def test_feedback_valid_quotes_get_coordinates(story, feedback_json):
    slug, base = story
    source = (base / "source.md").read_text(encoding="utf-8")
    _write(base, "feedback.json", feedback_json)

    fb, errors = viz.load_feedback(base, source)
    assert errors == []
    q = fb["strengths"][0]["_quotes"][0]
    assert q["start"] >= 0 and q["end"] > q["start"]


def test_load_feedback_absent_returns_none(story):
    slug, base = story
    fb, errors = viz.load_feedback(base, "他走進門。")
    assert fb is None and errors == []


# ── 診斷分類(意圖鏈的三種病)────────────────────────────────────────

def test_diagnostics_flags_orphan_technique():
    """技法沒 produces 任何 effect → 孤兒。"""
    a = {"nodes": [{"id": "k1", "type": "technique", "label": "x"}], "edges": []}
    assert "orphan" in viz.diagnostics(a)["k1"]


def test_diagnostics_flags_hollow_theme():
    """主題沒有任何 effect/motif 餵養 → 空心。"""
    a = {"nodes": [{"id": "t1", "type": "theme", "label": "x"}], "edges": []}
    assert "hollow" in viz.diagnostics(a)["t1"]


def test_diagnostics_flags_overloaded_theme():
    """>=4 條餵養 → 過載(什麼都往裡塞的主題)。"""
    nodes = [{"id": "t1", "type": "theme", "label": "x"}]
    edges = []
    for i in range(4):
        nodes.append({"id": f"e{i}", "type": "effect", "label": "e"})
        edges.append({"type": "serves", "from": f"e{i}", "to": "t1"})
    assert "overloaded" in viz.diagnostics({"nodes": nodes, "edges": edges})["t1"]


def test_diagnostics_healthy_graph_is_clean(story):
    """fixture 的小圖:k1→e1→t1,技法有出口、主題有餵養 → 不該被標病。"""
    slug, base = story
    classes = viz.diagnostics(_analysis(base))
    assert "orphan" not in classes.get("k1", set())
    assert "hollow" not in classes.get("t1", set())


# ── build_viz_data 契約 ─────────────────────────────────────────────

def test_build_viz_data_shape(story):
    slug, base = story
    analysis = _analysis(base)
    source = (base / "source.md").read_text(encoding="utf-8")
    viz.validate_and_locate(analysis, source)
    data = viz.build_viz_data(slug, analysis, source, viz.diagnostics(analysis))

    assert data["slug"] == "mini"
    assert data["title"] == "極小合成樣本"
    assert len(data["nodes"]) == 4 and len(data["edges"]) == 2
    assert data["feedback"] is None
    # 每個 evidence 都要帶座標給文本軸
    ev = data["nodes"][0]["evidence"][0]
    assert 0.0 <= ev["pos"] <= 1.0


def test_build_viz_data_includes_feedback(story, feedback_json):
    slug, base = story
    analysis = _analysis(base)
    source = (base / "source.md").read_text(encoding="utf-8")
    viz.validate_and_locate(analysis, source)
    _write(base, "feedback.json", feedback_json)
    fb, errors = viz.load_feedback(base, source)
    assert errors == []

    data = viz.build_viz_data(slug, analysis, source, viz.diagnostics(analysis), feedback=fb)
    assert data["feedback"]["one_line"] == "節制,但收得太急。"
    assert data["feedback"]["key_points"][0]["refs"] == ["e1"]   # 錨定到 node id
    assert data["feedback"]["key_points"][0]["quotes"][0]["start"] >= 0


# ── main():--check 不出檔、正常模式出檔 ─────────────────────────────

def test_check_mode_writes_nothing(story, monkeypatch):
    """--check:只驗閘門,一個檔都不准產出(critique 編排靠它當閘門)。

    --check 一律 sys.exit(0=過 / 1=沒過),不 return。
    """
    slug, base = story
    before = {p.name for p in base.iterdir()}

    monkeypatch.setattr(viz.sys, "argv", ["viz.py", slug, "--check"])
    with pytest.raises(SystemExit) as e:
        viz.main()
    assert e.value.code == 0, "合法樣本該以 0 離開"

    after = {p.name for p in base.iterdir()}
    assert after == before, f"--check 竟然產了檔:{after - before}"


def test_check_mode_exits_nonzero_on_bad_quote(story, monkeypatch):
    """--check 沒過要以非零離開 —— orchestrator 靠 returncode 判斷閘門結果。"""
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["evidence"][0]["quote"] = "這句原文裡根本沒有"
    _write(base, "analysis.json", data)

    monkeypatch.setattr(viz.sys, "argv", ["viz.py", slug, "--check"])
    with pytest.raises(SystemExit) as e:
        viz.main()
    assert e.value.code == 1


def test_main_writes_viz_json_and_html(story, monkeypatch):
    slug, base = story
    monkeypatch.setattr(viz.sys, "argv", ["viz.py", slug])
    viz.main()

    assert (base / "viz.json").exists()
    assert (base / "viz.html").exists()
    data = json.loads((base / "viz.json").read_text(encoding="utf-8"))
    assert data["slug"] == "mini"


def test_main_blocks_on_hallucinated_quote(story, monkeypatch):
    """幻覺引用 → 閘門擋下、非零離開、不出檔(這是硬閘門的最終行為)。"""
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["evidence"][0]["quote"] = "這句原文裡根本沒有"
    _write(base, "analysis.json", data)

    monkeypatch.setattr(viz.sys, "argv", ["viz.py", slug])
    with pytest.raises(SystemExit) as e:
        viz.main()
    assert e.value.code != 0
    assert not (base / "viz.json").exists(), "閘門沒過竟然還出檔"


def test_main_blocks_on_schema_violation(story, monkeypatch):
    slug, base = story
    data = _analysis(base)
    data["nodes"][0]["type"] = "vibe"
    _write(base, "analysis.json", data)

    monkeypatch.setattr(viz.sys, "argv", ["viz.py", slug])
    with pytest.raises(SystemExit) as e:
        viz.main()
    assert e.value.code != 0
    assert not (base / "viz.json").exists()


@pytest.mark.parametrize("arg", ["mini", "stories/mini", "stories/mini/source.md"])
def test_main_accepts_three_slug_forms(story, monkeypatch, arg):
    """容許傳 <slug>、stories/<slug>、stories/<slug>/source.md(編排端三種都會餵)。

    三種都要解析成 slug=mini → 閘門過 → exit 0。解析錯會找不到檔而 exit(非 0)。
    """
    slug, base = story
    monkeypatch.setattr(viz.sys, "argv", ["viz.py", arg, "--check"])
    with pytest.raises(SystemExit) as e:
        viz.main()
    assert e.value.code == 0, f"slug 形式 {arg!r} 沒被正確解析"


def test_main_without_args_exits(monkeypatch):
    monkeypatch.setattr(viz.sys, "argv", ["viz.py"])
    with pytest.raises(SystemExit):
        viz.main()
