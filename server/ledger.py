"""用量帳本:每個 LLM turn 一行 append 到 stories/<slug>/usage.jsonl(正本)。

單一擁有寫入邏輯的模組 —— orchestrator 與 discuss 都呼叫這裡,record 格式只有這裡知道。
append-only、同步寫(不 await)→ 對其他 asyncio task 原子;per-slug 不同檔,結構上零競爭。
總帳走讀時聚合(見 aggregate/aggregate_all),不落第二個檔。
"""
import json
import time

from . import config


def _usage_path(slug):
    return config.STORIES / slug / "usage.jsonl"


def record_of(phase, attempt, turn):
    """把一輪 TurnResult 攤成一筆帳本 record(純函式,好測)。
    usage key 用防禦性 .get:key 名對不上時記 0、不炸(真名以真跑 log 為準)。"""
    u = turn.usage or {}
    mu = turn.model_usage or {}
    return {
        "ts": round(time.time(), 3),
        "phase": phase,
        "attempt": attempt,
        "input": u.get("input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "cache_creation": u.get("cache_creation_input_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "cost_usd": round(turn.cost or 0.0, 6),
        "model": ",".join(mu.keys()) or None,
        "num_turns": turn.num_turns,
        "duration_ms": turn.duration_ms,
    }


def append(slug, phase, attempt, turn):
    """append 一行到該篇 usage.jsonl。目錄不存在就跳過(記帳絕不擋主流程)。"""
    if not (config.STORIES / slug).is_dir():
        return
    line = json.dumps(record_of(phase, attempt, turn), ensure_ascii=False)
    with _usage_path(slug).open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load(slug):
    """讀該篇所有 record;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。"""
    p = _usage_path(slug)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out
