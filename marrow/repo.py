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

_JSON_COLS = {"body", "provenance", "anchors", "refs", "quotes",
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

def ensure_discussion(conn, story_id: int, external_id: str, home: str, client: str | None,
                      started_at: float) -> int:
    conn.execute("INSERT INTO discussion (story_id, external_id, home, client, started_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (story_id, external_id) DO NOTHING",
                 (story_id, external_id, home, client, started_at))
    return _id(conn, "SELECT id FROM discussion WHERE story_id = ? AND external_id = ?",
               (story_id, external_id))


def discussion_by_external(conn, story_id: int, external_id: str) -> dict | None:
    """依 (story, external_id) 找局;web 聊天端靠它把 session id 對回既有的局。"""
    return _row(conn.execute("SELECT * FROM discussion WHERE story_id = ? AND external_id = ?",
                             (story_id, external_id)).fetchone())


def close_discussion(conn, discussion_id: int, ended_at: float) -> None:
    conn.execute("UPDATE discussion SET ended_at = ? WHERE id = ? "
                 "AND (ended_at IS NULL OR ended_at < ?)", (ended_at, discussion_id, ended_at))


def add_utterance(conn, discussion_id: int, seq: int, role: str, text: str, ts: float,
                  origin: str, anchors: list[str], analysis_fp: str | None,
                  usage: dict | None = None, mode: str | None = None,
                  character: str | None = None) -> bool:
    cur = conn.execute(
        "INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors, analysis_fp, "
        "usage, mode, character) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (discussion_id, seq) DO NOTHING",
        (discussion_id, seq, role, text, ts, origin, canonical_json(anchors), analysis_fp,
         None if usage is None else canonical_json(usage), mode, character))
    return cur.rowcount == 1


def last_mode(conn, discussion_id: int) -> str | None:
    """該局最後一筆有記模式的 assistant 發言用的模式(舊局沒有 → None)。"""
    r = conn.execute("SELECT mode FROM utterance WHERE discussion_id = ? AND role = 'assistant' "
                     "AND mode IS NOT NULL ORDER BY seq DESC LIMIT 1", (discussion_id,)).fetchone()
    return r[0] if r else None


def last_character(conn, discussion_id: int) -> str | None:
    """該局最後一筆有記角色的 assistant 發言是誰說的(舊局沒有 → None)。"""
    r = conn.execute("SELECT character FROM utterance WHERE discussion_id = ? AND role = 'assistant' "
                     "AND character IS NOT NULL ORDER BY seq DESC LIMIT 1", (discussion_id,)).fetchone()
    return r[0] if r else None


def utterances(conn, discussion_id: int) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM utterance WHERE discussion_id = ? ORDER BY seq", (discussion_id,))]


def discussions_with_utterances(conn, story_id: int) -> list[dict]:
    """一篇所有討論局的逐字,依 ts, seq 排;一次查完。"""
    return [_row(r) for r in conn.execute(
        "SELECT d.external_id AS external_id, u.seq AS seq, u.role AS role, u.text AS text, "
        "u.ts AS ts, u.anchors AS anchors FROM utterance u JOIN discussion d "
        "ON d.id = u.discussion_id WHERE d.story_id = ? ORDER BY u.ts, u.seq", (story_id,))]


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
                prompt_sha: str | None = None) -> int:
    def j(o):
        return None if o is None else canonical_json(o)
    cur = conn.execute(
        "INSERT INTO attempt (job_id, step, n, runner, model, cli_version, outcome, raw_output, "
        "parsed, gate_verdict, tokens, duration_ms, artifact_id, created_at, prompt_sha) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, step, n, runner, model, cli_version, outcome, raw_output, j(parsed),
         j(gate_verdict), j(tokens), duration_ms, artifact_id, now, prompt_sha))
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
