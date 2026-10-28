"""資料目錄、DATABASE_URL 與連線。

SQLite 專屬語法(PRAGMA、VACUUM INTO)只准出現在這個檔——這裡是方言接縫。
`DATABASE_URL` 的接縫保留,但目前只收 sqlite:(spec §8 R6):填別的直接拒收,
不讓人以為切得過去。
"""
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path

_SQLITE = "sqlite:///"


class UnsupportedDatabase(Exception):
    pass


def data_dir(env: Mapping[str, str] = os.environ) -> Path:
    if env.get("HYENOVEL_DATA_DIR"):
        return Path(env["HYENOVEL_DATA_DIR"])
    base = env.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(base) / "hyenovel"


def database_url(env: Mapping[str, str] = os.environ) -> str:
    return env.get("DATABASE_URL") or f"{_SQLITE}{data_dir(env)}/hyenovel.db"


def connect(url: str) -> sqlite3.Connection:
    if not url.startswith(_SQLITE):
        raise UnsupportedDatabase(f"目前只支援 SQLite(sqlite:///<路徑>),收到:{url.split(':', 1)[0]}")
    target = url[len(_SQLITE):]
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if target != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn
