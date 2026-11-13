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
import re
import sqlite3

_JSON_COLS = {"card", "recipe", "body", "provenance", "anchors", "refs", "quotes",
              "params", "detail", "parsed", "gate_verdict", "tokens", "usage"}


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    return {k: json.loads(r[k]) if k in _JSON_COLS and r[k] is not None else r[k]
            for k in r.keys()}


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


def next_den_slug(conn) -> str:
    """den 建的故事用 d01, d02…:掃 `^d(\\d+)$` 最大值 +1。只看 d 前綴,舊 web 的 sNN 不影響。"""
    nums = [int(m.group(1)) for (slug,) in conn.execute("SELECT slug FROM story")
            if (m := re.fullmatch(r"d(\d+)", slug))]
    return f"d{(max(nums) + 1) if nums else 1:02d}"


def story_by_latest_sha(conn, sha256: str) -> dict | None:
    """「最新版」source_version 的 sha 等於它的那篇;舊版吻合不算(改稿後舊稿不該認回來)。"""
    return _row(conn.execute(
        "SELECT st.* FROM story st JOIN source_version sv ON sv.story_id = st.id "
        "WHERE sv.sha256 = ? AND sv.n = (SELECT MAX(n) FROM source_version WHERE story_id = st.id) "
        "ORDER BY st.id LIMIT 1", (sha256,)).fetchone())


def story(conn, story_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM story WHERE id = ?", (story_id,)).fetchone())


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


def source_versions(conn, story_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM source_version WHERE story_id = ? ORDER BY n", (story_id,)).fetchall()]


def source_version_by_n(conn, story_id: int, n: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM source_version WHERE story_id = ? AND n = ?",
                             (story_id, n)).fetchone())


def source_version(conn, source_version_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM source_version WHERE id = ?",
                             (source_version_id,)).fetchone())


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

def ensure_discussion(conn, story_id: int | None, external_id: str, home: str, client: str | None,
                      started_at: float) -> int:
    conn.execute("INSERT INTO discussion (story_id, external_id, home, client, started_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (external_id) DO NOTHING",
                 (story_id, external_id, home, client, started_at))
    row = conn.execute("SELECT id, story_id FROM discussion WHERE external_id = ?", (external_id,)).fetchone()
    if row["story_id"] != story_id:
        raise ValueError(f"session {external_id} belongs to another story")
    return row["id"]


def discussion_by_session(conn, external_id: str) -> dict | None:
    return _row(conn.execute("SELECT d.*, st.slug AS slug FROM discussion d LEFT JOIN story st "
                             "ON st.id = d.story_id WHERE d.external_id = ?", (external_id,)).fetchone())


def bind_discussion(conn, discussion_id: int, story_id: int) -> None:
    conn.execute("UPDATE discussion SET story_id = ? WHERE id = ? AND story_id IS NULL",
                 (story_id, discussion_id))


def add_attachment(conn, discussion_id: int, seq: int, name: str, text: str, now: float) -> int:
    n = conn.execute("SELECT COUNT(*) FROM attachment WHERE discussion_id = ?", (discussion_id,)).fetchone()[0] + 1
    conn.execute("INSERT INTO attachment (discussion_id, n, seq, name, text, sha256, added_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", (discussion_id, n, seq, name, text, sha256_text(text), now))
    return n


def attachments(conn, discussion_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT n, seq, name, text, sha256, added_at, source_version_id FROM attachment "
        "WHERE discussion_id = ? ORDER BY n", (discussion_id,))]


def adopt_attachment(conn, discussion_id: int, n: int, source_version_id: int) -> None:
    conn.execute("UPDATE attachment SET source_version_id = ? WHERE discussion_id = ? AND n = ?",
                 (source_version_id, discussion_id, n))


def close_discussion(conn, discussion_id: int, ended_at: float) -> None:
    conn.execute("UPDATE discussion SET ended_at = ? WHERE id = ? "
                 "AND (ended_at IS NULL OR ended_at < ?)", (ended_at, discussion_id, ended_at))


