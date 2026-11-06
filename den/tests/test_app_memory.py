"""記憶 API:狀態碼、code、拒絕留痕、來源不跨篇。"""
import logging

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den.config import MAX_CHAT_CHARS
from den.tests.test_app import Run, _auth
from marrow import db, repo


@pytest.fixture
def c(data):
    url, d = data
    conn = db.connect(url)
    with conn:
        mini = repo.story_by_slug(conn, "mini")["id"]
        other = repo.ensure_story(conn, "other", None, 1.0)
        repo.add_source_version(conn, other, "另一篇", 1.0)
        m = repo.ensure_discussion(conn, mini, "same", "web", None, 1.0)
        repo.add_utterance(conn, m, 0, "user", "我不寫結局,真的", 5.0, "web", [], None)
        repo.add_utterance(conn, m, 1, "assistant", "你不寫結局", 6.0, "web", [], None)
        solo = repo.ensure_discussion(conn, mini, "solo", "web", None, 1.0)
        repo.add_utterance(conn, solo, 0, "user", "一句", 5.0, "web", [], None)
        repo.add_utterance(conn, solo, 1, "assistant", "回", 6.0, "web", [], None)
        longest = repo.ensure_discussion(conn, mini, "long", "web", None, 1.0)
        repo.add_utterance(conn, longest, 0, "user", "長" * MAX_CHAT_CHARS, 5.0, "web", [], None)
        o = repo.ensure_discussion(conn, other, "same", "web", None, 1.0)
        repo.add_utterance(conn, o, 0, "user", "別篇的話", 5.0, "web", [], None)
    conn.close()
    with TestClient(den_app.create_app(url, d, run_factory=Run()), base_url="http://127.0.0.1") as client:
        client.headers.update(_auth(d))
        yield client


SOURCE = {"slug": "mini", "session": "same", "seq": 0, "quote": "不寫結局"}


def _post(c, **body):
    return c.post("/api/memory", json={"scope": "author", "text": "記", **body})


def _assert_err(r, status, code):
    assert (r.status_code, r.json()["code"]) == (status, code), r.text


@pytest.mark.parametrize("body,status,code", [
    ({"scope": "character"}, 422, "bad-scope"),
    ({"scope": "亂寫"}, 422, "bad-scope"),
    ({"text": " \n "}, 422, "blank-memory"),
    ({"scope": "work"}, 422, "slug-required"),
    ({"session": "same", "seq": 0, "quote": "不寫結局"}, 422, "slug-required"),
    ({"slug": "nope"}, 404, "unknown-work"),
    ({"slug": "BAD SLUG!"}, 400, "bad-slug"),
    ({"slug": "mini", "session": "same"}, 422, "bad-source"),
    ({"slug": "mini", "seq": 0, "quote": "x"}, 422, "bad-source"),
    ({"slug": "mini", "session": "nope", "seq": 0, "quote": "x"}, 404, "unknown-session"),
    ({"slug": "mini", "session": "same", "seq": 9, "quote": "x"}, 404, "unknown-turn"),
    ({"slug": "mini", "session": "same", "seq": 0, "quote": "我要寫結局"}, 422, "quote-not-in-turn"),
    ({"slug": "mini", "session": "same", "seq": 1, "quote": "不寫結局"}, 422, "quote-not-in-turn"),
    ({"slug": "other", "session": "same", "seq": 0, "quote": "不寫結局"}, 422, "quote-not-in-turn"),
    ({"text": "字" * 801}, 422, "memory-full"),
])
def test_post_rejections(c, caplog, body, status, code):
    with caplog.at_level(logging.INFO):
        r = _post(c, **body)
    _assert_err(r, status, code)
    assert f"event=reject where=memory reason={code}" in caplog.text
    assert c.get("/api/memory").json()["memories"] == []


def test_needs_token(data):
    url, d = data
    with TestClient(den_app.create_app(url, d, run_factory=Run()), base_url="http://127.0.0.1") as c:
        assert c.get("/api/memory").status_code == 401
        assert c.post("/api/memory", json={"scope": "author", "text": "x"}).status_code == 401


def test_post_typed_shape(c):
    r = _post(c, text="  手打  ")
    assert r.status_code == 201
    row = r.json()
    assert row["text"] == "手打" and row["root"] == row["id"] and row["scope"] == "author"
    assert {k: row[k] for k in ("slug", "title", "quote", "session", "seq", "invalidated_at")} == dict.fromkeys(
        ("slug", "title", "quote", "session", "seq", "invalidated_at"))
    assert set(row) == {"id", "root", "scope", "slug", "title", "text", "quote", "session", "seq",
                        "valid_from", "learned_at", "invalidated_at"}


def test_post_author_with_source_jumps_back_to_the_work(c):
    row = _post(c, **SOURCE).json()
    assert (row["slug"], row["session"], row["seq"], row["quote"]) == ("mini", "same", 0, "不寫結局")
    assert row["valid_from"] == 5.0


def test_post_work_scope(c):
    row = _post(c, scope="work", slug="other").json()
    assert (row["scope"], row["slug"]) == ("work", "other")


def test_same_session_id_in_other_work_writes_to_the_named_one(c):
    row = _post(c, slug="other", session="same", seq=0, quote="別篇").json()
    assert row["slug"] == "other"


