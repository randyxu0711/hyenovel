"""POST /discuss/{slug}:一輪討論的行為契約。

假 chat 一律注入(chat_factory),絕不 spawn 真 claude。TestClient 會等 app 跑完才回應,
「卡住」與「中途斷線」用執行緒 / 直接驅動 ASGI 測(同 test_app 的 events 斷線測試)。
"""
import asyncio
import json
import logging
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den.config import MAX_QUOTE_CHARS, MAX_QUOTES
from den.runner import RunResult
from den.tests.conftest import FIXTURES
from den.tests.test_app import Run, _auth, _poll
from marrow import db, importer, repo

_MESSAGES = {"ok": None, "usage-limit": "用量已達上限", "crash": "工人掛了",
             "transient": "暫時性錯誤", "timeout": "逾時", "auth": "沒登入"}


class FakeChat:
    """chat_factory:記下每次 (system, user);可設 deltas / outcome / 卡住(只卡下一次呼叫)。"""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.deltas = ["A", "B"]
        self.outcome = "ok"
        self.hang = False
        self.started = threading.Event()   # 卡住的那次已吐出第一個 delta
        self.release = threading.Event()
        self.override = None               # 換掉整個 chat(測例外 / 無 result)
        self.closed = threading.Event()    # 卡住的那次 generator 的 finally 跑過

    def __call__(self):
        return self.chat

    async def chat(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.override:
            async for ev in self.override():
                yield ev
            return
        hang, self.hang = self.hang, False
        try:
            for d in self.deltas:
                yield ("delta", d)
                if hang:
                    self.started.set()
                    while not self.release.is_set():
                        await asyncio.sleep(0.01)
            text = "".join(self.deltas) if self.outcome == "ok" else None
            yield ("result", RunResult(self.outcome, None, "", "claude-x",
                                       {"output": 7, "cost_usd": 0.01}, 42,
                                       _MESSAGES[self.outcome], 1, text))
        finally:
            if hang:
                self.closed.set()


@pytest.fixture
def fake_chat():
    return FakeChat()


@pytest.fixture
def c(data, fake_chat):
    """第二篇已分析的故事 other = mini 的複本(假 critique 的引文對不上別的原文)。"""
    url, d = data
    shutil.copytree(FIXTURES / "mini", d / "other")
    conn = db.connect(url)
    importer.import_story(conn, d / "other", 1.0)
    conn.close()
    with TestClient(den_app.create_app(url, d, run_factory=Run(),
                                       chat_factory=fake_chat),
                    base_url="http://127.0.0.1") as client:
        client.headers.update(_auth(d))
        yield client


def post_raw(c, slug, sid, message="結尾太快?", anchors=()):
    return c.post(f"/api/discuss/{slug}",
                  json={"session_id": sid, "message": message, "anchors": list(anchors)})


def post_discuss(c, slug, sid, message, anchors=()) -> list[dict]:
    r = post_raw(c, slug, sid, message, anchors)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def first_turn(c, slug="mini") -> str:
    return post_discuss(c, slug, None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]


def turns(c, slug="mini"):
    return c.get(f"/api/stories/{slug}/transcript").json()["turns"]


def in_loop(c, fn):
    """sqlite 連線綁在 app 的事件迴圈執行緒:DB 斷言要在那條執行緒上跑。"""
    return c.portal.call(lambda: fn(c.app.state.mgr.conn))


def _session_rows(conn, sid, slug="mini"):
    d = repo.discussion_by_external(conn, repo.story_by_slug(conn, slug)["id"], sid)
    return d, repo.utterances(conn, d["id"])


# ── 成功路徑 ──

def test_first_turn_creates_session_and_persists_both(c):
    evs = post_discuss(c, "mini", None, "結尾太快?", ["b3"])
    assert [e["event"] for e in evs] == ["token", "token", "message", "done"]
    assert [e["data"] for e in evs[:2]] == [{"text": "A"}, {"text": "B"}]
    sid = evs[-1]["data"]["session_id"]
    assert len(sid) == 12
    assert evs[2]["data"] == {"role": "assistant", "text": "AB", "session_id": sid, "mode": "slow",
                               "character": "hyena"}
    assert evs[3]["data"] == {"ok": True, "session_id": sid}
    ts = turns(c)
    assert [(t["role"], t["text"], t["session"]) for t in ts] == \
           [("user", "結尾太快?", sid), ("assistant", "AB", sid)]
    assert ts[0]["anchors"] == ["b3"]


def test_second_turn_sends_history(c, fake_chat):
    sid = first_turn(c)
    evs = post_discuss(c, "mini", sid, "那改慢呢")
    assert evs[-1]["data"] == {"ok": True, "session_id": sid}
    system, user = fake_chat.calls[-1]
    assert "<source>" in system                       # 素材 = companion 那份
    assert "作者:結尾太快?" in user and "你:AB" in user
    assert user.rstrip().endswith("那改慢呢")
    assert fake_chat.calls[0][1] == "結尾太快?"         # 第一輪沒有歷史
    assert [t["text"] for t in turns(c)] == ["結尾太快?", "AB", "那改慢呢", "AB"]


def test_turn_rows_and_session_metadata(c):
    sid = first_turn(c)
    post_discuss(c, "mini", sid, "再一輪")
    d, us = in_loop(c, lambda conn: _session_rows(conn, sid))
    assert (d["home"], d["client"]) == ("web", "web")
    assert [u["seq"] for u in us] == [0, 1, 2, 3]
    assert {u["origin"] for u in us} == {"den"}
    fp = in_loop(c, lambda conn: repo.current_artifact(
        conn, repo.story_by_slug(conn, "mini")["id"], "analysis")["sha256"])
    assert {u["analysis_fp"] for u in us} == {fp}
    assert d["ended_at"] == max(u["ts"] for u in us)   # 最後活動時間


def test_assistant_utterance_records_usage(c):
    sid = first_turn(c)
    user, asst = in_loop(c, lambda conn: _session_rows(conn, sid))[1]
    assert user["usage"] is None
    assert asst["usage"] == {"output": 7, "cost_usd": 0.01, "duration_ms": 42, "model": "claude-x"}


def test_turn_logged_without_text(c, caplog):
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        first_turn(c)
    assert "event=discuss-turn slug=mini outcome=ok ms=42" in caplog.text
    assert "結尾太快" not in caplog.text


# ── 失敗:這輪沒發生過 ──

def test_failed_turn_writes_nothing(c, fake_chat):
    fake_chat.outcome = "crash"
    evs = post_discuss(c, "mini", None, "x")
    assert [e["event"] for e in evs] == ["token", "token", "error"]
    assert evs[-1]["data"]["recoverable"] is False
    assert turns(c) == []                               # 沒有空殼局、沒有半輪
    assert in_loop(c, lambda conn: conn.execute("SELECT COUNT(*) FROM discussion").fetchone()[0]) == 0


def test_failed_later_turn_keeps_earlier(c, fake_chat):
    sid = first_turn(c)
    fake_chat.outcome = "timeout"
    evs = post_discuss(c, "mini", sid, "y")
    assert evs[-1]["event"] == "error"
    assert len(turns(c)) == 2


def test_usage_limit_maps_to_error_event(c, fake_chat):
    fake_chat.outcome = "usage-limit"
    evs = post_discuss(c, "mini", None, "x")
    assert evs[-1] == {"event": "error", "data": {"where": "discuss", "message": "用量已達上限",
                                                  "recoverable": True, "code": "usage-limit"}}


@pytest.mark.parametrize("outcome, recoverable", [
    ("transient", True), ("timeout", True), ("usage-limit", True),
    ("auth", False), ("crash", False)])
def test_error_recoverable_mapping(c, fake_chat, outcome, recoverable):
    fake_chat.outcome = outcome
    evs = post_discuss(c, "mini", None, "x")
    assert evs[-1]["data"]["recoverable"] is recoverable
    assert evs[-1]["data"]["code"] == ("usage-limit" if outcome == "usage-limit" else "chat-failed")


# ── Review Focus ──

def test_disconnect_mid_turn_kills_worker_and_writes_nothing(data, fake_chat):
    """直接驅動 ASGI:收到第一塊 token 就回 http.disconnect;chat generator 必須被關(工人死)、
    逐字仍空、streams 歸 0。TestClient 等 app 跑完才回應,測不到中途斷線。"""
    url, d = data
    app = den_app.create_app(url, d, run_factory=Run(), chat_factory=fake_chat)
    fake_chat.hang = True

    async def main():
        async with app.router.lifespan_context(app):
            conn = app.state.mgr.conn
            st = repo.story_by_slug(conn, "mini")
            d_id = repo.ensure_discussion(conn, st["id"], "s1", "web", "web", 1.0)
            conn.commit()
            got_body = asyncio.Event()
            sent = []
            body = json.dumps({"session_id": "s1", "message": "x", "anchors": []}).encode()

            async def receive():
                if not sent:
                    sent.append(1)
                    return {"type": "http.request", "body": body, "more_body": False}
                await got_body.wait()
                return {"type": "http.disconnect"}

            async def send(msg):
                if msg["type"] == "http.response.body" and msg.get("body"):
                    got_body.set()
            path = "/api/discuss/mini"
            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                     "http_version": "1.1", "method": "POST", "scheme": "http",
                     "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                     "headers": [(b"host", b"127.0.0.1"), (b"authorization", f"Bearer {app.state.token}".encode()),
                                 (b"content-type", b"application/json")],
                     "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8788)}
            await asyncio.wait_for(app(scope, receive, send), 5)
            assert got_body.is_set()
            assert fake_chat.closed.is_set()            # finally 跑過 = 工人被殺
            assert not fake_chat.release.is_set()       # 不是自己跑完的
            assert repo.utterances(conn, d_id) == []
            assert app.state.streams == 0
            assert not app.state.chat_locks["mini/s1"].locked()
    asyncio.run(main())


def test_body_aclose_at_yield_closes_chat(c, fake_chat):
    """generator 停在 yield 時被 aclose(ASGI ≥2.4 斷線、或被回收):要一路關到 chat、放鎖、streams 歸 0。
    上面那條走的是 2.3 的取消路徑(uvicorn 現況),這條守 aclosing 本身。"""
    sid = first_turn(c)
    fake_chat.hang = True
    lock = asyncio.Lock()

    async def drive():
        conn = c.app.state.mgr.conn
        turn = den_app.discuss.prepare_turn(conn, "mini", sid)
        den_app.discuss.pick_character(conn, turn, None, None)
        events = den_app.discuss.run_turn(conn, c.app.state.chat, turn, "x", [])
        gen = den_app._chat_stream(c.app.state, lock, events)
        first = await anext(gen)
        busy = c.app.state.streams
        await gen.aclose()
        # 還握著 events:這時 chat 已關,靠的是 aclosing 而不是 GC 回收時的 finalizer
        return first, busy, fake_chat.closed.is_set(), lock.locked()
    try:
        first, busy, closed, locked = c.portal.call(drive)
    finally:
        fake_chat.release.set()
    assert json.loads(first[6:]) == {"event": "token", "data": {"text": "A"}}
    assert busy == 1 and c.app.state.streams == 0
    assert closed and not locked
    assert len(turns(c)) == 2                           # 被關掉的那輪沒落盤


