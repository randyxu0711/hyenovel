import json
import time

import pytest

from den import suggest
from den.tests.test_app_discuss import c, fake_chat, in_loop, post_discuss  # noqa: F401
from marrow import repo

OUT = json.dumps({"summary": "聊了結尾", "threads": [{"text": "結尾的節奏", "quote": "結尾太快", "source_quote": None}]},
                 ensure_ascii=False)


def talked(c):
    sid = post_discuss(c, "mini", None, "結尾太快?")[-1]["data"]["session_id"]
    post_discuss(c, "mini", sid, "再問一次")
    return sid


def made(c, fake_chat):
    sid = talked(c)
    fake_chat.deltas = [OUT]
    assert c.post("/api/works/mini/prior/prepare").status_code == 202
    for _ in range(200):
        got = c.get("/api/works/mini/prior").json()
        if got["digests"]:
            return sid, got
        time.sleep(0.02)
    raise AssertionError("digest 沒出現")


def test_prepare_then_read(c, fake_chat):
    sid, got = made(c, fake_chat)
    assert got["enabled"] is True
    assert [(d["session"], d["text"], d["edited"]) for d in got["digests"]] == [(sid, "聊了結尾", False)]
    assert [(t["text"], t["stale"]) for t in got["threads"]] == [("結尾的節奏", False)]


def test_prepare_runs_when_only_suggest_on(c, fake_chat):
    talked(c)
    fake_chat.deltas = [OUT]
    assert c.put("/api/settings/prior", json={"enabled": False}).status_code == 204
    assert c.post("/api/works/mini/prior/prepare").status_code == 202
    for _ in range(200):
        if c.get("/api/works/mini/prior").json()["digests"]:
            return
        time.sleep(0.02)
    raise AssertionError("digest 沒出現")


def test_disabled_prepare_noop(c, fake_chat):
    talked(c)
    n = len(fake_chat.calls)
    in_loop(c, lambda conn: suggest.set_enabled(conn, False))
    assert c.put("/api/settings/prior", json={"enabled": False}).status_code == 204
    assert c.post("/api/works/mini/prior/prepare").status_code == 204
    assert c.get("/api/works/mini/prior").json()["enabled"] is False
    assert c.get("/api/settings/prior").json() == {"enabled": False}
    time.sleep(0.05)
    assert len(fake_chat.calls) == n


def test_edit_digest(c, fake_chat):
    _, got = made(c, fake_chat)
    old = got["digests"][0]["id"]
    r = c.put(f"/api/digests/{old}", json={"text": " 作者改的 "})
    assert r.status_code == 201
    now = c.get("/api/works/mini/prior").json()
    assert now["digests"][0] == {**now["digests"][0], "id": r.json()["id"], "text": "作者改的", "edited": True}
    assert now["threads"][0]["id"] == got["threads"][0]["id"]


def test_edit_stale_digest_409(c, fake_chat):
    _, got = made(c, fake_chat)
    old = got["digests"][0]["id"]
    c.put(f"/api/digests/{old}", json={"text": "第一次改"})
    r = c.put(f"/api/digests/{old}", json={"text": "舊分頁改"})
    assert (r.status_code, r.json()["code"]) == (409, "stale-digest")
    assert c.get("/api/works/mini/prior").json()["digests"][0]["text"] == "第一次改"


def test_edit_blank_and_unknown(c, fake_chat):
    _, got = made(c, fake_chat)
    r = c.put(f"/api/digests/{got['digests'][0]['id']}", json={"text": "  "})
    assert (r.status_code, r.json()["code"]) == (422, "blank-digest")
    assert c.put("/api/digests/999", json={"text": "x"}).json()["code"] == "unknown-digest"


def test_thread_ended_and_talked(c, fake_chat):
    sid, got = made(c, fake_chat)
    tid = got["threads"][0]["id"]
    assert c.put(f"/api/threads/{tid}", json={"ended": True}).status_code == 204
    assert c.get("/api/works/mini/prior").json()["threads"] == []
    c.put(f"/api/threads/{tid}", json={"ended": False})
    assert len(c.get("/api/works/mini/prior").json()["threads"]) == 1
    assert c.put(f"/api/sessions/{sid}/threads/{tid}/talked", json={"talked": True}).status_code == 204
    d = in_loop(c, lambda conn: repo.discussion_by_session(conn, sid)["id"])
    assert in_loop(c, lambda conn: repo.talked_in(conn, d)) == {tid}
    c.put(f"/api/sessions/{sid}/threads/{tid}/talked", json={"talked": False})
    assert in_loop(c, lambda conn: repo.talked_in(conn, d)) == set()


@pytest.mark.parametrize("method,url,body,code", [
    ("post", "/api/works/nope/prior/prepare", None, "unknown-work"),
    ("get", "/api/works/nope/prior", None, "unknown-work"),
    ("put", "/api/threads/999", {"ended": True}, "unknown-thread"),
    ("put", "/api/sessions/nosuch/threads/1/talked", {"talked": True}, "unknown-session"),
])
def test_unknown_404(c, method, url, body, code):
    r = getattr(c, method)(url, **({"json": body} if body else {}))
    assert (r.status_code, r.json()["code"]) == (404, code)


def test_talked_unknown_thread(c):
    sid = talked(c)
    r = c.put(f"/api/sessions/{sid}/threads/999/talked", json={"talked": True})
    assert (r.status_code, r.json()["code"]) == (404, "unknown-thread")


def test_reject_is_logged(c, caplog):
    caplog.set_level("INFO", logger="hyenovel")
    c.put("/api/threads/999", json={"ended": True})
    assert "event=reject where=prior reason=unknown-thread" in caplog.text
