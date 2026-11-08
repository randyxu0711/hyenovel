import threading

from den.tests.test_app_discuss import c, fake_chat, first_turn, in_loop, post_discuss  # noqa: F401
from marrow import repo


def _discussion(c, sid):
    return in_loop(c, lambda conn: repo.discussion_by_session(conn, sid))


def _listed(c):
    recent = [r["session"] for r in c.get("/api/sessions").json()["sessions"]]
    work = [r["session"] for r in c.get("/api/works/mini/sessions").json()["sessions"]]
    archived = [r["session"] for r in c.get("/api/archived-sessions").json()["sessions"]]
    return recent, work, archived


def test_archive_hides_everywhere_and_unarchive_brings_back(c):
    sid = first_turn(c)
    assert _listed(c) == ([sid], [sid], [])
    assert c.post(f"/api/sessions/{sid}/archive").status_code == 204
    assert _listed(c) == ([], [], [sid])
    row = c.get("/api/archived-sessions").json()["sessions"][0]
    assert (row["slug"], row["preview"]) == ("mini", "結尾太快?")
    assert c.get(f"/api/sessions/{sid}").status_code == 200
    assert c.post(f"/api/sessions/{sid}/unarchive").status_code == 204
    assert _listed(c) == ([sid], [sid], [])


def test_archive_twice_keeps_first_time(c):
    sid = first_turn(c)
    c.post(f"/api/sessions/{sid}/archive")
    first = _discussion(c, sid)["archived_at"]
    c.post(f"/api/sessions/{sid}/archive")
    assert _discussion(c, sid)["archived_at"] == first


def test_delete_requires_archive_first(c):
    sid = first_turn(c)
    r = c.delete(f"/api/sessions/{sid}")
    assert (r.status_code, r.json()["code"]) == (409, "not-archived")
    assert _discussion(c, sid) is not None


def test_delete_removes_session_keeps_memory_without_source(c):
    sid = first_turn(c)
    r = c.post("/api/memory", json={"scope": "author", "text": "寫短句", "session": sid, "seq": 0, "quote": "結尾太快"})
    assert r.status_code == 201, r.json()
    assert c.put(f"/api/sessions/{sid}/turns/1/reaction", json={"mark": "stopped"}).status_code == 200
    c.post(f"/api/sessions/{sid}/archive")
    assert c.delete(f"/api/sessions/{sid}").status_code == 204
    assert _discussion(c, sid) is None
    assert c.get(f"/api/sessions/{sid}").json()["code"] == "unknown-session-id"
    assert _listed(c) == ([], [], [])
    mem = c.get("/api/memory").json()["memories"]
    assert [(m["text"], m["session"], m["quote"]) for m in mem] == [("寫短句", None, None)]


def test_unknown_session_404(c):
    for r in (c.post("/api/sessions/nosuch/archive"), c.post("/api/sessions/nosuch/unarchive"),
              c.delete("/api/sessions/nosuch")):
        assert (r.status_code, r.json()["code"]) == (404, "unknown-session")


def test_archive_and_delete_busy_while_turn_running(c, fake_chat):
    sid = first_turn(c)
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "卡住"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert c.post(f"/api/sessions/{sid}/archive").json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)
