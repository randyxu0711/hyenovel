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
                                       chat_factory=fake_chat)) as client:
        client.headers.update(_auth(d))
        yield client


def post_raw(c, slug, sid, message="結尾太快?", anchors=()):
    return c.post(f"/discuss/{slug}",
                  json={"session_id": sid, "message": message, "anchors": list(anchors)})


def post_discuss(c, slug, sid, message, anchors=()) -> list[dict]:
    r = post_raw(c, slug, sid, message, anchors)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def first_turn(c, slug="mini") -> str:
    return post_discuss(c, slug, None, "結尾太快?", ["b3"])[-1]["data"]["session_id"]


def turns(c, slug="mini"):
    return c.get(f"/stories/{slug}/transcript").json()["turns"]


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
    assert evs[2]["data"] == {"role": "assistant", "text": "AB", "session_id": sid}
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
    assert "<source>" in system                       # 素材 = open_discussion 那份
    assert "作者:結尾太快?" in user and "編輯:AB" in user
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
                                                  "recoverable": True}}


@pytest.mark.parametrize("outcome, recoverable", [
    ("transient", True), ("timeout", True), ("usage-limit", True),
    ("auth", False), ("crash", False)])
def test_error_recoverable_mapping(c, fake_chat, outcome, recoverable):
    fake_chat.outcome = outcome
    evs = post_discuss(c, "mini", None, "x")
    assert evs[-1]["data"]["recoverable"] is recoverable


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
            path = "/discuss/mini"
            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                     "http_version": "1.1", "method": "POST", "scheme": "http",
                     "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                     "headers": [(b"authorization", f"Bearer {app.state.token}".encode()),
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
        "where": "discuss", "message": "這一局還有一輪在跑", "recoverable": True}}]
    assert pulled == [] and c.app.state.streams == 0


# ── 4xx(串流開始前判)──

@pytest.mark.parametrize("body", [{"message": ""}, {"message": "x" * 8001},
                                  {"message": "x", "anchors": ["a"] * 9},
                                  {"message": "x", "session_id": "s" * 65}])
def test_bad_body_422(c, fake_chat, body):
    assert c.post("/discuss/mini", json=body).status_code == 422
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


def test_not_analyzed_409(c, caplog, fake_chat):
    slug = c.post("/stories", json={"text": "未分析。"}).json()["slug"]
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        r = post_raw(c, slug, None)
    assert r.status_code == 409 and r.json() == {"detail": "這篇還沒分析完成"}
    assert "event=reject where=discuss reason=not-analyzed" in caplog.text
    assert fake_chat.calls == []


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
    assert turns(c) == []
    assert "event=discuss-turn-failed slug=mini stage=chat" in caplog.text
    assert "秘密提問" not in caplog.text


def test_chat_without_result_yields_error(c, fake_chat):
    async def empty():
        yield ("delta", "x")
    fake_chat.override = empty
    evs = post_discuss(c, "mini", None, "q")
    assert [e["event"] for e in evs] == ["token", "error"]
    assert evs[-1]["data"]["recoverable"] is False
    assert turns(c) == []


def test_commit_failure_yields_error_and_does_not_log_ok(c, monkeypatch, caplog):
    import sqlite3

    def busy(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(repo, "add_utterance", busy)
    caplog.set_level(logging.INFO)
    evs = post_discuss(c, "mini", None, "q")
    assert evs[-1]["event"] == "error" and evs[-1]["data"]["recoverable"] is False
    assert "message" not in [e["event"] for e in evs]
    monkeypatch.undo()
    assert turns(c) == []
    assert "outcome=ok" not in caplog.text
    assert "stage=commit" in caplog.text