def test_get_lists_caps(c):
    body = c.get("/api/memory").json()
    assert body == {"memories": [], "caps": {"author": 800, "work": 600}}


def test_full_flow_keeps_every_row_and_one_live(c):
    mid = _post(c, **SOURCE).json()["id"]
    edited = c.patch(f"/api/memory/{mid}", json={"text": " 新 "})
    assert edited.status_code == 200 and edited.json()["text"] == "新" and edited.json()["root"] == mid
    new = edited.json()["id"]
    assert c.post(f"/api/memory/{new}/archive").status_code == 204
    back = c.post(f"/api/memory/{mid}/revert")
    assert back.status_code == 200 and back.json()["text"] == "記" and back.json()["quote"] == "不寫結局"
    rows = c.get("/api/memory").json()["memories"]
    assert len(rows) == 3 and {r["root"] for r in rows} == {mid}
    assert [r["invalidated_at"] is None for r in rows] == [False, False, True]


@pytest.mark.parametrize("call", [
    lambda c: c.patch("/api/memory/999", json={"text": "x"}),
    lambda c: c.post("/api/memory/999/archive"),
    lambda c: c.post("/api/memory/999/revert"),
])
def test_unknown_memory(c, caplog, call):
    with caplog.at_level(logging.INFO):
        _assert_err(call(c), 404, "unknown-memory")
    assert "event=reject where=memory reason=unknown-memory" in caplog.text


def test_edit_or_archive_dead_row_is_conflict(c, caplog):
    mid = _post(c).json()["id"]
    c.post(f"/api/memory/{mid}/archive")
    with caplog.at_level(logging.INFO):
        _assert_err(c.patch(f"/api/memory/{mid}", json={"text": "x"}), 409, "memory-not-current")
        _assert_err(c.post(f"/api/memory/{mid}/archive"), 409, "memory-not-current")
    assert "event=reject where=memory reason=memory-not-current" in caplog.text


def test_revert_live_row_is_conflict(c, caplog):
    mid = _post(c).json()["id"]
    with caplog.at_level(logging.INFO):
        _assert_err(c.post(f"/api/memory/{mid}/revert"), 409, "memory-is-current")
    assert "event=reject where=memory reason=memory-is-current" in caplog.text


def test_patch_blank_and_over_cap(c, caplog):
    mid = _post(c).json()["id"]
    with caplog.at_level(logging.INFO):
        _assert_err(c.patch(f"/api/memory/{mid}", json={"text": "  "}), 422, "blank-memory")
        _assert_err(c.patch(f"/api/memory/{mid}", json={"text": "字" * 801}), 422, "memory-full")
    assert "reason=blank-memory" in caplog.text and "reason=memory-full" in caplog.text


def test_revert_over_cap(c):
    mid = _post(c, text="字" * 800).json()["id"]
    c.post(f"/api/memory/{mid}/archive")
    _post(c, text="字" * 800)
    _assert_err(c.post(f"/api/memory/{mid}/revert"), 422, "memory-full")


def _turns(c):
    return c.get("/api/sessions/solo").json()["turns"]


def test_session_turn_carries_memories_until_archived(c):
    mid = _post(c, scope="work", slug="mini", session="solo", seq=0, quote="一句").json()["id"]
    turns = _turns(c)
    assert turns[0]["memories"] == [{"id": mid, "scope": "work"}]
    assert turns[1]["memories"] == []
    c.post(f"/api/memory/{mid}/archive")
    assert _turns(c)[0]["memories"] == []


def test_edited_memory_stays_on_the_turn_with_the_new_id(c):
    mid = _post(c, slug="mini", session="solo", seq=0, quote="一句").json()["id"]
    new = c.patch(f"/api/memory/{mid}", json={"text": "改"}).json()["id"]
    assert _turns(c)[0]["memories"] == [{"id": new, "scope": "author"}]


def test_longest_turn_as_is_gets_memory_full_not_a_bare_422(c):
    r = _post(c, text="長" * MAX_CHAT_CHARS, slug="mini", session="long", seq=0, quote="長" * MAX_CHAT_CHARS)
    _assert_err(r, 422, "memory-full")


def test_longest_turn_quote_with_short_text_passes(c):
    r = _post(c, text="短", slug="mini", session="long", seq=0, quote="長" * MAX_CHAT_CHARS)
    assert r.status_code == 201


def test_title_follows_the_rest_of_the_dashboard(data):
    url, d = data
    conn = db.connect(url)
    with conn:
        sid = repo.ensure_story(conn, "untitled", None, 1.0)
        v, _ = repo.add_source_version(conn, sid, "文", 1.0)
        aid, _ = repo.add_artifact(conn, sid, v, "analysis", 1, {"title": "分析給的題"}, {}, 1.0)
        repo.set_current(conn, sid, "analysis", aid)
    conn.close()
    with TestClient(den_app.create_app(url, d, run_factory=Run()), base_url="http://127.0.0.1") as client:
        client.headers.update(_auth(d))
        row = _post(client, scope="work", slug="untitled").json()
        assert row["title"] == "分析給的題"
        assert client.get("/api/memory").json()["memories"][0]["title"] == "分析給的題"
