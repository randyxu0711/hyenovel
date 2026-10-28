"""舊 stories/<slug>/ 檔案 → DB。冪等、可重跑(spec §8 R1)。

切片 1–4 期間舊 server 仍在寫檔,DB 是它的唯讀鏡像:重跑只補新增的部分
(冪等鍵見 repo.py)。切片 4 web 改接 den 之前最後跑一次。

- 一篇 = 一個 transaction:中途例外整篇 rollback,不留半篇;其他篇照跑。
- 單一項目壞掉(JSON 壞、過不了 v1、jsonl 壞行)→ 跳過、記 `event=import-skip`、報告列出,
  同篇其他項目照匯。被拒絕的東西要留痕(#21)。
- 不匯入:衍生物(index/label-map/viz/*.md)與 usage.jsonl(舊 SDK 成本不可比)。
  settled.jsonl 只取 ok 列。理由見切片 1 plan「範圍決定」。

    python -m marrow.importer [--stories DIR] [--db URL]
"""
import argparse
import json
import logging
import time
from pathlib import Path

from . import db, repo, schema

log = logging.getLogger("hyenovel")

_ROOT = Path(__file__).resolve().parent.parent
_KINDS = ("analysis", "feedback")


def _skip(rep, item, reason):
    rep["skipped"].append(f"{item}: {reason}")
    log.warning(f"event=import-skip slug={rep['slug']} item={item} reason={reason}")


_REQUIRED = {
    "transcript.jsonl": ("session", "ts", "role", "text"),
    "conclusions.jsonl": ("id", "kind", "text", "refs", "quotes", "provenance", "valid_from"),
    "settled.jsonl": ("session", "ts", "written"),
}


def _jsonl(rep, path: Path) -> list[dict]:
    """壞行(非 JSON)與形狀不對的行(不是 object、缺必要欄)都只跳過那一行——
    丟 KeyError 會讓整篇 rollback、每次重跑都卡在同一行。"""
    if not path.exists():
        return []
    rows = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            _skip(rep, f"{path.name}:{i}", "bad-json")
            continue
        if not isinstance(row, dict) or any(k not in row for k in _REQUIRED[path.name]):
            _skip(rep, f"{path.name}:{i}", "bad-shape")
            continue
        rows.append(row)
    return rows


def _artifact_body(rep, story_dir: Path, kind: str) -> dict | None:
    p = story_dir / f"{kind}.json"
    if not p.exists():
        return None
    try:
        body = schema.to_v1(kind, json.loads(p.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        _skip(rep, kind, "bad-json")
        return None
    except UnicodeDecodeError:
        _skip(rep, kind, "bad-encoding")
        return None
    errors = schema.validate_v1(kind, body)
    if errors:
        _skip(rep, kind, f"schema-v1 {errors[0]}")
        return None
    return body


def import_story(conn, story_dir: Path, now: float) -> dict:
    rep = {"slug": story_dir.name, "source_versions_added": 0, "artifacts_added": 0,
           "utterances_added": 0, "conclusions_added": 0, "settlements_added": 0, "skipped": []}
    bodies = {k: _artifact_body(rep, story_dir, k) for k in _KINDS}
    title = (bodies["analysis"] or {}).get("title")
    with conn:
        sid = repo.ensure_story(conn, story_dir.name, title, now)
        vid, created = repo.add_source_version(
            conn, sid, (story_dir / "source.md").read_text(encoding="utf-8"), now)
        rep["source_versions_added"] += created
        for kind, body in bodies.items():
            if body is None:
                continue
            aid, created = repo.add_artifact(
                conn, sid, vid, kind, schema.SCHEMA_VERSION, body,
                {"tier": "A", "runner": "legacy-sdk", "imported_from": f"{kind}.json"}, now)
            rep["artifacts_added"] += created
            repo.set_current(conn, sid, kind, aid)

        sessions: dict[str, list[dict]] = {}
        for row in _jsonl(rep, story_dir / "transcript.jsonl"):
            sessions.setdefault(row["session"], []).append(row)
        disc = {}
        for session, rows in sessions.items():
            d = repo.ensure_discussion(conn, sid, session, "web", None, min(r["ts"] for r in rows))
            repo.close_discussion(conn, d, max(r["ts"] for r in rows))
            disc[session] = d
            for seq, r in enumerate(rows):
                rep["utterances_added"] += repo.add_utterance(
                    conn, d, seq, r["role"], r["text"], r["ts"], "den",
                    r.get("anchors") or [], r.get("analysis_fp"))

        for c in _jsonl(rep, story_dir / "conclusions.jsonl"):
            rep["conclusions_added"] += repo.add_conclusion(
                conn, sid, c["id"],
                disc.get(c["provenance"].get("session")) if isinstance(c["provenance"], dict) else None,
                c["kind"], c["text"],
                c["refs"], c["quotes"], c["provenance"], c["valid_from"], c.get("invalidated_at"))

        for s in _jsonl(rep, story_dir / "settled.jsonl"):
            if s.get("ok") and s["session"] in disc:
                rep["settlements_added"] += repo.add_settlement(
                    conn, disc[s["session"]], s["ts"], s["written"])
    return rep


def import_all(conn, stories_root: Path, now: float) -> list[dict]:
    """依 slug 排序逐篇匯入。DB 裡有、磁碟上已沒有的篇(例:fresh run 被取消、目錄被刪)
    只記 `event=import-orphan`,不刪——鏡像不替使用者決定刪什麼。"""
    reps = []
    dirs = sorted(p for p in stories_root.iterdir() if (p / "source.md").is_file())
    on_disk = {d.name for d in dirs}
    for (slug,) in conn.execute("SELECT slug FROM story ORDER BY slug").fetchall():
        if slug not in on_disk:
            log.warning(f"event=import-orphan slug={slug}")
    for d in dirs:
        try:
            reps.append(import_story(conn, d, now))
        except Exception as e:
            log.warning(f"event=import-fail slug={d.name} err={type(e).__name__}")
            reps.append({"slug": d.name, "skipped": [f"story: {type(e).__name__}"]})
    return reps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m marrow.importer")
    ap.add_argument("--stories", type=Path, default=_ROOT / "stories")
    ap.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    url = args.db or db.database_url()
    conn = db.connect(url)
    try:
        path = url.removeprefix("sqlite:///")
        db.migrate(conn, None if path == ":memory:" else Path(path))
        reps = import_all(conn, args.stories, time.time())
    finally:
        conn.close()
    for r in reps:
        added = " ".join(f"{k.removesuffix('_added')}+{v}" for k, v in r.items() if k.endswith("_added"))
        print(f"{r['slug']}: {added or '-'}" + "".join(f"\n  skipped {s}" for s in r["skipped"]))
    return 1 if any(r["skipped"] for r in reps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