def add_utterance(conn, discussion_id: int, seq: int, role: str, text: str, ts: float,
                  origin: str, anchors: list[str], analysis_fp: str | None,
                  *, usage: dict | None = None,
                  character: str | None = None, quotes: list[str] | None = None,
                  recipe: dict | None = None) -> bool:
    cur = conn.execute(
        "INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors, analysis_fp, "
        "usage, character, quotes, recipe) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (discussion_id, seq) DO NOTHING",
        (discussion_id, seq, role, text, ts, origin, canonical_json(anchors), analysis_fp,
         None if usage is None else canonical_json(usage), character,
         canonical_json(quotes) if quotes else None,
         None if recipe is None else canonical_json(recipe)))
    return cur.rowcount == 1


def last_character(conn, discussion_id: int) -> str | None:
    """該局最後一筆有記角色的 assistant 發言是誰說的(舊局沒有 → None)。"""
    r = conn.execute("SELECT character FROM utterance WHERE discussion_id = ? AND role = 'assistant' "
                     "AND character IS NOT NULL ORDER BY seq DESC LIMIT 1", (discussion_id,)).fetchone()
    return r[0] if r else None


def utterance(conn, discussion_id: int, seq: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM utterance WHERE discussion_id = ? AND seq = ?",
                             (discussion_id, seq)).fetchone())


_CUR = "(SELECT variant FROM utterance WHERE discussion_id = ? AND seq = ?)"
_VERSION_COLS = ("text", "ts", "usage", "recipe", "analysis_fp", "edited_at")


def set_reaction(conn, discussion_id: int, seq: int, mark: str, comment: str | None, now: float) -> None:
    conn.execute("INSERT INTO reaction (discussion_id, seq, variant, mark, comment, updated_at) "
                 f"VALUES (?, ?, {_CUR}, ?, ?, ?) "
                 "ON CONFLICT (discussion_id, seq, variant) DO UPDATE SET mark = excluded.mark, "
                 "comment = excluded.comment, updated_at = excluded.updated_at",
                 (discussion_id, seq, discussion_id, seq, mark, comment, now))


def clear_reaction(conn, discussion_id: int, seq: int) -> None:
    conn.execute(f"DELETE FROM reaction WHERE discussion_id = ? AND seq = ? AND variant = {_CUR}",
                 (discussion_id, seq, discussion_id, seq))


def reactions(conn, discussion_id: int) -> dict[int, dict]:
    return {r["seq"]: {"mark": r["mark"], "comment": r["comment"]} for r in conn.execute(
        "SELECT r.seq AS seq, r.mark AS mark, r.comment AS comment FROM reaction r JOIN utterance u "
        "ON u.discussion_id = r.discussion_id AND u.seq = r.seq AND u.variant = r.variant "
        "WHERE r.discussion_id = ?", (discussion_id,))}


def set_voice(conn, discussion_id: int, seq: int, now: float) -> None:
    conn.execute(f"INSERT INTO voice_mark (discussion_id, seq, variant, marked_at) VALUES (?, ?, {_CUR}, ?) "
                 "ON CONFLICT (discussion_id, seq, variant) DO NOTHING",
                 (discussion_id, seq, discussion_id, seq, now))


def clear_voice(conn, discussion_id: int, seq: int) -> None:
    conn.execute(f"DELETE FROM voice_mark WHERE discussion_id = ? AND seq = ? AND variant = {_CUR}",
                 (discussion_id, seq, discussion_id, seq))


def voice_marks(conn, discussion_id: int) -> set[int]:
    return {r[0] for r in conn.execute(
        "SELECT v.seq FROM voice_mark v JOIN utterance u ON u.discussion_id = v.discussion_id "
        "AND u.seq = v.seq AND u.variant = v.variant WHERE v.discussion_id = ?", (discussion_id,))}


def variant_counts(conn, discussion_id: int) -> dict[int, int]:
    return {r[0]: r[1] + 1 for r in conn.execute(
        "SELECT seq, COUNT(*) FROM utterance_variant WHERE discussion_id = ? GROUP BY seq", (discussion_id,))}


def _encoded(version: dict) -> tuple:
    return tuple(None if version[k] is None else canonical_json(version[k]) if k in ("usage", "recipe")
                 else version[k] for k in _VERSION_COLS)