def test_same_session_concurrent_turn_409(c, fake_chat, caplog):
    a, b = first_turn(c), first_turn(c)
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", a, "卡住的那輪"), daemon=True)
    t.start()
    try:   # 斷言失敗也要放行,否則 TestClient 收尾會等那輪等到天荒地老
        assert fake_chat.started.wait(5)
        with caplog.at_level(logging.INFO, logger="hyenovel"):
            r = post_raw(c, "mini", a, "插隊")
        assert r.status_code == 409
        assert "event=reject where=discuss reason=busy" in caplog.text
        assert post_discuss(c, "mini", b, "別局")[-1]["event"] == "done"   # 不同局不受影響
    finally:
        fake_chat.release.set()
    t.join(5)
    assert not t.is_alive()
    assert [x["text"] for x in turns(c) if x["session"] == a][-2:] == ["卡住的那輪", "AB"]
    assert post_discuss(c, "mini", a, "放開後")[-1]["event"] == "done"   # 鎖已釋放


def test_session_of_other_story_404(c, caplog):
    sid = first_turn(c, "mini")
    assert post_discuss(c, "other", None, "x")[-1]["event"] == "done"   # other 本身可聊
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert post_raw(c, "other", sid).status_code == 404
        assert post_raw(c, "mini", "nosuchsess").status_code == 404
    assert caplog.text.count("event=reject where=discuss reason=unknown-session") == 2


