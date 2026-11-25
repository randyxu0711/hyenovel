"""用量帳本的唯讀報表:`python -m marrow.usage [--since DAYS] [--by kind|prompt|tag] [--json]`。"""
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


def unknown(row: dict) -> bool:
    return row["tokens"] is None


def _key(row: dict, by: str) -> str:
    if by == "prompt":
        return f"{row['kind']}@{row['prompt_fp']}"
    if by == "tag":
        return row["tag"] or "-"
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


def render(groups: list[dict], fx: list[dict], latest, by: str) -> str:
    lines = [_rate_line(latest), ""] if latest else []
    head = {"kind": "種類", "prompt": "種類@prompt", "tag": "標籤"}[by]
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
    ap.add_argument("--by", choices=("kind", "prompt", "tag"), default="kind")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        conn = db.connect_readonly(args.db or db.database_url())
        try:
            rows = repo.calls_since(conn, now() - args.since * 86400)
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
        out.write(json.dumps({"rate_limit": rate, "groups": groups, "effects": fx}, ensure_ascii=False, indent=1) + "\n")
    else:
        out.write(render(groups, fx, latest, args.by))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
