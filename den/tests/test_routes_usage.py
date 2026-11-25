"""GET /api/usage:期間篩選、補標題與讀伴名、非法期間。"""
import time

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den import characters
from den.tests.test_app import Run, _auth
from marrow import db, repo

TOK = {"input": 100, "output": 0, "cache_read": 0, "cache_creation": 0, "thinking": 0}


def _call(conn, started, kind="chat", **keys):
    cid = repo.start_call(conn, kind, started, "fp", runner="claude-cli", **keys)
    repo.finish_call(conn, cid, outcome="ok", ended_at=started + 1, duration_ms=10, tokens=TOK,
                     tokens_partial=False, cost_usd=None, model="m", rate_limit=None)


@pytest.fixture
def c(data):
    url, d = data
    now = time.time()
    conn = db.connect(url)
    with conn:
        mini = repo.story_by_slug(conn, "mini")["id"]
        _call(conn, now - 3600, story_id=mini, character_id="hyena", character_v=1)
        _call(conn, now - 20 * 86400, story_id=mini, character_id="ghost", character_v=2)
    conn.close()
    with TestClient(den_app.create_app(url, d, run_factory=Run()), base_url="http://127.0.0.1") as client:
        client.headers.update(_auth(d))
        client.db_url = url
        yield client


def test_usage_default_7_days(c):
    r = c.get("/api/usage")
    assert r.status_code == 200, r.text
    assert r.json()["total"]["tokens"] == 100


def test_usage_all(c):
    body = c.get("/api/usage", params={"since": "all"}).json()
    assert body["total"]["tokens"] == 200 and len(body["compare"]["character"]) == 2
    assert c.get("/api/usage", params={"since": "30"}).json()["total"]["tokens"] == 200


def test_usage_bad_since_422(c):
    assert c.get("/api/usage", params={"since": "9"}).status_code == 422


def test_usage_titles_and_names(c):
    body = c.get("/api/usage", params={"since": "all"}).json()
    [w] = body["works"]
    assert w["slug"] == "mini" and isinstance(w["title"], str) and w["title"]
    names = {r["character_id"]: r["name"] for r in body["compare"]["character"]}
    conn = db.connect(c.db_url)
    try:
        assert names["hyena"] == characters.get(conn, "hyena")["name"]
    finally:
        conn.close()
    assert names["ghost"] == {"zh-Hant": "ghost", "en": "ghost"}