def _shelve(conn, discussion_id: int, seq: int, current: dict) -> None:
    conn.execute(f"INSERT INTO utterance_variant (discussion_id, seq, n, {', '.join(_VERSION_COLS)}) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (discussion_id, seq, current["variant"], *_encoded(current)))


def _install(conn, discussion_id: int, seq: int, n: int, version: dict) -> None:
    conn.execute(f"UPDATE utterance SET variant = ?, {', '.join(f'{k} = ?' for k in _VERSION_COLS)} "
                 "WHERE discussion_id = ? AND seq = ?", (n, *_encoded(version), discussion_id, seq))


def replace_reply(conn, discussion_id: int, seq: int, *, text: str, ts: float, usage: dict | None,
                  recipe: dict | None, analysis_fp: str | None) -> int:
    current = utterance(conn, discussion_id, seq)
    shelved = conn.execute("SELECT MAX(n) FROM utterance_variant WHERE discussion_id = ? AND seq = ?",
                           (discussion_id, seq)).fetchone()[0]
    n = 1 + max(current["variant"], shelved or 0)
    _shelve(conn, discussion_id, seq, current)
    _install(conn, discussion_id, seq, n, {"text": text, "ts": ts, "usage": usage, "recipe": recipe,
                                           "analysis_fp": analysis_fp, "edited_at": None})
    return n


def pick_reply(conn, discussion_id: int, seq: int, n: int) -> bool:
    current = utterance(conn, discussion_id, seq)
    if current["variant"] == n:
        return True
    row = _row(conn.execute("SELECT * FROM utterance_variant WHERE discussion_id = ? AND seq = ? AND n = ?",
                            (discussion_id, seq, n)).fetchone())
    if row is None:
        return False
    conn.execute("DELETE FROM utterance_variant WHERE discussion_id = ? AND seq = ? AND n = ?",
                 (discussion_id, seq, n))
    _shelve(conn, discussion_id, seq, current)
    _install(conn, discussion_id, seq, n, row)
    return True


def edit_reply(conn, discussion_id: int, seq: int, text: str, now: float) -> bool:
    cur = conn.execute("UPDATE utterance SET text = ?, edited_at = ? WHERE discussion_id = ? AND seq = ? "
                       "AND text <> ?", (text, now, discussion_id, seq, text))
    return cur.rowcount == 1


def voice_samples(conn, character: str, exclude_discussion: int | None) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT u.text AS text, p.text AS prompt, d.story_id AS story_id, v.marked_at AS marked_at "
        "FROM voice_mark v JOIN utterance u ON u.discussion_id = v.discussion_id AND u.seq = v.seq "
        "AND u.variant = v.variant JOIN discussion d ON d.id = v.discussion_id "
        "LEFT JOIN utterance p ON p.discussion_id = u.discussion_id AND p.seq = u.seq - 1 AND p.role = 'user' "
        "WHERE u.character = ? AND u.role = 'assistant' AND v.discussion_id IS NOT ? "
        "ORDER BY v.marked_at DESC, v.discussion_id DESC, v.seq DESC", (character, exclude_discussion))]


