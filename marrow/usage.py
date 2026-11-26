"""用量帳本的唯讀報表:`python -m marrow.usage [--since DAYS] [--by kind|prompt|tag|character|work|model] [--json]`。"""
import argparse
import json
import sqlite3
import statistics
import sys
import time
from collections import Counter

from marrow import db, repo

CLASSES = ("adopted", "unselected", "not_injected", "rejected", "cancelled", "error", "unsaved")
LABELS = {"adopted": "採用", "unselected": "未選用", "not_injected": "未帶入", "rejected": "退回",
          "cancelled": "中止", "error": "錯誤", "unsaved": "未保存"}
TOKENS = ("input", "output", "cache_read", "cache_creation", "thinking")
TOKEN_LABELS = ("輸入", "輸出", "cache讀", "cache寫", "thinking")
MARKS = {"stopped": "停下", "misread": "讀錯"}
SIGNALS = {"voice": "像它", "edited": "編輯", "remembered": "記住", "digest_edited": "摘要改過",
           "saved": "建議記憶存入", "skipped": "建議記憶略過"}
CATEGORIES = {"analyst": "analysis", "reviewer": "analysis", "chat": "chat", "redo": "chat",
              "digest": "upkeep", "compact": "upkeep", "candidates": "character", "candidate_revise": "character"}
CATEGORY_ORDER = ("analysis", "chat", "upkeep", "character", "other")
_OUTCOME = {"gate_rejected": "rejected", "discarded": "unsaved", "cancelled": "cancelled"}


def injected(conn) -> set[int]:
    ids: set[int] = set()
    for (raw,) in conn.execute("SELECT recipe FROM utterance WHERE recipe IS NOT NULL "
                               "UNION ALL SELECT recipe FROM utterance_variant WHERE recipe IS NOT NULL"):
        snap = json.loads(raw).get("prior")
        if snap:
            ids.update(snap.get("digests") or ())
    return ids


def _edited_copies(conn, digest_id: int) -> list[int]:
    me = conn.execute("SELECT root_id FROM digest WHERE id = ?", (digest_id,)).fetchone()
    if me is None:
        return []
    out = []
    for i, edited in conn.execute("SELECT id, edited FROM digest WHERE root_id = ? AND id > ? ORDER BY id",
                                  (me[0], digest_id)):
        if not edited:
            break
        out.append(i)
    return out


def classify(conn, row: dict, brought: set[int] | None = None) -> str:
    outcome = row["outcome"]
    if outcome is None:
        return "error"
    if outcome != "ok":
        return _OUTCOME.get(outcome, "error")
    kind = row["kind"]
    if kind in ("chat", "redo"):
        if row["seq"] is None:
            return "unsaved"
        u = conn.execute("SELECT variant FROM utterance WHERE discussion_id = ? AND seq = ?",
                         (row["discussion_id"], row["seq"])).fetchone()
        return "adopted" if u is None or u[0] == row["variant"] else "unselected"
    if kind == "compact":
        return "adopted" if row["seq"] is not None else "unsaved"
    if kind in ("candidates", "candidate_revise"):
        return "adopted" if row["character_id"] is not None else "unselected"
    if kind == "digest":
        if row["digest_id"] is None:
            return "unsaved"
        brought = injected(conn) if brought is None else brought
        family = [row["digest_id"], *_edited_copies(conn, row["digest_id"])]
        return "adopted" if brought.intersection(family) else "not_injected"
    return "adopted"


def running(row: dict) -> bool:
    return row["outcome"] is None and row["ended_at"] is None


def unknown(row: dict) -> bool:
    return row["tokens"] is None


def category(kind: str) -> str:
    return CATEGORIES.get(kind, "other")


def _key(row: dict, by: str) -> str:
    if by == "prompt":
        return f"{row['kind']}@{row['prompt_fp']}"
    if by == "tag":
        return row["tag"] or "-"
    if by == "character":
        if row["character_id"] is None:
            return "-"
        return f"{row['character_id']}@{row['character_v'] if row['character_v'] is not None else '-'}"
    if by == "work":
        return str(row["story_id"]) if row["story_id"] is not None else "-"
    if by == "model":
        return f"{row['model'] or '-'}/{row['effort'] or '-'}"
    return row["kind"]


