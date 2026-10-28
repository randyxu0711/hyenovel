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
