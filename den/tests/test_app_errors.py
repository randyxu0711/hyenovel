"""錯誤帶機器可讀 code、API 收進 /api、den 出前端靜態檔。"""
import pytest

from den import app as den_app
from den import config as den_config
from den.tests.test_app import _auth, _client

NAV = {"accept": "text/html"}   # 瀏覽器導覽:fallback 只對它回 index.html


def test_error_codes_are_unique():
    assert len(set(den_app.ERROR_CODES)) == len(den_app.ERROR_CODES)


def test_unknown_work_has_code(data):
    with _client(data) as c:
        r = c.get("/api/works/nope/source", headers=_auth(data[1]))
    assert r.status_code == 404
    assert r.json() == {"detail": "這篇不在 DB", "code": "unknown-work", "params": {}}


def test_bad_part_has_code(data):
    with _client(data) as c:
        r = c.get("/api/works/mini/zzz", headers=_auth(data[1]))
    assert r.status_code == 422 and r.json()["code"] == "bad-part"


@pytest.mark.parametrize("text,code", [("  ", "empty-story"), ("字" * 1000, "story-too-long")])
def test_story_rejects_have_code(data, text, code, monkeypatch):
    monkeypatch.setattr(den_config, "MAX_SOURCE_BYTES", 1000)
    with _client(data) as c:
        r = c.post("/api/stories", json={"text": text}, headers=_auth(data[1]))
    assert r.status_code == 422 and r.json()["code"] == code


def test_plain_http_exception_has_no_code(data):
    with _client(data) as c:
        r = c.get("/api/jobs/999", headers=_auth(data[1]))
    assert r.status_code == 404 and r.json() == {"detail": "job 不存在"}


def test_old_root_paths_are_gone(data):
    with _client(data) as c:
        assert c.get("/works", headers=_auth(data[1])).status_code == 404
        assert c.get("/health", headers=_auth(data[1])).status_code == 404


def test_frontend_served_with_spa_fallback(data, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>dash")
    with _client(data, frontend_dir=dist) as c:
        assert "dash" in c.get("/w/d01", headers=NAV).text            # SPA 路由回 index.html,不需 token
        assert c.get("/api/works", headers=_auth(data[1])).status_code == 200   # API 優先
        assert c.get("/api/works").status_code == 401    # /api 仍要 token


def test_unmatched_api_path_is_json_404_not_index(data, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>dash")
    with _client(data, frontend_dir=dist) as c:
        r = c.get("/api/nope", headers={**_auth(data[1]), **NAV})
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