def _groups(rows: list[dict], by: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(_key(r, by), []).append(r)
    return dict(sorted(out.items()))


def summarize(conn, rows: list[dict], by: str = "kind") -> list[dict]:
    brought = injected(conn)
    out = []
    for key, rs in _groups(rows, by).items():
        tokens = {t: sum((r["tokens"] or {}).get(t) or 0 for r in rs) for t in TOKENS}
        denom = tokens["input"] + tokens["cache_read"] + tokens["cache_creation"]
        ms = [r["duration_ms"] for r in rs if r["duration_ms"] is not None]
        counts = Counter(classify(conn, r, brought) for r in rs)
        out.append({"group": key, "n": len(rs), "tokens": tokens,
                    "partial": any(r["tokens_partial"] for r in rs),
                    "cost_usd": sum(r["cost_usd"] or 0 for r in rs),
                    "classes": {c: counts[c] for c in CLASSES},
                    "unknown": sum(unknown(r) for r in rs),
                    "cache_hit": tokens["cache_read"] / denom if denom else None,
                    "ms_median": statistics.median(ms) if ms else None})
    return out


USED = ("input", "output", "cache_read", "cache_creation")
UNBOUND_KINDS = ("chat", "redo", "digest", "compact")
_KIND_ORDER = {k: i for i, k in enumerate(CATEGORIES)}


def used(row: dict) -> int:
    t = row["tokens"] or {}
    return sum(t.get(k) or 0 for k in USED)


def complete(row: dict) -> bool:
    return row["outcome"] == "ok" and not row["tokens_partial"] and row["tokens"] is not None


def _mean(xs) -> int | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs)) if xs else None


def _bucket() -> dict:
    return {"tokens": 0, "partial": False, "by_category": {}}


def _add(b: dict, r: dict) -> None:
    b["tokens"] += used(r)
    b["partial"] |= bool(r["tokens_partial"])
    cat = category(r["kind"])
    b["by_category"][cat] = b["by_category"].get(cat, 0) + used(r)


def _quota(all_rows: list[dict]) -> dict | None:
    windows = ("five_hour", "seven_day")
    seen = [r for r in all_rows if r["ended_at"] is not None and r["rate_limit"]
            and any(isinstance(r["rate_limit"].get(w), dict) for w in windows)]
    if not seen:
        return None
    r = max(seen, key=lambda x: x["ended_at"])
    rl = r["rate_limit"]
    return {"at": r["ended_at"], **{w: {"utilization": rl[w].get("utilization"), "resets_at": rl[w].get("resetsAt")}
                                    if isinstance(rl.get(w), dict) else None for w in windows}}


def _categories(rows: list[dict], total: int) -> list[dict]:
    if not total:
        return []
    out = []
    for cat in CATEGORY_ORDER:
        rs = [r for r in rows if category(r["kind"]) == cat]
        if rs:
            tokens = sum(used(r) for r in rs)
            out.append({"id": cat, "n": len(rs), "tokens": tokens, "partial": any(r["tokens_partial"] for r in rs),
                        "avg": _mean(used(r) for r in rs if complete(r)), "share": tokens / total})
    return out


def _works(conn, rows: list[dict]) -> tuple[list[dict], dict | None]:
    stories = repo.story_rows(conn, [r["story_id"] for r in rows if r["story_id"] is not None])
    mine = [r for r in rows if r["story_id"] in stories and r["started_at"] >= stories[r["story_id"]]["created_at"]]
    jobs = repo.call_versions(conn, [r["job_id"] for r in mine if r["job_id"] is not None])
    versions = repo.version_numbers(conn, {r["story_id"] for r in mine})
    works: dict[int, dict] = {}
    for r in mine:
        sid = r["story_id"]
        w = works.setdefault(sid, {"story_id": sid, "slug": stories[sid]["slug"], "archived": stories[sid]["archived"],
                                   **_bucket(), "versions": {n: {"n": n, "tokens": 0, "partial": False,
                                                                 "analyzed": done} for n, done in versions[sid]}})
        _add(w, r)
        j = jobs.get(r["job_id"])
        if j and j[0] == sid and j[2] <= r["started_at"] and j[1] in w["versions"]:
            v = w["versions"][j[1]]
            v["tokens"] += used(r)
            v["partial"] |= bool(r["tokens_partial"])
    out = sorted(works.values(), key=lambda w: (-w["tokens"], w["story_id"]))
    for w in out:
        w["versions"] = list(w["versions"].values())
    loose = [r for r in rows if r["story_id"] is None and r["kind"] in UNBOUND_KINDS]
    unbound = None
    if loose:
        unbound = _bucket()
        for r in loose:
            _add(unbound, r)
    return out, unbound


def _ratio(cur, prev) -> float | None:
    return (cur - prev) / prev if cur is not None and prev else None


