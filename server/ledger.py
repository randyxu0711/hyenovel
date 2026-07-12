"""用量帳本:每個 LLM turn 一行 append 到 stories/<slug>/usage.jsonl(正本)。

單一擁有寫入邏輯的模組 —— orchestrator 與 discuss 都呼叫這裡,record 格式只有這裡知道。
append-only、同步寫(不 await)→ 對其他 asyncio task 原子;per-slug 不同檔,結構上零競爭。
總帳走讀時聚合(見 aggregate/aggregate_all),不落第二個檔。
"""
import json
import time

from . import config
from .log import log


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
    """append 一行到該篇 usage.jsonl。目錄不存在就跳過(記帳絕不擋主流程)。
    寫入 I/O 失敗(磁碟滿/權限/TOCTOU 被 rmtree)也吞掉並記 log,絕不讓記帳打斷主流程。"""
    if not (config.STORIES / slug).is_dir():
        return
    line = json.dumps(record_of(phase, attempt, turn), ensure_ascii=False)
    try:
        with _usage_path(slug).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        log.warning(f"ledger append failed slug={slug} phase={phase}: {type(e).__name__}")


def load(slug):
    """讀該篇所有 record;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。
    讀取 I/O 失敗(TOCTOU 被 rmtree/換成目錄)也吞掉,回 []。"""
    p = _usage_path(slug)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _zero():
    return {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "cost_usd": 0.0}


def _round_cost(d):
    d = dict(d)
    d["cost_usd"] = round(d["cost_usd"], 6)
    return d


def aggregate(slug):
    """單篇:各 phase 小計 + 總計 + 衍生量(cache 命中率、重試成本)。無資料回 empty 態。"""
    rows = load(slug)
    if not rows:
        return {"slug": slug, "empty": True, "phases": {}, "total": _zero(),
                "cache_read_ratio": 0.0, "retry_cost_usd": 0.0}
    phases, total, retry_cost = {}, _zero(), 0.0
    for r in rows:
        acc = phases.setdefault(r.get("phase", "unknown"), _zero())
        for k in ("input", "output", "cache_creation", "cache_read"):
            v = r.get(k, 0) or 0
            acc[k] += v
            total[k] += v
        c = r.get("cost_usd", 0.0) or 0.0
        acc["cost_usd"] += c
        total["cost_usd"] += c
        if (r.get("attempt", 0) or 0) > 0:
            retry_cost += c
    denom = total["input"] + total["cache_creation"] + total["cache_read"]
    return {
        "slug": slug, "empty": False,
        "phases": {k: _round_cost(v) for k, v in phases.items()},
        "total": _round_cost(total),
        "cache_read_ratio": round(total["cache_read"] / denom, 4) if denom else 0.0,
        "retry_cost_usd": round(retry_cost, 6),
    }


def aggregate_all():
    """跨篇:掃 stories/*/usage.jsonl,總計 + 每篇 rollup。"""
    stories, total = [], _zero()
    if config.STORIES.is_dir():
        for d in sorted(p for p in config.STORIES.iterdir() if p.is_dir()):
            agg = aggregate(d.name)
            if agg["empty"]:
                continue
            t = agg["total"]
            for k in _zero():
                total[k] += t[k]
            stories.append({
                "slug": d.name,
                "cost_usd": t["cost_usd"],
                "tokens": t["input"] + t["output"] + t["cache_creation"] + t["cache_read"],
            })
    return {"empty": not stories, "total": _round_cost(total), "stories": stories}
