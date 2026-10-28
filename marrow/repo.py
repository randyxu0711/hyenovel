"""storage repository:對 DB 的所有讀寫都經過這裡。

- **不 commit**:transaction 邊界歸呼叫者(`with conn:`)——「每次閘門提交 = 一個 transaction」
  要由知道「一次提交」範圍的那一層決定,不是由單一 INSERT 決定。
- **只寫標準 SQL**:`ON CONFLICT ... DO NOTHING/UPDATE` 可用(SQLite ≥3.24 與 Postgres 同語法);
  不用 `INSERT OR IGNORE`、不用 JSON1。方言只准在 db.py。
- **寫入皆冪等**:同一份內容寫兩次回同一個 id,`created` 告訴你這次有沒有真的新增
  (匯入器重跑靠它,spec §8 R1)。
- 回傳 dict;JSON 欄位已 decode。
"""
import hashlib
import json
import sqlite3

_JSON_COLS = {"body", "provenance", "anchors", "refs", "quotes"}


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    return {k: json.loads(r[k]) if k in _JSON_COLS else r[k] for k in r.keys()}


def _id(conn, sql, args) -> int | None:
    r = conn.execute(sql, args).fetchone()
    return r[0] if r else None


# ── story / source_version ──

def ensure_story(conn, slug: str, title: str | None, now: float) -> int:
    conn.execute("INSERT INTO story (slug, title, created_at) VALUES (?, ?, ?) "
                 "ON CONFLICT (slug) DO NOTHING", (slug, title, now))
    if title is not None:
        conn.execute("UPDATE story SET title = ? WHERE slug = ?", (title, slug))
    return _id(conn, "SELECT id FROM story WHERE slug = ?", (slug,))


def story_by_slug(conn, slug: str) -> dict | None:
    return _row(conn.execute("SELECT * FROM story WHERE slug = ?", (slug,)).fetchone())


def add_source_version(conn, story_id: int, text: str, now: float) -> tuple[int, bool]:
    """只跟**最新一版**比:相同回 (舊 id, False);不同就是新的一版——
    包括改回更早的稿(A→B→A 的第三次是 n=3,不是 n=1),否則「最新版」會指向磁碟上已不存在的文字。"""
    digest = sha256_text(text)
    latest = latest_source_version(conn, story_id)
    if latest is not None and latest["sha256"] == digest:
        return latest["id"], False
    n = (latest["n"] if latest else 0) + 1
    cur = conn.execute("INSERT INTO source_version (story_id, n, text, sha256, created_at) "
                       "VALUES (?, ?, ?, ?, ?)", (story_id, n, text, digest, now))
    return cur.lastrowid, True


def latest_source_version(conn, story_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM source_version WHERE story_id = ? "
                             "ORDER BY n DESC LIMIT 1", (story_id,)).fetchone())


# ── artifact / current ──

def add_artifact(conn, story_id: int, source_version_id: int, kind: str, schema_version: int,
                 body: dict, provenance: dict, now: float) -> tuple[int, bool]:
    text = canonical_json(body)
    digest = sha256_text(text)
    old = _id(conn, "SELECT id FROM artifact WHERE story_id = ? AND kind = ? AND sha256 = ?",
              (story_id, kind, digest))
    if old is not None:
        return old, False
    cur = conn.execute(
        "INSERT INTO artifact (story_id, source_version_id, kind, schema_version, body, sha256, "
        "provenance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (story_id, source_version_id, kind, schema_version, text, digest,
         canonical_json(provenance), now))
    return cur.lastrowid, True


def set_current(conn, story_id: int, kind: str, artifact_id: int) -> None:
    conn.execute("INSERT INTO current_artifact (story_id, kind, artifact_id) VALUES (?, ?, ?) "
                 "ON CONFLICT (story_id, kind) DO UPDATE SET artifact_id = excluded.artifact_id",
                 (story_id, kind, artifact_id))


def current_artifact(conn, story_id: int, kind: str) -> dict | None:
    return _row(conn.execute(
        "SELECT a.* FROM current_artifact c JOIN artifact a ON a.id = c.artifact_id "
        "WHERE c.story_id = ? AND c.kind = ?", (story_id, kind)).fetchone())


# ── discussion / utterance ──

def ensure_discussion(conn, story_id: int, external_id: str, home: str, client: str | None,
                      started_at: float) -> int:
    conn.execute("INSERT INTO discussion (story_id, external_id, home, client, started_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (story_id, external_id) DO NOTHING",
                 (story_id, external_id, home, client, started_at))
    return _id(conn, "SELECT id FROM discussion WHERE story_id = ? AND external_id = ?",
               (story_id, external_id))


def close_discussion(conn, discussion_id: int, ended_at: float) -> None:
    conn.execute("UPDATE discussion SET ended_at = ? WHERE id = ? "
                 "AND (ended_at IS NULL OR ended_at < ?)", (ended_at, discussion_id, ended_at))


def add_utterance(conn, discussion_id: int, seq: int, role: str, text: str, ts: float,
                  origin: str, anchors: list[str], analysis_fp: str | None) -> bool:
    cur = conn.execute(
        "INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors, analysis_fp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (discussion_id, seq) DO NOTHING",
        (discussion_id, seq, role, text, ts, origin, canonical_json(anchors), analysis_fp))
    return cur.rowcount == 1


def utterances(conn, discussion_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM utterance WHERE discussion_id = ? ORDER BY seq", (discussion_id,))]


# ── conclusion / settlement ──

def add_conclusion(conn, story_id: int, external_id: str, discussion_id: int | None, kind: str,
                   text: str, refs: list, quotes: list, provenance: dict, valid_from: float,
                   invalidated_at: float | None) -> bool:
    cur = conn.execute(
        "INSERT INTO conclusion (story_id, external_id, discussion_id, kind, text, refs, quotes, "
        "provenance, valid_from, invalidated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (story_id, external_id) DO NOTHING",
        (story_id, external_id, discussion_id, kind, text, canonical_json(refs),
         canonical_json(quotes), canonical_json(provenance), valid_from, invalidated_at))
    return cur.rowcount == 1


def conclusions(conn, story_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM conclusion WHERE story_id = ? ORDER BY valid_from", (story_id,))]


def add_settlement(conn, discussion_id: int, settled_at: float, written: int) -> bool:
    cur = conn.execute("INSERT INTO settlement (discussion_id, settled_at, written) "
                       "VALUES (?, ?, ?) ON CONFLICT (discussion_id) DO NOTHING",
                       (discussion_id, settled_at, written))
    return cur.rowcount == 1
