"""critique Run 的狀態正本(run.json)+ 續跑點推導。純函式吃 story_dir: Path。

只由確定性層寫(server/critique.py + re-analyze 編排),subagent 永不碰。
續跑點靠「產物是否 wellformed」推導(輕量、防漂移),不 spawn viz 子行程;
真的要跳過某格時,orchestrator 會再過一次完整閘門確認(見 orchestrator)。
"""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import atomicio

RUN = "run.json"
PREV = ".prev"
_ARTIFACTS = ("analysis.json", "feedback.json", "viz.json",
              "analysis.md", "feedback.md")


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read(story_dir) -> dict | None:
    """讀 run.json;缺或壞回 None(不炸)。"""
    p = Path(story_dir) / RUN
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write(story_dir, *, status, stage, reason=None, resets_at=None,
          title=None, cost_usd=0.0) -> None:
    """原子同步寫 run.json。目錄不存在就跳過(狀態寫入絕不擋主流程)。"""
    d = Path(story_dir)
    if not d.is_dir():
        return
    payload = {
        "status": status, "stage": stage, "reason": reason,
        "resets_at": resets_at, "title": title,
        "cost_usd": round(cost_usd or 0.0, 4), "updated": _iso_now(),
    }
    atomicio.write_text_atomic(d / RUN, json.dumps(payload, ensure_ascii=False) + "\n")


def _wellformed(path, required) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and all(k in data for k in required)


def analysis_wellformed(story_dir) -> bool:
    return _wellformed(Path(story_dir) / "analysis.json", ("nodes", "edges"))


def feedback_wellformed(story_dir) -> bool:
    return _wellformed(Path(story_dir) / "feedback.json", ("key_points",))


def resume_point(story_dir) -> str:
    """從產物推導續跑點(輕量,不過完整閘門)。"""
    d = Path(story_dir)
    if feedback_wellformed(d) and analysis_wellformed(d):
        return "render"
    if analysis_wellformed(d):
        return "criticizer"
    return "analyst"


def is_complete(story_dir) -> bool:
    """re-analyze 守門用:三個產物都在且 wellformed = 完整故事。"""
    d = Path(story_dir)
    return analysis_wellformed(d) and feedback_wellformed(d) and (d / "viz.json").exists()


def snapshot_to_prev(story_dir) -> None:
    """搬既有 artifact 到 .prev/(re-analyze 的退路)。輸入/帳本/狀態不動。"""
    d = Path(story_dir)
    prev = d / PREV
    prev.mkdir(exist_ok=True)
    for name in _ARTIFACTS:
        src = d / name
        if src.exists():
            os.replace(src, prev / name)


def restore_prev(story_dir) -> None:
    """.prev/ 搬回覆蓋;全搬回才 rmtree(.prev)。逐檔 os.replace 冪等、crash 安全。"""
    d = Path(story_dir)
    prev = d / PREV
    if not prev.is_dir():
        return
    for name in _ARTIFACTS:
        src = prev / name
        if src.exists():
            os.replace(src, d / name)
    shutil.rmtree(prev, ignore_errors=True)


def discard_prev(story_dir) -> None:
    """commit:重新分析成功,舊版不再需要。"""
    shutil.rmtree(Path(story_dir) / PREV, ignore_errors=True)