def _ranked(groups: dict[tuple, list[dict]], family, recorded, fields) -> list[dict]:
    rows = []
    for key, rs in groups.items():
        ms = [r["duration_ms"] for r in rs if r["duration_ms"] is not None]
        rows.append({**fields(key), "first_at": min(r["started_at"] for r in rs),
                     "last_at": max(r["started_at"] for r in rs), "n": len(rs), "avg": _mean(used(r) for r in rs),
                     "thinking": _mean((r["tokens"] or {}).get("thinking") for r in rs),
                     "ms_median": statistics.median(ms) if ms else None, "current": False, "delta": None,
                     "recorded": recorded(key), "_family": family(key)})
    for fam in {r["_family"] for r in rows}:
        live = sorted((r for r in rows if r["_family"] == fam and r["recorded"]), key=lambda r: -r["last_at"])
        if live:
            live[0]["current"] = True
            if len(live) > 1:
                cur, prev = live[0], live[1]
                cur["delta"] = {"avg": _ratio(cur["avg"], prev["avg"]),
                                "thinking": _ratio(cur["thinking"], prev["thinking"]),
                                "ms": _ratio(cur["ms_median"], prev["ms_median"])}
    rows.sort(key=lambda r: (r["_family"], -r["first_at"]))
    for r in rows:
        del r["_family"]
    return rows


def _compare(all_rows: list[dict]) -> dict:
    full = [r for r in all_rows if complete(r)]
    cfg: dict[tuple, list[dict]] = {}
    for r in full:
        key = (r["kind"], r["prompt_fp"], *((r["runner"], r["model"], r["effort"]) if r["runner"] is not None
                                           else (None, None, None)))
        cfg.setdefault(key, []).append(r)
    chr_: dict[tuple, list[dict]] = {}
    for r in full:
        if r["kind"] in ("chat", "redo"):
            key = (r["character_id"], r["character_v"]) if r["character_id"] is not None else (None, None)
            chr_.setdefault(key, []).append(r)
    return {"config": _ranked(cfg, lambda k: (_KIND_ORDER.get(k[0], len(_KIND_ORDER)), k[0]),
                              lambda k: k[2] is not None,
                              lambda k: dict(zip(("kind", "prompt_fp", "runner", "model", "effort"), k))),
            "character": _ranked(chr_, lambda k: (k[0] is None, k[0] or ""), lambda k: k[0] is not None,
                                 lambda k: {"character_id": k[0], "character_v": k[1]})}


def page(conn, rows: list[dict], all_rows: list[dict], now: float) -> dict:
    n_running = sum(running(r) for r in rows)
    rows = [r for r in rows if not running(r)]
    total = sum(used(r) for r in rows)
    brought = injected(conn)
    unused = sum(used(r) for r in rows if classify(conn, r, brought) != "adopted")
    works, unbound = _works(conn, rows)
    return {"as_of": now, "quota": _quota(all_rows),
            "total": {"tokens": total, "partial": any(r["tokens_partial"] for r in rows)},
            "categories": _categories(rows, total),
            "unused_share": unused / total if total else None,
            "works": works, "unbound": unbound, "compare": _compare(all_rows),
            "running": n_running,
            "completeness": {"partial": sum(bool(r["tokens_partial"]) for r in rows),
                             "unknown": sum(unknown(r) for r in rows)}}


def _chat_signals(conn, r: dict, sig: Counter) -> None:
    d, seq, v = r["discussion_id"], r["seq"], r["variant"]
    if conn.execute("SELECT 1 FROM voice_mark WHERE discussion_id = ? AND seq = ? AND variant = ?",
                    (d, seq, v)).fetchone():
        sig["voice"] += 1
    for (mark,) in conn.execute("SELECT mark FROM reaction WHERE discussion_id = ? AND seq = ? AND variant = ?",
                                (d, seq, v)):
        sig[f"mark:{mark}"] += 1
    if conn.execute("SELECT 1 FROM utterance WHERE discussion_id = ? AND seq = ? AND variant = ? "
                    "AND edited_at IS NOT NULL", (d, seq, v)).fetchone():
        sig["edited"] += 1
    if conn.execute("SELECT 1 FROM memory WHERE discussion_id = ? AND seq = ?", (d, seq)).fetchone():
        sig["remembered"] += 1


def _digest_signals(conn, r: dict, sig: Counter) -> None:
    g = conn.execute("SELECT discussion_id, created_at FROM digest WHERE id = ?", (r["digest_id"],)).fetchone()
    if g is None:
        return
    if _edited_copies(conn, r["digest_id"]):
        sig["digest_edited"] += 1
    for (res,) in conn.execute("SELECT DISTINCT resolution FROM memory_candidate WHERE discussion_id = ? "
                               "AND created_at = ? AND resolution IS NOT NULL", (g[0], g[1])):
        sig[res] += 1


