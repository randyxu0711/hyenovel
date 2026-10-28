"""marrow.db:資料目錄、DATABASE_URL、連線。只支援 SQLite(spec §8 R6)。"""
import pytest

from marrow import db


def test_data_dir_prefers_override(tmp_path):
    env = {"HYENOVEL_DATA_DIR": str(tmp_path / "x"), "XDG_DATA_HOME": "/nope"}
    assert db.data_dir(env) == tmp_path / "x"


def test_data_dir_xdg(tmp_path):
    assert db.data_dir({"XDG_DATA_HOME": str(tmp_path)}) == tmp_path / "hyenovel"


def test_data_dir_default_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert db.data_dir({}) == tmp_path / ".local/share/hyenovel"


def test_database_url_default_and_override(tmp_path):
    env = {"HYENOVEL_DATA_DIR": str(tmp_path)}
    assert db.database_url(env) == f"sqlite:///{tmp_path}/hyenovel.db"
    assert db.database_url({**env, "DATABASE_URL": "sqlite:///:memory:"}) == "sqlite:///:memory:"


def test_connect_rejects_non_sqlite():
    with pytest.raises(db.UnsupportedDatabase, match="目前只支援 SQLite"):
        db.connect("postgresql://u@h/d")


def test_connect_file_creates_parent_and_enables_fk(tmp_path):
    conn = db.connect(f"sqlite:///{tmp_path}/a/b.db")
    assert (tmp_path / "a/b.db").exists()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


def test_connect_memory():
    conn = db.connect("sqlite:///:memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