def utterances(conn, discussion_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM utterance WHERE discussion_id = ? ORDER BY seq", (discussion_id,))]


def discussions_with_utterances(conn, story_id: int, archived: bool = True) -> list[dict]:
    """一篇所有討論局的逐字,依 ts, seq 排;一次查完。archived=False 不含封存的局。"""
    hide = "" if archived else "AND d.archived_at IS NULL "
    return [_row(r) for r in conn.execute(
        "SELECT d.external_id AS external_id, u.seq AS seq, u.role AS role, u.text AS text, "
        "u.ts AS ts, u.anchors AS anchors, u.character AS character, "
        "u.quotes AS quotes, u.analysis_fp AS analysis_fp FROM utterance u JOIN discussion d "
        "ON d.id = u.discussion_id WHERE d.story_id = ? AND u.role IN ('user', 'assistant') "
        + hide + "ORDER BY u.ts, u.seq", (story_id,))]


def analysis_versions(conn, story_id: int) -> dict[str, int]:
    """一篇所有 analysis artifact:sha256(= 發言的 analysis_fp)→ 它對的原文版本 n;一次查完。"""
    return {r["sha256"]: r["n"] for r in conn.execute(
        "SELECT a.sha256 AS sha256, sv.n AS n FROM artifact a JOIN source_version sv "
        "ON sv.id = a.source_version_id WHERE a.story_id = ? AND a.kind = 'analysis'", (story_id,))}


def analysis_bodies(conn, story_id: int) -> dict[str, dict]:
    return {r["sha256"]: json.loads(r["body"]) for r in conn.execute(
        "SELECT sha256, body FROM artifact WHERE story_id = ? AND kind = 'analysis'", (story_id,))}


def artifact_versions(conn, story_id: int, kind: str) -> set[int]:
    """一篇所有 kind artifact 對的原文版本 n(不論 current)。"""
    return {r["n"] for r in conn.execute(
        "SELECT DISTINCT sv.n AS n FROM artifact a JOIN source_version sv ON sv.id = a.source_version_id "
        "WHERE a.story_id = ? AND a.kind = ?", (story_id, kind))}


def recent_discussions(conn, limit: int, legacy: bool = False) -> list[dict]:
    """跨作品最近的局(有發言才算),依最後發言時間新到舊;一次查完。
    turns = assistant 則數;character / preview / fp 取最後一則 assistant 發言(preview 不截,換標籤後由 views 截)。
    legacy = 沒有任何記了 character 的 assistant 發言(改版前的舊局);只回 legacy 或只回非 legacy,過濾在 LIMIT 之前。"""
    last = ("(SELECT {c} FROM utterance WHERE discussion_id = d.id AND role = 'assistant' "
            "ORDER BY seq DESC LIMIT 1)")
    out = []
    for r in conn.execute(
            "SELECT d.external_id AS external_id, st.slug AS slug, st.title AS title, "
            "d.started_at AS started_at, "
            "(SELECT MAX(ts) FROM utterance WHERE discussion_id = d.id) AS last_at, "
            "(SELECT COUNT(*) FROM utterance WHERE discussion_id = d.id AND role = 'assistant') AS turns, "
            f"{last.format(c='character')} AS character, "
            f"{last.format(c='text')} AS preview, "
            f"{last.format(c='analysis_fp')} AS fp, d.story_id AS story_id "
            "FROM discussion d LEFT JOIN story st ON st.id = d.story_id "
            "WHERE d.archived_at IS NULL AND EXISTS (SELECT 1 FROM utterance WHERE discussion_id = d.id) "
            f"AND {'NOT ' if legacy else ''}EXISTS (SELECT 1 FROM utterance WHERE discussion_id = d.id "
            "AND role = 'assistant' AND character IS NOT NULL) "
            "ORDER BY last_at DESC, d.id DESC LIMIT ?", (limit,)):
        row = _row(r)
        row["preview"] = row["preview"] or ""
        out.append(row)
    return out


def archive_discussion(conn, discussion_id: int, now: float) -> None:
    conn.execute("UPDATE discussion SET archived_at = ? WHERE id = ? AND archived_at IS NULL", (now, discussion_id))


def unarchive_discussion(conn, discussion_id: int) -> None:
    conn.execute("UPDATE discussion SET archived_at = NULL WHERE id = ?", (discussion_id,))


def archived_discussions(conn) -> list[dict]:
    """封存的局,新封存的在上;preview = 第一句話前 60 字。"""
    out = []
    for r in conn.execute(
            "SELECT d.external_id AS external_id, st.slug AS slug, st.title AS title, d.archived_at AS archived_at, "
            "(SELECT MAX(ts) FROM utterance WHERE discussion_id = d.id) AS last_at, "
            "(SELECT text FROM utterance WHERE discussion_id = d.id AND role IN ('user', 'assistant') "
            "ORDER BY seq LIMIT 1) AS preview "
            "FROM discussion d LEFT JOIN story st ON st.id = d.story_id "
            "WHERE d.archived_at IS NOT NULL ORDER BY d.archived_at DESC, d.id DESC"):
        row = _row(r)
        row["preview"] = (row["preview"] or "")[:60]
        out.append(row)
    return out


def delete_discussion(conn, discussion_id: int) -> None:
    """永久刪掉一局:逐字(含擱著的版本)、附件、回饋記號、「像它」、收束紀錄;記憶與結論留著,只斷開來源。"""
    conn.execute("UPDATE memory SET quote = NULL, discussion_id = NULL, seq = NULL WHERE discussion_id = ?",
                 (discussion_id,))
    conn.execute("UPDATE conclusion SET discussion_id = NULL WHERE discussion_id = ?", (discussion_id,))
    for table in ("reaction", "voice_mark", "utterance_variant", "attachment", "settlement", "utterance"):
        conn.execute(f"DELETE FROM {table} WHERE discussion_id = ?", (discussion_id,))
    conn.execute("DELETE FROM discussion WHERE id = ?", (discussion_id,))


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


def set_conclusion_artifact(conn, story_id: int, external_id: str, artifact_id: int) -> None:
    """回填結論當時對照的 analysis artifact;只在尚未記錄時寫(已有的不被覆蓋)。"""
    conn.execute("UPDATE conclusion SET analysis_artifact_id = ? WHERE story_id = ? "
                 "AND external_id = ? AND analysis_artifact_id IS NULL",
                 (artifact_id, story_id, external_id))


def add_settlement(conn, discussion_id: int, settled_at: float, written: int) -> bool:
    cur = conn.execute("INSERT INTO settlement (discussion_id, settled_at, written) "
                       "VALUES (?, ?, ?) ON CONFLICT (discussion_id) DO NOTHING",
                       (discussion_id, settled_at, written))
    return cur.rowcount == 1


# ── memory ──

_MEMORY_JOINED = ("SELECT m.*, d.external_id AS session, st.id AS work_id, st.slug AS slug, st.title AS title FROM memory m "
                  "LEFT JOIN discussion d ON d.id = m.discussion_id "
                  "LEFT JOIN story st ON st.id = COALESCE(m.story_id, d.story_id)")


def add_memory(conn, scope: str, text: str, now: float, *, story_id: int | None = None,
               character: str | None = None, quote: str | None = None,
               discussion_id: int | None = None, seq: int | None = None,
               valid_from: float | None = None, root_id: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO memory (root_id, scope, story_id, character, text, quote, discussion_id, seq, "
        "valid_from, learned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (root_id, scope, story_id, character, text, quote, discussion_id, seq,
         now if valid_from is None else valid_from, now))
    return cur.lastrowid


def memory(conn, memory_id: int) -> dict | None:
    return _row(conn.execute(f"{_MEMORY_JOINED} WHERE m.id = ?", (memory_id,)).fetchone())


def active_memories(conn, scope: str, story_id: int | None = None) -> list[dict]:
    where = "story_id IS NULL" if story_id is None else "story_id = ?"
    args = (scope,) if story_id is None else (scope, story_id)
    return [_row(r) for r in conn.execute(
        f"SELECT * FROM memory WHERE scope = ? AND {where} AND invalidated_at IS NULL ORDER BY id", args)]


def current_in_chain(conn, root_id: int) -> dict | None:
    return _row(conn.execute(
        "SELECT * FROM memory WHERE COALESCE(root_id, id) = ? AND invalidated_at IS NULL",
        (root_id,)).fetchone())


def invalidate_memory(conn, memory_id: int, now: float) -> None:
    conn.execute("UPDATE memory SET invalidated_at = ? WHERE id = ?", (now, memory_id))


def all_memories(conn) -> list[dict]:
    return [_row(r) for r in conn.execute(f"{_MEMORY_JOINED} ORDER BY COALESCE(m.root_id, m.id), m.id")]


def memories_of_discussion(conn, discussion_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM memory WHERE discussion_id = ? AND invalidated_at IS NULL ORDER BY id",
        (discussion_id,))]


