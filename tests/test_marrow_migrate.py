"""marrow.db.migrate:編號 SQL + PRAGMA user_version,升級前備份(spec §8 R6)。"""
import sqlite3

import pytest

from marrow import db

TABLES = {"story", "source_version", "artifact", "current_artifact", "job", "attempt",
          "discussion", "utterance", "conclusion", "settlement"}


_open = []


def _mem():
    c = db.connect("sqlite:///:memory:")
    _open.append(c)
    return c


@pytest.fixture(autouse=True)
def _close_all():
    yield
    while _open:
        _open.pop().close()


def test_fresh_db_gets_all_tables_and_version():
    conn = _mem()
    assert db.migrate(conn, None) == 17
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert TABLES <= names


def test_migrate_is_idempotent():
    conn = _mem()
    db.migrate(conn, None)
    assert db.migrate(conn, None) == 17


def test_upgrade_backs_up_first(tmp_path):
    mig = tmp_path / "mig"
    mig.mkdir()
    (mig / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    p = tmp_path / "h.db"
    conn = db.connect(f"sqlite:///{p}")
    _open.append(conn)
    db.migrate(conn, p, mig)
    assert not list(tmp_path.glob("h.db.bak-*"))            # 全新 DB 不備份
    (mig / "0002_b.sql").write_text("CREATE TABLE b (y INTEGER);")
    assert db.migrate(conn, p, mig) == 2
    old = sqlite3.connect(tmp_path / "h.db.bak-v1")
    _open.append(old)
    assert {r[0] for r in old.execute("SELECT name FROM sqlite_master")} == {"a"}


def test_upgrade_without_path_skips_backup(tmp_path):    # :memory: 沒有檔可備份
    mig = tmp_path / "mig"
    mig.mkdir()
    (mig / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    conn = _mem()
    db.migrate(conn, None, mig)
    (mig / "0002_b.sql").write_text("CREATE TABLE b (y INTEGER);")
    assert db.migrate(conn, None, mig) == 2


@pytest.mark.parametrize("names", [["0001_a.sql", "0003_c.sql"], ["0001_a.sql", "0001_b.sql"]])
def test_migration_numbering_gap_or_dup_rejected(tmp_path, names):
    for n in names:
        (tmp_path / n).write_text("SELECT 1;")
    with pytest.raises(ValueError):
        db.migrate(_mem(), None, tmp_path)


def test_unique_settlement_per_discussion():   # #15 的洞由 DB 約束擋
    conn = _mem()
    db.migrate(conn, None)
    conn.execute("INSERT INTO story VALUES (1,'s','t',0)")
    conn.execute("INSERT INTO discussion (id, story_id, external_id, home, client, started_at, ended_at) VALUES (1,1,'x','web',NULL,0,NULL)")
    conn.execute("INSERT INTO settlement VALUES (1,0,1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO settlement VALUES (1,1,1)")


def test_foreign_keys_enforced():
    conn = _mem()
    db.migrate(conn, None)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO source_version VALUES (1,99,1,'x','h',0)")


def test_failed_migration_leaves_no_partial_state(tmp_path):
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);\nCREATE TABLE a (x INTEGER);")
    conn = _mem()
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(conn, None, tmp_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


def test_leftover_backup_does_not_block_upgrade(tmp_path):                # final review I3
    mig = tmp_path / "mig"
    mig.mkdir()
    (mig / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    p = tmp_path / "h.db"
    conn = db.connect(f"sqlite:///{p}")
    _open.append(conn)
    db.migrate(conn, p, mig)
    (tmp_path / "h.db.bak-v1").write_text("舊的備份")
    (mig / "0002_b.sql").write_text("CREATE TABLE b (y INTEGER);")
    assert db.migrate(conn, p, mig) == 2
    assert (tmp_path / "h.db.bak-v1").read_text() == "舊的備份"          # 不覆蓋既有備份
    assert (tmp_path / "h.db.bak-v1-2").exists()


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v2_db_upgrades_to_prompt_sha_with_backup(tmp_path):     # Task 9e
    mig = tmp_path / "mig"
    mig.mkdir()
    for f in sorted(db.MIGRATIONS_DIR.glob("*.sql"))[:2]:
        (mig / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    p = tmp_path / "h.db"
    conn = db.connect(f"sqlite:///{p}")
    _open.append(conn)
    assert db.migrate(conn, p, mig) == 2
    assert "prompt_sha" not in _cols(conn, "attempt")
    conn.execute("INSERT INTO story VALUES (1,'s','t',0)")
    conn.execute("INSERT INTO job (id, kind, story_id, state, params, created_at, updated_at) "
                 "VALUES (1,'critique',1,'done','{}',0,0)")
    conn.execute("INSERT INTO attempt (job_id, step, n, runner, created_at) "
                 "VALUES (1,'analyst',0,'cli',0)")
    conn.commit()
    assert db.migrate(conn, p) == 17
    assert "prompt_sha" in _cols(conn, "attempt")
    assert conn.execute("SELECT prompt_sha FROM attempt").fetchone()[0] is None
    assert (tmp_path / "h.db.bak-v2").exists()


def test_0012_backfills_character_then_drops_mode(tmp_path):
    mig = tmp_path / "mig"
    mig.mkdir()
    for f in sorted(db.MIGRATIONS_DIR.glob("*.sql"))[:11]:
        (mig / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    conn = _mem()
    assert db.migrate(conn, None, mig) == 11
    conn.execute("INSERT INTO story VALUES (1,'s','t',0)")
    conn.execute("INSERT INTO discussion VALUES (1,1,'x','web',NULL,0,NULL)")
    seed = [(1, "slow", None), (2, "direct", None), (3, "imaginative", None), (4, "slow", "deer"), (5, None, None)]
    for seq, mode, character in seed:
        conn.execute("INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors, mode, character) "
                     "VALUES (1, ?, 'assistant', 't', 0, 'den', '[]', ?, ?)", (seq, mode, character))
    conn.execute("INSERT INTO memory (scope, text, quote, discussion_id, seq, valid_from, learned_at) "
                 "VALUES ('author', 'm', 'q', 1, 1, 0, 0)")
    conn.commit()
    assert db.migrate(conn, None) >= 12
    rows = {r["seq"]: r["character"] for r in conn.execute("SELECT seq, character FROM utterance")}
    assert rows == {1: "hyena", 2: "buffalo", 3: "deer", 4: "deer", 5: None}
    assert "mode" not in _cols(conn, "utterance")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT discussion_id, seq FROM memory").fetchone()[:] == (1, 1)


def test_0014_keeps_every_discussion_reference(tmp_path):
    old = tmp_path / "mig"
    old.mkdir()
    for f in sorted(db.MIGRATIONS_DIR.glob("*.sql"))[:13]:
        (old / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    conn = _mem()
    assert db.migrate(conn, None, old) == 13
    conn.executescript("""
        INSERT INTO story VALUES (1,'a','甲',0), (2,'b','乙',0);
        INSERT INTO discussion VALUES (5,1,'x','web',NULL,0,NULL), (7,1,'y','mcp',NULL,0,NULL),
                                      (9,2,'z','web',NULL,0,NULL);
        INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors)
            VALUES (5,0,'user','問',1,'den','[]'), (5,1,'assistant','答',2,'den','[]'),
                   (7,0,'assistant','嗯',3,'den','[]'), (9,0,'assistant','好',4,'den','[]');
        INSERT INTO reaction VALUES (5,1,'up',NULL,5);
        INSERT INTO memory (scope, text, quote, discussion_id, seq, valid_from, learned_at)
            VALUES ('author','記','答',5,1,2,6);
        INSERT INTO conclusion (story_id, external_id, discussion_id, kind, text, refs, quotes,
                                provenance, valid_from) VALUES (2,'c1',9,'k','t','[]','[]','{}',0);
        INSERT INTO settlement VALUES (7,0,1);
    """)
    tables = ("discussion", "utterance", "reaction", "memory", "conclusion", "settlement")
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    assert db.migrate(conn, None) == 17
    assert {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables} == before
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert [tuple(r) for r in conn.execute("SELECT id, story_id FROM discussion ORDER BY id")] == [(5, 1), (7, 1), (9, 2)]


def test_0014_session_id_is_global_and_story_optional():
    conn = _mem()
    db.migrate(conn, None)
    conn.execute("INSERT INTO story VALUES (1,'s','t',0), (2,'u','t',0)")
    conn.execute("INSERT INTO discussion (id, story_id, external_id, home, client, started_at, ended_at) VALUES (1,NULL,'x','web',NULL,0,NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO discussion (id, story_id, external_id, home, client, started_at, ended_at) VALUES (2,2,'x','web',NULL,0,NULL)")


def test_0016_existing_rows_become_version_one(tmp_path):
    old = tmp_path / "mig"
    old.mkdir()
    for f in sorted(db.MIGRATIONS_DIR.glob("*.sql"))[:15]:
        (old / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    conn = _mem()
    assert db.migrate(conn, None, old) == 15
    conn.executescript("""
        INSERT INTO story VALUES (1,'a','甲',0);
        INSERT INTO discussion (id, story_id, external_id, home, client, started_at, ended_at)
            VALUES (5,1,'x','web',NULL,0,NULL);
        INSERT INTO utterance (discussion_id, seq, role, text, ts, origin, anchors)
            VALUES (5,0,'user','問',1,'den','[]'), (5,1,'assistant','答',2,'den','[]');
        INSERT INTO reaction VALUES (5,1,'misread','嗯',5);
    """)
    assert db.migrate(conn, None) == 17
    assert [tuple(r) for r in conn.execute("SELECT seq, variant, edited_at FROM utterance ORDER BY seq")] == \
        [(0, 1, None), (1, 1, None)]
    assert [tuple(r) for r in conn.execute("SELECT * FROM reaction")] == [(5, 1, 1, "misread", "嗯", 5.0)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
