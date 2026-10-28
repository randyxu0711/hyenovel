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


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _free_backup_path(db_path: Path, version: int) -> Path:
    """`<db>.bak-v<N>`,已存在就 `-2`、`-3`…——絕不覆蓋既有備份,也不讓一份殘留的備份
    (上次升級失敗、或使用者剛從它還原)擋住之後每一次啟動(VACUUM INTO 不肯寫已存在的檔)。"""
    base = Path(f"{db_path}.bak-v{version}")
    p, i = base, 2
    while p.exists():
        p, i = Path(f"{base}-{i}"), i + 1
    return p


def migrate(conn: sqlite3.Connection, db_path: Path | None,
            migrations_dir: Path = MIGRATIONS_DIR) -> int:
    """套用 `NNNN_*.sql` 中版號大於 `PRAGMA user_version` 的,回最終版號。

    別人機器上的 DB 我們碰不到,所以升級是 daemon 啟動時自動做的;既有 DB(版號 > 0)
    升級前先 `VACUUM INTO` 留一份 `<db>.bak-v<舊版號>`——WAL 下直接複製檔案可能拿到不一致快照。
    """
    files = sorted(migrations_dir.glob("*.sql"))
    versions = [int(f.name.split("_", 1)[0]) for f in files]
    if versions != list(range(1, len(files) + 1)):
        raise ValueError(f"migration 版號必須從 1 連號不重複:{[f.name for f in files]}")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = files[current:]
    if pending and current > 0 and db_path is not None:
        conn.execute("VACUUM INTO ?", (str(_free_backup_path(db_path, current)),))
    for n, f in enumerate(pending, start=current + 1):
        # 每支 migration 連同版號一個 transaction(SQLite 的 DDL 可 rollback):中途壞掉不留半套表。
        try:
            conn.executescript(f"BEGIN;\n{f.read_text(encoding='utf-8')}\n"
                               f"PRAGMA user_version = {n};\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
    return conn.execute("PRAGMA user_version").fetchone()[0]