# ── 列表用批次查詢(固定次數,不隨篇數成長) ──

def stories(conn) -> list[dict]:
    return [_row(r) for r in conn.execute("SELECT * FROM story ORDER BY slug")]


def works(conn) -> list[dict]:
    """每篇一列:最新版(id / n / 原文 / 交稿時間)與最近一次聊天的結束時間(沒聊過 = None)。"""
    return [_row(r) for r in conn.execute(
        "SELECT st.id, st.slug, st.title, sv.id AS latest_sv_id, sv.n AS latest_n, "
        "sv.text AS latest_text, sv.created_at AS submitted_at, "
        "(SELECT MAX(ended_at) FROM discussion WHERE story_id = st.id) AS talked_at "
        "FROM story st JOIN source_version sv ON sv.story_id = st.id "
        "AND sv.n = (SELECT MAX(n) FROM source_version WHERE story_id = st.id) ORDER BY st.slug")]


def activity_times(conn) -> dict[int, float]:
    """story_id → 最新 analysis/notes artifact 建立時間與最新 assistant 發言時間取大者(都沒有就沒這個 key)。"""
    out: dict[int, float] = {}
    for r in conn.execute(
            "SELECT story_id, MAX(created_at) AS t FROM artifact WHERE kind IN ('analysis', 'notes') "
            "GROUP BY story_id"):
        out[r["story_id"]] = r["t"]
    for r in conn.execute(
            "SELECT d.story_id AS story_id, MAX(u.ts) AS t FROM utterance u "
            "JOIN discussion d ON d.id = u.discussion_id WHERE u.role = 'assistant' AND d.story_id IS NOT NULL "
            "GROUP BY d.story_id"):
        out[r["story_id"]] = max(out.get(r["story_id"], 0.0), r["t"])
    return out