def test_chat_stream_counts_as_activity(c, fake_chat):
    sid = first_turn(c)
    fake_chat.hang = True
    t = threading.Thread(target=post_discuss, args=(c, "mini", sid, "x"), daemon=True)
    t.start()
    try:
        assert fake_chat.started.wait(5)
        assert c.app.state.streams == 1
    finally:
        fake_chat.release.set()
    t.join(5)
    assert _poll(lambda: c.app.state.streams == 0)


def test_busy_lock_at_stream_start_yields_error(c):
    """端點判過沒鎖、串流開始前別人先拿到鎖(極窄的競態):不排隊、回錯誤事件、不碰這輪。"""
    lock, pulled = asyncio.Lock(), []

    async def events():
        pulled.append(1)
        yield {"event": "done", "data": {}}

    async def drive():
        await lock.acquire()
        try:
            return [x async for x in den_app._chat_stream(c.app.state, lock, events())]
        finally:
            lock.release()
    out = c.portal.call(drive)
    assert [json.loads(x[6:]) for x in out] == [{"event": "error", "data": {
        "where": "discuss", "message": "這一局還有一輪在跑", "recoverable": True, "code": "busy"}}]
    assert pulled == [] and c.app.state.streams == 0


# ── 4xx(串流開始前判)──

@pytest.mark.parametrize("body", [{"message": "x", "mode": "doubt"}, {"message": "x" * 8001},
                                  {"message": "x", "home": "cli"},
                                  {"message": "x", "anchors": ["a"] * 9},
                                  {"message": "x", "session_id": "s" * 65}])
def test_bad_body_422(c, fake_chat, body):
    assert c.post("/api/discuss/mini", json=body).status_code == 422
    assert fake_chat.calls == []


def test_max_body_ok(c):
    evs = post_discuss(c, "mini", None, "x" * 8000, ["a"] * 8)
    assert evs[-1]["event"] == "done"


def test_bad_slug_422(c, caplog):
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert post_raw(c, "-x", None).status_code == 422
    assert "event=reject where=discuss reason=bad-slug" in caplog.text


def test_unknown_slug_404(c, caplog):
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert post_raw(c, "nope", None).status_code == 404
    assert "event=reject where=discuss reason=unknown-slug" in caplog.text


def test_requires_token(c):
    c.headers.pop("Authorization")
    assert post_raw(c, "mini", None).status_code == 401


# ── 例外轉 error 事件(整輪不落盤) ──

def test_chat_raising_yields_error_and_persists_nothing(c, fake_chat, caplog):
    async def boom():
        raise OSError("spawn failed")
        yield   # pragma: no cover
    fake_chat.override = boom
    caplog.set_level(logging.INFO)
    evs = post_discuss(c, "mini", None, "秘密提問")
    assert evs[-1]["event"] == "error"
    assert evs[-1]["data"]["where"] == "discuss" and evs[-1]["data"]["recoverable"] is False
    assert evs[-1]["data"]["code"] == "no-response"
    assert turns(c) == []
    assert "event=discuss-turn-failed slug=mini stage=chat" in caplog.text
    assert "秘密提問" not in caplog.text


def test_chat_without_result_yields_error(c, fake_chat):
    async def empty():
        yield ("delta", "x")
    fake_chat.override = empty
    evs = post_discuss(c, "mini", None, "q")
    assert [e["event"] for e in evs] == ["token", "error"]
    assert evs[-1]["data"]["recoverable"] is False and evs[-1]["data"]["code"] == "no-response"
    assert turns(c) == []


