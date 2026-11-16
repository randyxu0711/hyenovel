import threading

from den.tests.test_app_discuss import c, fake_chat, first_turn, in_loop, post_discuss  # noqa: F401
from marrow import repo


def _slugs(c):
    return [w["slug"] for w in c.get("/api/works").json()["works"]]


def _archived(c):
    return [w["slug"] for w in c.get("/api/archived-works").json()["works"]]


def _story(c, slug="mini"):
    return in_loop(c, lambda conn: repo.story_by_slug(conn, slug))


def test_rename_wins_over_analysis_title_and_blank_resets(c):
    auto = next(w["title"] for w in c.get("/api/works").json()["works"] if w["slug"] == "mini")
    r = c.patch("/api/works/mini", json={"title": "  新名字 "})
    assert (r.status_code, r.json()) == (200, {"title": "新名字"})
    assert next(w["title"] for w in c.get("/api/works").json()["works"] if w["slug"] == "mini") == "新名字"
    assert c.get("/api/works/mini").json()["title"] == "新名字"
    assert c.get("/api/works", params={"q": "新名字"}).json()["works"][0]["slug"] == "mini"
    assert c.patch("/api/works/mini", json={"title": " "}).json() == {"title": auto}
    assert _story(c)["custom_title"] is None


def test_rename_too_long_rejected(c):
    r = c.patch("/api/works/mini", json={"title": "字" * 81})
    assert (r.status_code, r.json()["code"]) == (422, "title-too-long")
    assert _story(c)["custom_title"] is None


def test_renamed_title_reaches_sessions_and_memory(c):
    sid = first_turn(c)
    c.post("/api/memory", json={"scope": "work", "slug": "mini", "text": "記"})
    c.patch("/api/works/mini", json={"title": "改過"})
    assert c.get("/api/sessions").json()["sessions"][0]["title"] == "改過"
    assert c.get("/api/memory").json()["memories"][0]["title"] == "改過"
    c.post(f"/api/sessions/{sid}/archive")
    assert c.get("/api/archived-sessions").json()["sessions"][0]["title"] == "改過"


def test_archive_hides_work_and_its_sessions_unarchive_brings_back(c):
    sid = first_turn(c)
    assert c.post("/api/works/mini/archive").status_code == 204
    assert "mini" not in _slugs(c) and _archived(c) == ["mini"]
    assert c.get("/api/sessions").json()["sessions"] == []
    assert c.get("/api/works/mini").status_code == 200
    row = c.get("/api/archived-works").json()["works"][0]
    assert row["sessions"] == 1 and row["title"]
    assert c.post("/api/works/mini/unarchive").status_code == 204
    assert "mini" in _slugs(c) and _archived(c) == []
    assert [s["session"] for s in c.get("/api/sessions").json()["sessions"]] == [sid]


def test_talking_in_archived_work_brings_it_back(c):
    sid = first_turn(c)
    c.post("/api/works/mini/archive")
    post_discuss(c, "mini", sid, "再聊")
    assert "mini" in _slugs(c) and _story(c)["archived_at"] is None


def test_delete_requires_archive_first(c):
    r = c.delete("/api/works/mini")
    assert (r.status_code, r.json()["code"]) == (409, "not-archived")
    assert _story(c) is not None


def test_delete_removes_work_and_its_sessions(c):
    sid = first_turn(c)
    c.post("/api/works/mini/archive")
    assert c.delete("/api/works/mini").status_code == 204
    assert _story(c) is None and _archived(c) == []
    assert c.get(f"/api/sessions/{sid}").status_code == 404
    assert c.get("/api/works/mini").status_code == 404
    assert "other" in _slugs(c)


def test_delete_busy_while_analysis_or_turn_running(c, fake_chat):
    sid = first_turn(c)
    c.post("/api/works/mini/archive")

    def running(conn):
        st = repo.story_by_slug(conn, "mini")
        j = repo.create_job(conn, "critique", st["id"], repo.latest_source_version(conn, st["id"])["id"], {}, 0)
        conn.execute("UPDATE job SET state = 'running' WHERE id = ?", (j,))
        conn.commit()
        return j
    j = in_loop(c, running)
    assert c.delete("/api/works/mini").json()["code"] == "busy"
    in_loop(c, lambda conn: (conn.execute("UPDATE job SET state = 'cancelled' WHERE id = ?", (j,)), conn.commit()))

    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "卡住"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert c.delete("/api/works/mini").json()["code"] == "busy"
    finally:
        fake_chat.release.set()
    t.join(5)
    assert _story(c) is not None


def test_unknown_work_404(c):
    for r in (c.patch("/api/works/nosuch", json={"title": "x"}), c.post("/api/works/nosuch/archive"),
              c.post("/api/works/nosuch/unarchive"), c.delete("/api/works/nosuch")):
        assert (r.status_code, r.json()["code"]) == (404, "unknown-work")


def test_submitting_to_archived_work_brings_it_back(c):
    text = in_loop(c, lambda conn: repo.latest_source_version(conn, repo.story_by_slug(conn, "mini")["id"])["text"])
    c.post("/api/works/mini/archive")
    assert c.post("/api/stories", json={"text": text}).json()["reused"] is True
    assert "mini" in _slugs(c)
    c.post("/api/works/mini/archive")
    assert c.post("/api/stories", json={"text": "新的一版。", "slug": "mini"}).status_code == 201
    assert "mini" in _slugs(c)