def current_artifacts(conn) -> list[dict]:
    """所有篇的 current:`{story_id, kind, artifact}`,一次查完。"""
    out = []
    for r in conn.execute(
            "SELECT c.story_id AS cur_story_id, c.kind AS cur_kind, a.* FROM current_artifact c "
            "JOIN artifact a ON a.id = c.artifact_id"):
        art = _row(r)
        out.append({"story_id": art.pop("cur_story_id"), "kind": art.pop("cur_kind"),
                    "artifact": art})
    return out


def latest_jobs(conn) -> dict[int, dict]:
    """story_id → 該篇 id 最大的 job。"""
    return {r["story_id"]: _row(r) for r in conn.execute(
        "SELECT j.* FROM job j WHERE j.story_id IS NOT NULL "
        "AND j.id = (SELECT MAX(id) FROM job WHERE story_id = j.story_id)")}


# ── artifact 單筆 ──

def artifact(conn, artifact_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM artifact WHERE id = ?", (artifact_id,)).fetchone())


# ── job / attempt ──
# 狀態:queued | running | paused | failed | done | cancelled。可續 = paused | failed | cancelled
# (取消過的也要有出口,#22)。

_RESUMABLE = ("paused", "failed", "cancelled")


def create_job(conn, kind: str, story_id: int, source_version_id: int, params: dict,
               now: float) -> int:
    cur = conn.execute(
        "INSERT INTO job (kind, story_id, source_version_id, state, params, created_at, updated_at) "
        "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
        (kind, story_id, source_version_id, canonical_json(params), now, now))
    return cur.lastrowid


def get_job(conn, job_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone())


def claim_next_job(conn, now: float) -> dict | None:
    """最舊的 queued 改 running 並回傳;呼叫者在 `with conn:` 內呼叫。

    假設只有單一 claimer(一個 worker + daemon 檔案鎖);SELECT 與 UPDATE 之間沒有防併發。
    """
    jid = _id(conn, "SELECT id FROM job WHERE state = 'queued' ORDER BY id LIMIT 1", ())
    if jid is None:
        return None
    conn.execute("UPDATE job SET state = 'running', updated_at = ? WHERE id = ?", (now, jid))
    return get_job(conn, jid)


def set_job_state(conn, job_id: int, state: str, now: float, step: str | None = None,
                  error_class: str | None = None, detail: dict | None = None) -> None:
    """改 job 狀態。省略 error_class / detail = 清成 NULL;省略 step = 保留原值。"""
    conn.execute(
        "UPDATE job SET state = ?, step = COALESCE(?, step), error_class = ?, detail = ?, "
        "updated_at = ? WHERE id = ?",
        (state, step, error_class, None if detail is None else canonical_json(detail), now, job_id))


def requeue_job(conn, job_id: int, now: float) -> bool:
    cur = conn.execute(
        "UPDATE job SET state = 'queued', error_class = NULL, detail = NULL, updated_at = ? "
        "WHERE id = ? AND state IN (?, ?, ?)", (now, job_id, *_RESUMABLE))
    return cur.rowcount == 1


def recover_running_jobs(conn, now: float) -> list[int]:
    """daemon 啟動時呼叫:上次沒收尾的 running 一律視為 crash。"""
    ids = [r[0] for r in conn.execute("SELECT id FROM job WHERE state = 'running' ORDER BY id")]
    for jid in ids:
        set_job_state(conn, jid, "failed", now, error_class="crash")
    return ids


def add_attempt(conn, job_id: int, step: str, n: int, *, runner: str, model: str | None,
                cli_version: str | None, outcome: str, raw_output: str | None,
                parsed: dict | None, gate_verdict: dict | None, tokens: dict | None,
                duration_ms: int | None, artifact_id: int | None, now: float,
                prompt_sha: str | None = None, recipe: dict | None = None) -> int:
    def j(o):
        return None if o is None else canonical_json(o)
    cur = conn.execute(
        "INSERT INTO attempt (job_id, step, n, runner, model, cli_version, outcome, raw_output, "
        "parsed, gate_verdict, tokens, duration_ms, artifact_id, created_at, prompt_sha, recipe) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, step, n, runner, model, cli_version, outcome, raw_output, j(parsed),
         j(gate_verdict), j(tokens), duration_ms, artifact_id, now, prompt_sha, j(recipe)))
    return cur.lastrowid