def effects(conn, rows: list[dict], by: str = "kind") -> list[dict]:
    brought = injected(conn)
    out = []
    for key, rs in _groups(rows, by).items():
        sig: Counter = Counter()
        n = 0
        for r in rs:
            if r["kind"] in ("chat", "redo") and classify(conn, r, brought) == "adopted" and r["seq"] is not None:
                n += 1
                _chat_signals(conn, r, sig)
            elif r["kind"] == "digest" and r["outcome"] == "ok" and r["digest_id"] is not None:
                n += 1
                _digest_signals(conn, r, sig)
        if n:
            out.append({"group": key, "n": n, "signals": dict(sorted(sig.items()))})
    return out


def latest_rate_limit(rows: list[dict]) -> tuple[float, dict] | None:
    seen = [(r["ended_at"], r["rate_limit"]) for r in rows if r["rate_limit"] and r["ended_at"] is not None]
    return max(seen, key=lambda x: x[0]) if seen else None


def _when(t) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(t)) if isinstance(t, (int, float)) else "?"


def _pct(x) -> str:
    return f"{x * 100:.0f}%" if isinstance(x, (int, float)) else "?"


def _rate_line(latest: tuple[float, dict]) -> str:
    at, rl = latest
    parts = [f"{label} {_pct(rl[w].get('utilization'))}(重置 {_when(rl[w].get('resetsAt'))})"
             for w, label in (("five_hour", "5 小時"), ("seven_day", "7 天")) if isinstance(rl.get(w), dict)]
    return " · ".join(parts + [f"觀測於 {_when(at)}"])


def _signal_label(name: str) -> str:
    return MARKS.get(name[5:], name[5:]) if name.startswith("mark:") else SIGNALS.get(name, name)


def render(groups: list[dict], fx: list[dict], latest, by: str, n_running: int = 0) -> str:
    lines = [_rate_line(latest), ""] if latest else []
    if n_running:
        lines += [f"進行中 {n_running} 次(不列入下表)", ""]
    head = {"kind": "種類", "prompt": "種類@prompt", "tag": "標籤", "character": "讀伴@卡版", "work": "作品",
            "model": "模型/effort"}[by]
    cols = [head, "次數", *TOKEN_LABELS, "美元(參考)", *(LABELS[c] for c in CLASSES), "用量不明", "cache命中", "延遲中位"]
    lines.append("\t".join(cols))
    for g in groups:
        mark = "≥" if g["partial"] else ""
        lines.append("\t".join([g["group"], str(g["n"]), *(f"{mark}{g['tokens'][t]}" for t in TOKENS),
                                f"{g['cost_usd']:.4f}", *(str(g["classes"][c]) for c in CLASSES), str(g["unknown"]),
                                _pct(g["cache_hit"]) if g["cache_hit"] is not None else "-",
                                f"{g['ms_median']:.0f}ms" if g["ms_median"] is not None else "-"]))
    if not groups:
        lines.append("(這段期間沒有呼叫)")
    if fx:
        lines += ["", "效果訊號"]
        for e in fx:
            cells = [f"{_signal_label(k)} {v}/{e['n']}" for k, v in e["signals"].items()]
            lines.append("\t".join([e["group"], f"n={e['n']}", *cells]))
    return "\n".join(lines) + "\n"


def main(argv=None, out=sys.stdout, err=sys.stderr, now=time.time) -> int:
    ap = argparse.ArgumentParser(prog="python -m marrow.usage")
    ap.add_argument("--db", default=None)
    ap.add_argument("--since", type=float, default=7, metavar="DAYS")
    ap.add_argument("--by", choices=("kind", "prompt", "tag", "character", "work", "model"), default="kind")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        conn = db.connect_readonly(args.db or db.database_url())
        try:
            rows = repo.calls_since(conn, now() - args.since * 86400)
            n_running = sum(running(r) for r in rows)
            rows = [r for r in rows if not running(r)]
            groups = summarize(conn, rows, args.by)
            fx = effects(conn, rows, "kind" if args.by == "tag" else args.by)
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        err.write(f"讀不到用量帳本({e})。DB 不存在,或還沒升到含帳本的版本:重啟 den 會自動升級。\n")
        return 1
    latest = latest_rate_limit(rows)
    if args.json:
        rate = {"at": latest[0], **latest[1]} if latest else None
        out.write(json.dumps({"rate_limit": rate, "running": n_running, "groups": groups, "effects": fx}, ensure_ascii=False, indent=1) + "\n")
    else:
        out.write(render(groups, fx, latest, args.by, n_running))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
