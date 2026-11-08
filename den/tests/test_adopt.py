from den import companion, discuss, stories
from den.tests.test_app_discuss import SEA, c, events, fake_chat, free, in_loop  # noqa: F401
from marrow import repo

MOUNTAIN = "山很高,石頭一路滾下來。"


def adopt(c, sid, n=1):
    return c.post(f"/api/sessions/{sid}/attachments/{n}/adopt")


def _two(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    events(free(c, sid, "還有一篇", attach={"name": "山", "text": MOUNTAIN}))
    return sid


def test_adopt_creates_work_and_binds_session(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    r = adopt(c, sid)
    assert r.status_code == 201
    got = r.json()
    assert (got["title"], got["version"], got["reused"]) == ("海", 1, False)
    turn = in_loop(c, lambda conn: discuss.prepare_turn(conn, None, sid))
    assert turn["slug"] == got["slug"] and turn["ctx"]["source"].strip() == SEA
    assert in_loop(c, lambda conn: repo.attachments(conn, repo.discussion_by_session(conn, sid)["id"]))[0][
        "source_version_id"] is not None


def test_adopted_quotes_still_pass_gate(c, fake_chat):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    adopt(c, sid)
    assert events(free(c, sid, "這句", quotes=["她站在堤上沒有動"]))[-1]["event"] == "done"


def test_after_adopt_text_appears_once_as_work_source(c, fake_chat):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    adopt(c, sid)
    events(free(c, sid, "然後"))
    system = fake_chat.calls[-1][0]
    assert system.count(SEA) == 1 and "作者丟進來的稿" not in system and "# 《海》" in system


def test_other_attachments_stay_after_adopt(c, fake_chat):
    sid = _two(c)
    adopt(c, sid, 1)
    events(free(c, sid, "那山呢", quotes=["石頭一路滾下來"]))
    names = [x.name for x in companion.assemble(
        in_loop(c, lambda conn: stories.companion_context(conn, None, repo.discussion_by_session(conn, sid)["id"])),
        {"id": "hyena", "voice": "", "reading": "讀"}).layers]
    assert "attachment_2" in names and "attachment_1" not in names
    assert MOUNTAIN in fake_chat.calls[-1][0]


def test_adopt_reuses_existing_work_with_same_text(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    first = adopt(c, sid).json()
    sid2 = events(free(c, attach={"name": "海二", "text": SEA}))[-1]["data"]["session_id"]
    again = adopt(c, sid2).json()
    assert again["reused"] and again["slug"] == first["slug"]

    def check(conn):
        d = repo.discussion_by_session(conn, sid2)
        latest = repo.latest_source_version(conn, d["story_id"])
        return d["slug"], repo.attachments(conn, d["id"])[0]["source_version_id"] == latest["id"]
    assert in_loop(c, check) == (first["slug"], True)


def test_adopt_on_bound_session_rejected(c):
    sid = _two(c)
    adopt(c, sid, 1)
    r = adopt(c, sid, 2)
    assert (r.status_code, r.json()["code"]) == (422, "bound-session")


def test_adopt_twice_conflict(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    adopt(c, sid)
    r = adopt(c, sid)
    assert (r.status_code, r.json()["code"]) == (409, "already-adopted")


def test_adopt_unknown(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    assert adopt(c, sid, 9).json()["code"] == "unknown-attachment"
    assert adopt(c, "nosuch").json()["code"] == "unknown-session"


def test_adopt_bad_source_422(c, monkeypatch):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    monkeypatch.setattr(stories.config, "MAX_SOURCE_BYTES", 3)
    r = adopt(c, sid)
    assert (r.status_code, r.json()["code"]) == (422, "bad-source")
    assert in_loop(c, lambda conn: repo.discussion_by_session(conn, sid)["story_id"]) is None


def test_adopt_busy(c):
    import types
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    c.app.state.chat_locks[sid] = types.SimpleNamespace(locked=lambda: True)
    assert adopt(c, sid).status_code == 409


def test_adopt_starts_no_job(c):
    sid = events(free(c, attach={"name": "海", "text": SEA}))[-1]["data"]["session_id"]
    slug = adopt(c, sid).json()["slug"]
    assert in_loop(c, lambda conn: conn.execute(
        "SELECT COUNT(*) FROM job WHERE story_id = ?", (repo.story_by_slug(conn, slug)["id"],)).fetchone()[0]) == 0