def attempts(conn, job_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM attempt WHERE job_id = ? ORDER BY id", (job_id,))]


def ok_attempt(conn, job_id: int, step: str) -> dict | None:
    """該 job 該步 outcome=ok 的那筆(續跑判定用)。"""
    return _row(conn.execute(
        "SELECT * FROM attempt WHERE job_id = ? AND step = ? AND outcome = 'ok' "
        "ORDER BY id LIMIT 1", (job_id, step)).fetchone())


def attempt_history(conn, step: str) -> list[dict]:
    """所有成功 attempt 的 {chars, duration_ms, tokens}(chars = 該 job 原文長度)。
    prompt_sha NULL = 舊 --json-schema 配方的樣本,不代表現行速度,排除。"""
    return [_row(r) for r in conn.execute(
        "SELECT LENGTH(sv.text) AS chars, a.duration_ms AS duration_ms, a.tokens AS tokens "
        "FROM attempt a JOIN job j ON j.id = a.job_id "
        "JOIN source_version sv ON sv.id = j.source_version_id "
        "WHERE a.step = ? AND a.outcome = 'ok' AND a.prompt_sha IS NOT NULL "
        "ORDER BY a.id", (step,))]


def has_pending_jobs(conn) -> bool:
    return conn.execute("SELECT 1 FROM job WHERE state IN ('queued', 'running') LIMIT 1"
                        ).fetchone() is not None


def active_job(conn, story_id: int, source_version_id: int) -> dict | None:
    """同篇同版還在排隊 / 執行中的最舊 job(重送去重用:同一份原文不該花兩次錢)。"""
    return _row(conn.execute(
        "SELECT * FROM job WHERE story_id = ? AND source_version_id = ? "
        "AND state IN ('queued', 'running') ORDER BY id LIMIT 1",
        (story_id, source_version_id)).fetchone())


def list_jobs(conn, limit: int) -> list[dict]:
    """最近的 job(updated_at DESC, id DESC)取 limit 筆,附 story 的 slug、title,
    與 is_latest_version(這個 job 的原文是不是該篇最新版;舊版不能續跑)。"""
    rows = [_row(r) for r in conn.execute(
        "SELECT j.*, st.slug AS slug, st.title AS title, "
        "CASE WHEN j.source_version_id = (SELECT id FROM source_version "
        "WHERE story_id = j.story_id ORDER BY n DESC LIMIT 1) THEN 1 ELSE 0 END "
        "AS is_latest_version FROM job j JOIN story st ON st.id = j.story_id "
        "ORDER BY j.updated_at DESC, j.id DESC LIMIT ?", (limit,))]
    for r in rows:
        r["is_latest_version"] = bool(r["is_latest_version"])
    return rows


def latest_job(conn, story_id: int, source_version_id: int) -> dict | None:
    """同篇同版 id 最大的 job(companion 素材的進度用)。"""
    return _row(conn.execute(
        "SELECT * FROM job WHERE story_id = ? AND source_version_id = ? ORDER BY id DESC LIMIT 1",
        (story_id, source_version_id)).fetchone())


def has_newer_done_job(conn, story_id: int, source_version_id: int, job_id: int) -> bool:
    """同篇同版有 id 比 job_id 大、已 done 的 job(這個 job 已被後來跑完的取代)。
    較早的 done 不算:跑完後明確重跑的 job 停在半路仍要能續。"""
    return conn.execute(
        "SELECT 1 FROM job WHERE story_id = ? AND source_version_id = ? AND id > ? "
        "AND state = 'done' LIMIT 1", (story_id, source_version_id, job_id)).fetchone() is not None


def active_jobs_of_story(conn, story_id: int) -> list[dict]:
    """該篇任何版本還在排隊 / 執行中的 job(依作品取消用)。"""
    return [_row(r) for r in conn.execute(
        "SELECT * FROM job WHERE story_id = ? AND state IN ('queued', 'running') ORDER BY id",
        (story_id,))]


def resumable_job(conn, story_id: int, source_version_id: int) -> dict | None:
    """同篇同版可續(paused/failed/cancelled)的最新 job(重送自動續跑用:已付的步驟不重花)。"""
    return _row(conn.execute(
        "SELECT * FROM job WHERE story_id = ? AND source_version_id = ? "
        "AND state IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        (story_id, source_version_id, *_RESUMABLE)).fetchone())


def has_newer_resumable_job(conn, story_id: int, source_version_id: int, job_id: int) -> bool:
    """同篇同版有 id 比 job_id 大、可續(paused/failed/cancelled)的 job:續舊的會跟新的重複花錢。"""
    return conn.execute(
        "SELECT 1 FROM job WHERE story_id = ? AND source_version_id = ? AND id > ? "
        "AND state IN (?, ?, ?) LIMIT 1",
        (story_id, source_version_id, job_id, *_RESUMABLE)).fetchone() is not None


# ── character / setting ──

_LATEST_CHARACTER = ("SELECT c.id AS id, c.origin AS origin, c.archived_at AS archived_at, v.n AS n, "
                     "v.card AS card, v.sha256 AS sha256 FROM character c JOIN character_version v "
                     "ON v.character_id = c.id AND v.n = (SELECT MAX(n) FROM character_version "
                     "WHERE character_id = c.id) ")


def add_character(conn, character_id: str, origin: str, now: float) -> None:
    conn.execute("INSERT INTO character (id, origin, created_at) VALUES (?, ?, ?)", (character_id, origin, now))


def add_character_version(conn, character_id: str, card: dict, now: float) -> int:
    text = canonical_json(card)
    n = conn.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM character_version WHERE character_id = ?",
                     (character_id,)).fetchone()[0]
    conn.execute("INSERT INTO character_version (character_id, n, card, sha256, created_at) VALUES (?, ?, ?, ?, ?)",
                 (character_id, n, text, sha256_text(text), now))
    return n


def latest_character(conn, character_id: str) -> dict | None:
    return _row(conn.execute(_LATEST_CHARACTER + "WHERE c.id = ?", (character_id,)).fetchone())


def latest_characters(conn) -> list[dict]:
    return [_row(r) for r in conn.execute(_LATEST_CHARACTER + "ORDER BY c.created_at, c.id")]


def archive_character(conn, character_id: str, now: float) -> None:
    conn.execute("UPDATE character SET archived_at = ? WHERE id = ? AND archived_at IS NULL", (now, character_id))


def unarchive_character(conn, character_id: str) -> None:
    conn.execute("UPDATE character SET archived_at = NULL WHERE id = ?", (character_id,))


def get_setting(conn, key: str) -> str | None:
    r = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return r[0] if r else None


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO setting (key, value) VALUES (?, ?) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