def test_commit_failure_yields_error_and_does_not_log_ok(c, monkeypatch, caplog):
    import sqlite3

    def busy(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(repo, "add_utterance", busy)
    caplog.set_level(logging.INFO)
    evs = post_discuss(c, "mini", None, "q")
    assert evs[-1]["event"] == "error" and evs[-1]["data"]["recoverable"] is False
    assert evs[-1]["data"]["code"] == "commit-failed"
    assert "message" not in [e["event"] for e in evs]
    monkeypatch.undo()
    assert turns(c) == []
    assert "outcome=ok" not in caplog.text
    assert "stage=commit" in caplog.text


# ── companion(第 1 批) ──

def _mini_id(conn):
    return repo.story_by_slug(conn, "mini")["id"]


def test_unanalyzed_story_can_chat_with_source_only(c, fake_chat):
    slug = c.post("/api/stories", json={"text": "未分析的稿。"}).json()["slug"]
    evs = post_discuss(c, slug, None, "你覺得呢")
    assert evs[-1]["event"] == "done"
    system = fake_chat.calls[-1][0]
    assert "未分析的稿。" in system and "你讀的時候注意到的結構" not in system
    sid = evs[-1]["data"]["session_id"]
    us = in_loop(c, lambda conn: _session_rows(conn, sid, slug))[1]
    assert {u["analysis_fp"] for u in us} == {None}


def test_system_prompt_has_no_feedback_or_conclusions(c, fake_chat):
    def judged(conn):
        sid_ = _mini_id(conn)
        fb = repo.current_artifact(conn, sid_, "feedback")
        return fb["body"] if fb else None, [x["text"] for x in repo.conclusions(conn, sid_)]
    fb, concl = in_loop(c, judged)
    first_turn(c)
    system = fake_chat.calls[-1][0]
    assert "你讀的時候注意到的結構" in system
    assert "編輯回饋" not in system and "已留下的結論" not in system
    for text in concl:
        assert text not in system
    if fb:
        for p in fb.get("key_points") or ():
            assert p["body"] not in system


def test_mode_defaults_to_slow_and_is_recorded(c, fake_chat):
    sid = first_turn(c)
    assert "你的讀法:慢讀" in fake_chat.calls[-1][0]
    user, asst = in_loop(c, lambda conn: _session_rows(conn, sid))[1]
    assert (user["mode"], asst["mode"]) == (None, "slow")


def test_mode_carries_over_within_session(c, fake_chat):
    evs = [json.loads(line[6:]) for line in c.post("/api/discuss/mini", json={
        "message": "講重點", "mode": "direct"}).text.splitlines() if line.startswith("data: ")]
    sid = evs[-1]["data"]["session_id"]
    assert "你的讀法:直說" in fake_chat.calls[-1][0]
    post_discuss(c, "mini", sid, "然後呢")
    assert "你的讀法:直說" in fake_chat.calls[-1][0]
    assert in_loop(c, lambda conn: _session_rows(conn, sid))[1][-1]["mode"] == "direct"


def test_empty_message_stores_only_assistant(c, fake_chat):
    from den.discuss import OPENER
    evs = post_discuss(c, "mini", None, "")
    sid = evs[-1]["data"]["session_id"]
    assert fake_chat.calls[-1][1] == OPENER
    us = in_loop(c, lambda conn: _session_rows(conn, sid))[1]
    assert [(u["seq"], u["role"]) for u in us] == [(0, "assistant")]
    post_discuss(c, "mini", sid, "嗯")
    us = in_loop(c, lambda conn: _session_rows(conn, sid))[1]
    assert [(u["seq"], u["role"]) for u in us] == [(0, "assistant"), (1, "user"), (2, "assistant")]
    assert "作者:\n" not in fake_chat.calls[-1][1]


def test_home_and_client_recorded(c):
    r = c.post("/api/discuss/mini", json={"message": "q", "home": "mcp",
                                      "client": {"name": "claude-code", "version": "2.1.314"}})
    sid = [json.loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: ")][-1]["data"]["session_id"]
    d = in_loop(c, lambda conn: _session_rows(conn, sid))[0]
    assert (d["home"], d["client"]) == ("mcp", "claude-code")


def test_discuss_mode_literal_matches_companion_modes():
    import typing
    from den.companion import MODES
    ann = den_app.DiscussIn.model_fields["mode"].annotation
    assert typing.get_args(typing.get_args(ann)[0]) == MODES


def test_empty_message_mid_conversation_asks_to_continue(c, fake_chat):
    from den.discuss import CONTINUE, OPENER
    sid = first_turn(c)
    post_discuss(c, "mini", sid, "")
    user = fake_chat.calls[-1][1]
    assert user.rstrip().endswith(CONTINUE) and OPENER not in user


def _post(c, body):
    return c.post("/api/discuss/mini", json={"message": "q", **body})


def _last_assistant(c, evs):
    sid = evs[-1]["data"]["session_id"]
    return in_loop(c, lambda conn: _session_rows(conn, sid))[1][-1]


def test_unknown_character_is_422_before_stream(c, fake_chat):
    r = _post(c, {"character": "dragon"})
    assert r.status_code == 422 and r.json()["code"] == "unknown-character"
    assert fake_chat.calls == []


def test_mcp_mode_only_stores_matching_character(c, fake_chat):
    r = _post(c, {"mode": "direct", "home": "mcp"})
    evs = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    row = _last_assistant(c, evs)
    assert (row["character"], row["mode"]) == ("buffalo", "direct")
    assert evs[-2]["data"]["character"] == "buffalo"


def test_character_carries_over_and_overrides(c, fake_chat):
    evs = [json.loads(line[6:]) for line in _post(c, {"character": "deer"}).text.splitlines()
           if line.startswith("data: ")]
    sid = evs[-1]["data"]["session_id"]
    assert (_last_assistant(c, evs)["character"], _last_assistant(c, evs)["mode"]) == ("deer", "imaginative")
    post_discuss(c, "mini", sid, "然後")
    assert _last_assistant(c, evs)["character"] == "deer"
    assert "你的讀法:想像" in fake_chat.calls[-1][0]


def test_legacy_session_with_only_mode_keeps_that_mode(c, fake_chat):
    sid = first_turn(c)
    def strip(conn):
        with conn:
            conn.execute("UPDATE utterance SET character = NULL, mode = 'direct' WHERE role = 'assistant'")
    in_loop(c, strip)
    post_discuss(c, "mini", sid, "再說")
    assert "你的讀法:直說" in fake_chat.calls[-1][0]


def test_get_themes_route(c):
    r = c.get("/api/themes")
    body = r.json()
    assert r.status_code == 200 and body["default"] == "olive"
    assert [t["id"] for t in body["themes"]] == ["grassland", "olive"]


def test_get_characters_route(c):
    r = c.get("/api/characters")
    body = r.json()
    assert r.status_code == 200 and body["default"] == "hyena"
    assert {x["id"] for x in body["characters"]} == {"hyena", "buffalo", "deer"}


# ── 帶這段(quotes) ──

def test_quote_not_in_source_rejected_before_stream(c, fake_chat):
    r = _post(c, {"quotes": ["原文裡根本沒有這句"]})
    assert r.status_code == 422 and r.json()["code"] == "quote-not-in-source"
    assert fake_chat.calls == []


def test_quote_too_long_rejected(c, fake_chat):
    r = _post(c, {"quotes": ["他" * (MAX_QUOTE_CHARS + 1)]})
    assert r.status_code == 422 and r.json()["code"] == "quote-too-long"
    assert fake_chat.calls == []


def test_blank_quote_rejected(c, fake_chat):
    r = _post(c, {"quotes": ["  "]})
    assert r.status_code == 422 and r.json()["code"] == "quote-not-in-source"


def test_quotes_reach_companion_and_are_stored_on_user_turn(c, fake_chat):
    r = _post(c, {"quotes": ["他把燈關了。"]})
    assert r.status_code == 200
    assert "作者指著原文的這幾段:\n「他把燈關了。」" in fake_chat.calls[-1][1]
    sid = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")][-1]["data"]["session_id"]
    rows = in_loop(c, lambda conn: _session_rows(conn, sid))[1]
    assert rows[0]["quotes"] == ["他把燈關了。"] and rows[1]["quotes"] is None
    post_discuss(c, "mini", sid, "再說")
    assert "「他把燈關了。」" in fake_chat.calls[-1][1]   # 歷史裡的舊引文照樣還原


def test_quotes_matched_with_loose_punctuation(c, fake_chat):
    r = _post(c, {"quotes": ["他走進門.屋裡沒有人."]})   # 原文是全形句點
    assert r.status_code == 200


def test_quote_needs_message(c, fake_chat):
    for msg in ("", "  "):
        r = _post(c, {"message": msg, "quotes": ["他把燈關了。"]})
        assert r.status_code == 422 and r.json()["code"] == "quote-needs-message"
    assert fake_chat.calls == []


def test_too_many_quotes(c, fake_chat):
    r = _post(c, {"quotes": ["他把燈關了。"] * (MAX_QUOTES + 1)})
    assert r.status_code == 422 and r.json()["code"] == "too-many-quotes"
    assert fake_chat.calls == []
