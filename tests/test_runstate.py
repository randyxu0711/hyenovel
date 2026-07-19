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


def _full_story(tmp_path):
    d = tmp_path / "s01"; d.mkdir()
    for name in ("analysis.json", "feedback.json", "viz.json",
                 "analysis.md", "feedback.md"):
        (d / name).write_text(f"OLD:{name}", encoding="utf-8")
    (d / "source.md").write_text("原文", encoding="utf-8")
    (d / "usage.jsonl").write_text("{}\n", encoding="utf-8")
    return d


def test_snapshot_moves_artifacts_keeps_source(tmp_path):
    d = _full_story(tmp_path)
    runstate.snapshot_to_prev(d)
    assert not (d / "analysis.json").exists()          # 搬走了
    assert (d / ".prev" / "analysis.json").read_text(encoding="utf-8") == "OLD:analysis.json"
    assert (d / "source.md").exists()                  # 輸入不動
    assert (d / "usage.jsonl").exists()                # 帳本不動


def test_restore_brings_back_and_removes_prev(tmp_path):
    d = _full_story(tmp_path)
    runstate.snapshot_to_prev(d)
    (d / "analysis.json").write_text("NEW", encoding="utf-8")   # 假裝重跑寫了新的
    runstate.restore_prev(d)
    assert (d / "analysis.json").read_text(encoding="utf-8") == "OLD:analysis.json"
    assert not (d / ".prev").exists()


def test_restore_is_idempotent_when_no_prev(tmp_path):
    d = _full_story(tmp_path)
    runstate.restore_prev(d)                            # 沒有 .prev,不拋
    assert (d / "analysis.json").exists()


def test_discard_prev_removes_it(tmp_path):
    d = _full_story(tmp_path)
    runstate.snapshot_to_prev(d)
    runstate.discard_prev(d)
    assert not (d / ".prev").exists()
    assert not (d / "analysis.json").exists()           # discard 不還原(commit 語意)


def test_restore_partial_prev(tmp_path):
    """restore_prev 只還原存在的檔案(partial .prev)"""
    d = _full_story(tmp_path)
    runstate.snapshot_to_prev(d)
    # 刪掉 .prev 中的某些檔案,模擬部分復原情境
    (d / ".prev" / "feedback.json").unlink()
    (d / ".prev" / "viz.json").unlink()
    # 寫入新的 analysis.json
    (d / "analysis.json").write_text("NEW", encoding="utf-8")
    # 現在 .prev 只有 analysis.md, feedback.md, analysis.json 沒了
    # restore 應該只還原存在的檔案
    runstate.restore_prev(d)
    assert (d / "analysis.md").read_text(encoding="utf-8") == "OLD:analysis.md"
    assert (d / "feedback.md").read_text(encoding="utf-8") == "OLD:feedback.md"
    # analysis.json 被復原了
    assert (d / "analysis.json").read_text(encoding="utf-8") == "OLD:analysis.json"
    assert not (d / ".prev").exists()


def test_snapshot_skips_missing_artifacts(tmp_path):
    """snapshot 只搬存在的檔案"""
    d = tmp_path / "s01"; d.mkdir()
    # 只創建部分 artifact
    (d / "analysis.json").write_text("data", encoding="utf-8")
    (d / "source.md").write_text("原文", encoding="utf-8")
    (d / "usage.jsonl").write_text("{}\n", encoding="utf-8")
    # 不創建其他的
    runstate.snapshot_to_prev(d)
    # 只有 analysis.json 應該被搬到 .prev
    assert not (d / "analysis.json").exists()
    assert (d / ".prev" / "analysis.json").exists()
    # 其他檔案不應該在 .prev 裡
    assert not (d / ".prev" / "feedback.json").exists()
    # 輸入應該還在
    assert (d / "source.md").exists()
    assert (d / "usage.jsonl").exists()
