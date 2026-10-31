"""瀏覽器驗證:一次性啟動碼 → HttpOnly cookie;guard 對所有路由驗 Host / Origin。"""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den.app import SESSION_COOKIE, session_cookie_value
from den.tests.test_app import BASE, Run, _auth


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_app(data, clock):
    url, d = data

    def make(**kw):
        return TestClient(den_app.create_app(url, d, run_factory=Run(), clock=clock, **kw),
                          base_url=BASE)
    return make


@pytest.fixture
def client(make_app, data):
    with make_app() as c:
        c.bearer = _auth(data[1])
        yield c


def _login(client):
    """走完 launch → login,回傳 cookie 值。"""
    url = client.post("/api/launch", headers=client.bearer).json()["url"]
    code = parse_qs(urlparse(url).query)["code"][0]
    r = client.get(f"/login?code={code}", follow_redirects=False)
    return r.cookies[SESSION_COOKIE]


@pytest.fixture
def cookie_client(client):
    cookie = _login(client)
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, cookie)
    return client


def test_launch_code_single_use(client):
    body = client.post("/api/launch", headers=client.bearer).json()
    assert body["url"].startswith("http://127.0.0.1:8788/login?code=")
    code = parse_qs(urlparse(body["url"]).query)["code"][0]
    assert len(code) == 32 and int(code, 16) >= 0
    r = client.get(f"/login?code={code}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    sc = r.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in sc and "HttpOnly" in sc and "SameSite=strict" in sc.replace(
        "Strict", "strict") and "Path=/" in sc
    r2 = client.get(f"/login?code={code}", follow_redirects=False)
    assert r2.status_code == 401 and r2.json()["code"] == "bad-launch-code"


def test_login_without_or_wrong_code(client):
    assert client.get("/login", follow_redirects=False).json()["code"] == "bad-launch-code"
    assert client.get("/login?code=nope", follow_redirects=False).status_code == 401


def test_launch_code_expires(client, clock):
    url = client.post("/api/launch", headers=client.bearer).json()["url"]
    code = parse_qs(urlparse(url).query)["code"][0]
    clock.t += 121
    r = client.get(f"/login?code={code}", follow_redirects=False)
    assert r.status_code == 401 and r.json()["code"] == "bad-launch-code"


def test_launch_code_valid_at_ttl_edge_and_expired_codes_pruned(client, clock):
    c1 = parse_qs(urlparse(client.post("/api/launch", headers=client.bearer).json()["url"]).query)["code"][0]
    clock.t += 120
    assert client.get(f"/login?code={c1}", follow_redirects=False).status_code == 303
    client.post("/api/launch", headers=client.bearer)
    clock.t += 121
    client.post("/api/launch", headers=client.bearer)
    assert len(client.app.state.launch_codes) == 1   # 前兩張過期的被清掉


def test_launch_needs_bearer_not_cookie(cookie_client):
    r = cookie_client.post("/api/launch")
    assert r.status_code == 401 and r.json()["code"] == "bad-token"
    assert cookie_client.post("/api/launch", headers={"Origin": "http://127.0.0.1:8788"}).status_code == 401


def test_cookie_get_ok_post_needs_origin(cookie_client):
    assert cookie_client.get("/api/works").status_code == 200
    r = cookie_client.post("/api/stories", json={"text": "x"})
    assert r.status_code == 403 and r.json()["code"] == "bad-origin"
    ok = cookie_client.post("/api/stories", json={"text": "x"}, headers={"Origin": "http://127.0.0.1:8788"})
    assert ok.status_code != 403
    ok = cookie_client.post("/api/stories", json={"text": "x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert ok.status_code != 403
    cross = cookie_client.post("/api/stories", json={"text": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403


def test_cookie_with_foreign_origin_rejected(cookie_client):
    r = cookie_client.get("/api/works", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "bad-origin"


def test_wrong_cookie_and_no_credentials_are_bad_token(client):
    for cookies in ({}, {SESSION_COOKIE: "deadbeef"}):
        client.cookies.clear()
        client.cookies.update(cookies)
        r = client.get("/api/works")
        assert r.status_code == 401 and r.json()["code"] == "bad-token"
    r = client.get("/api/works", headers={"Authorization": "Bearer wrong"})
    assert r.json()["code"] == "bad-token"


def test_bearer_still_works_without_origin(client):
    assert client.post("/api/stories", json={"text": "x"}, headers=client.bearer).status_code != 403
    assert client.get("/api/works", headers=client.bearer).status_code == 200


@pytest.mark.parametrize("host", ["evil.example:8788", "127.0.0.1.evil.example", "a@127.0.0.1",
                                  "localhost.evil.com:80", "", "[::2]:80", "127.0.0.1:8788/x"])
def test_bad_host_rejected_everywhere(client, host):
    for path in ("/", "/login?code=x", "/api/works", "/api/launch", "/nope"):
        r = client.get(path, headers={**client.bearer, "host": host})
        assert r.status_code == 403 and r.json()["code"] == "bad-host", (path, host)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8788", "localhost:8788", "LOCALHOST", "[::1]:8788"])
def test_local_hosts_accepted(client, host):
    r = client.get("/api/works", headers={**client.bearer, "host": host})
    assert r.status_code == 200


def test_missing_host_rejected(client):
    r = client.get("/api/works", headers={**client.bearer, "host": ""})
    assert r.json()["code"] == "bad-host"


def test_bad_origin_code_and_allowlist_includes_ipv6(client):
    h = {**client.bearer, "Origin": "http://evil.example"}
    assert client.get("/api/works", headers=h).json()["code"] == "bad-origin"
    assert client.get("/api/works", headers={**client.bearer, "Origin": "http://[::1]:8788"}).status_code == 200
    # 靜態/ login 也驗 Origin
    assert client.get("/login?code=x", headers={"Origin": "http://evil.example"}).json()["code"] == "bad-origin"


def test_prefix_is_exact_api(client):
    # /apix 不是 API:不要 token(落到一般 404),/api 本身要 token
    assert client.get("/apix").status_code == 404
    assert client.get("/api").json()["code"] == "bad-token"
    assert client.get("/api/").json()["code"] == "bad-token"


def test_cookie_survives_restart_and_dies_on_token_rotation(make_app, data):
    d = data[1]
    with make_app() as c:
        c.bearer = _auth(d)
        cookie = _login(c)
    with make_app() as c:   # 重啟:token 沒變 → 同一個 cookie 仍有效
        c.cookies.set(SESSION_COOKIE, cookie)
        assert c.get("/api/works").status_code == 200
    (d / "den.token").unlink()   # 輪替:load_token 重產
    with make_app() as c:
        c.cookies.set(SESSION_COOKIE, cookie)
        assert c.get("/api/works").json()["code"] == "bad-token"


def test_cookie_value_is_hmac_of_token():
    assert session_cookie_value("a") != session_cookie_value("b")
    assert len(session_cookie_value("a")) == 64
    assert session_cookie_value("a") == session_cookie_value("a")


def test_rejects_do_not_refresh_last_seen(client, clock):
    t0 = client.app.state.last_seen
    clock.t += 50
    client.get("/api/works", headers={"host": "evil.example"})
    client.get("/api/works")
    assert client.app.state.last_seen == t0
    client.get("/api/works", headers=client.bearer)
    assert client.app.state.last_seen == clock.t
