"""den 測試共用 fixture(tests/conftest.py 的看不到,照抄這一支)。"""
from pathlib import Path

import pytest

from marrow import db, importer

FIXTURES = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


@pytest.fixture
def conn():
    """已 migrate 的 in-memory DB,並匯入 tests/fixtures/mini。"""
    c = db.connect("sqlite:///:memory:")
    db.migrate(c, None)
    importer.import_story(c, FIXTURES / "mini", 1.0)
    yield c
    c.close()


@pytest.fixture
def data(tmp_path):
    """tmp_path 當 data_dir,檔案 DB 預先 migrate + 匯入 mini。"""
    url = f"sqlite:///{tmp_path}/t.db"
    c = db.connect(url)
    db.migrate(c, tmp_path / "t.db")
    importer.import_story(c, FIXTURES / "mini", 1.0)
    c.close()
    return url, tmp_path
