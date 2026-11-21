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


def test_memory_works_lists_unarchived(c):
    def seed(conn):
        with conn:
            for slug in ("gone", "quiet"):
                repo.add_source_version(conn, repo.ensure_story(conn, slug, None, 1.0), "一段稿", 1.0)
    in_loop(c, seed)
    assert c.post("/api/works/gone/archive").status_code == 204
    works = {w["slug"]: w for w in c.get("/api/memory/works").json()["works"]}
    assert "gone" not in works and {"mini", "quiet"} <= works.keys()
    assert all(w["title"] for w in works.values())
    assert works["quiet"]["digests"] == [] and works["quiet"]["threads"] == []


def test_memory_works_carries_digests_and_threads(c, fake_chat):
    sid, _ = made(c, fake_chat)
    (w,) = [w for w in c.get("/api/memory/works").json()["works"] if w["slug"] == "mini"]
    assert [(d["session"], d["versions"]) for d in w["digests"]] == [(sid, 1)]
    assert [(t["text"], t["ended"], t["stale"]) for t in w["threads"]] == [("結尾的節奏", False, False)]


def test_digest_revert_adds_version(c, fake_chat):
    _, got = made(c, fake_chat)
    first = got["digests"][0]["id"]
    c.put(f"/api/digests/{first}", json={"text": "作者改的"})
    r = c.post(f"/api/digests/{first}/revert")
    assert r.status_code == 201
    vs = c.get(f"/api/digests/{r.json()['id']}/versions").json()["versions"]
    assert [(v["text"], v["current"]) for v in vs] == [("聊了結尾", True), ("作者改的", False), ("聊了結尾", False)]
    assert c.get("/api/works/mini/prior").json()["digests"][0]["text"] == "聊了結尾"
    r2 = c.post(f"/api/digests/{r.json()['id']}/revert")
    assert (r2.status_code, r2.json()["code"]) == (409, "digest-is-current")


def test_digest_versions_unknown(c):
    for r in (c.get("/api/digests/999/versions"), c.post("/api/digests/999/revert")):
        assert (r.status_code, r.json()["code"]) == (404, "unknown-digest")


def test_digest_revert_keeps_through_seq_and_threads(c, fake_chat):
    _, got = made(c, fake_chat)
    first = got["digests"][0]["id"]
    c.put(f"/api/digests/{first}", json={"text": "作者改的"})
    cur_id = c.get("/api/works/mini/prior").json()["digests"][0]["id"]
    cur = in_loop(c, lambda conn: repo.digest_by_id(conn, cur_id))
    in_loop(c, lambda conn: conn.execute("UPDATE digest SET through_seq = through_seq + 7 WHERE id = ?", (cur["id"],)))
    threads = in_loop(c, lambda conn: repo.threads_of(conn, cur["root_id"]))
    new = c.post(f"/api/digests/{first}/revert").json()["id"]
    row = in_loop(c, lambda conn: repo.digest_by_id(conn, new))
    assert row["through_seq"] == cur["through_seq"] + 7
    assert in_loop(c, lambda conn: repo.threads_of(conn, cur["root_id"])) == threads
    n = len(fake_chat.calls)
    assert c.post("/api/works/mini/prior/prepare").status_code == 202
    time.sleep(0.1)
    assert len(fake_chat.calls) == n
