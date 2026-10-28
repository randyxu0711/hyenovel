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
    assert db.migrate(conn, None) == 2
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert TABLES <= names


def test_migrate_is_idempotent():
    conn = _mem()
    db.migrate(conn, None)
    assert db.migrate(conn, None) == 2


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
    conn.execute("INSERT INTO discussion VALUES (1,1,'x','web',NULL,0,NULL)")
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
