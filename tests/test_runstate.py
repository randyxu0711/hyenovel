"""runstate:run.json 狀態機 + 續跑點推導。全是我們的政策,純函式吃 Path。"""
import json

import runstate


def _mk(tmp_path, **files):
    d = tmp_path / "s01"
    d.mkdir()
    for name, content in files.items():
        (d / name.replace("__", ".")).write_text(content, encoding="utf-8")
    return d


def test_write_then_read_roundtrips(tmp_path):
    d = tmp_path / "s01"; d.mkdir()
    runstate.write(d, status="paused", stage="criticizer", reason="usage-limit",
                   resets_at=123, title="標題", cost_usd=0.4)
    got = runstate.read(d)
    assert got["status"] == "paused" and got["stage"] == "criticizer"
    assert got["reason"] == "usage-limit" and got["resets_at"] == 123
    assert got["title"] == "標題" and got["cost_usd"] == 0.4
    assert got["updated"]


def test_read_missing_returns_none(tmp_path):
    d = tmp_path / "s01"; d.mkdir()
    assert runstate.read(d) is None


def test_read_corrupt_returns_none(tmp_path):
    d = _mk(tmp_path, run__json="{ 不是 JSON")
    assert runstate.read(d) is None


def test_write_skips_when_dir_absent(tmp_path):
    runstate.write(tmp_path / "ghost", status="running", stage="analyst")  # 不拋
    assert not (tmp_path / "ghost").exists()


def test_resume_point_empty_is_analyst(tmp_path):
    d = tmp_path / "s01"; d.mkdir()
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    assert runstate.resume_point(d) == "analyst"


def test_resume_point_half_analysis_is_analyst(tmp_path):
    d = _mk(tmp_path, analysis__json='{ "nodes": [')   # 截斷 → parse 不動
    assert runstate.resume_point(d) == "analyst"


def test_resume_point_good_analysis_is_criticizer(tmp_path):
    d = _mk(tmp_path, analysis__json=json.dumps({"nodes": [], "edges": []}))
    assert runstate.resume_point(d) == "criticizer"


def test_resume_point_analysis_and_feedback_is_render(tmp_path):
    d = _mk(tmp_path,
            analysis__json=json.dumps({"nodes": [], "edges": []}),
            feedback__json=json.dumps({"key_points": []}))
    assert runstate.resume_point(d) == "render"


def test_resume_point_half_feedback_falls_back_to_criticizer(tmp_path):
    d = _mk(tmp_path,
            analysis__json=json.dumps({"nodes": [], "edges": []}),
            feedback__json='{ "key_points": [')
    assert runstate.resume_point(d) == "criticizer"


def test_is_complete_true_only_with_all_three(tmp_path):
    d = _mk(tmp_path,
            analysis__json=json.dumps({"nodes": [], "edges": []}),
            feedback__json=json.dumps({"key_points": []}))
    assert runstate.is_complete(d) is False          # 缺 viz.json
    (d / "viz.json").write_text("{}", encoding="utf-8")
    assert runstate.is_complete(d) is True
