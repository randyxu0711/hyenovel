"""den.app 行為契約:安全三件套、路由狀態碼、SSE 必收尾、單一實例、worker 監督。

TestClient 當 context manager 才會跑 lifespan;run_factory 一律注入假的,絕不 spawn 真 claude。
假 run 用 threading.Event 放行:TestClient 的事件迴圈在另一條執行緒,asyncio.Event 不能跨執行緒碰。
"""
import asyncio
import json
import logging
import os
import stat
import threading
import time

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den import config as den_config
from den.tests.test_pipeline import _analysis, _notes, ok
from marrow import db, repo
from marrow.workpacks import WORKPACKS


class Run:
    """run_factory:release 沒 set 就一直等(可被取消);set 了就依 schema 吐 ok。"""

    def __init__(self, released=True):
        self.release = threading.Event()
        if released:
            self.release.set()

    def __call__(self, on_proc):
        async def run(system_prompt, user_prompt, schema):
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            return ok(_analysis() if schema is WORKPACKS["analyst"].schema else _notes())
        return run


def _client(data, run=None, **kw):
    url, d = data
    return TestClient(den_app.create_app(url, d, run_factory=run or Run(), **kw))


def _auth(d):
    return {"Authorization": f"Bearer {(d / 'den.token').read_text().strip()}"}


def _wait_state(c, h, jid, want, limit=10.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        st = c.get(f"/jobs/{jid}", headers=h).json()["state"]
        if st == want:
            return
        time.sleep(0.02)
    raise AssertionError(f"job {jid} 等不到 {want}(現在 {st})")


def _read_sse(c, h, jid, limit=10.0) -> list[dict]:
    """讀完整條 SSE;串流不收尾就在 limit 秒後判失敗,不讓測試卡死。"""
    out: list = []

    def go():
        with c.stream("GET", f"/jobs/{jid}/events", headers=h) as r:
            out.append(r.headers["content-type"])
            for line in r.iter_lines():
                if line.startswith("data: "):
                    out.append(json.loads(line[6:]))
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(limit)
    assert not t.is_alive(), "SSE 沒有收尾"
    assert out[0].startswith("text/event-stream")
    return out[1:]


# ── 安全三件套 ──

def test_token_file_created_0600(data):
    with _client(data):
        p = data[1] / "den.token"
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
        assert len(p.read_text().strip()) >= 32


def test_token_file_reused_across_restarts(data):
    with _client(data):
        first = (data[1] / "den.token").read_text()
    with _client(data):
        assert (data[1] / "den.token").read_text() == first


def test_empty_token_file_regenerated(data):
    """建檔後、寫入前被殺 → 空檔:不可變成「Bearer 」就過,要重產且仍 0600。"""
    p = data[1] / "den.token"
    p.write_text("  \n")
    p.chmod(0o644)
    with _client(data) as c:
        assert c.get("/jobs/999", headers={"Authorization": "Bearer "}).status_code == 401
        tok = p.read_text().strip()
        assert len(tok) >= 32
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
        assert c.get("/jobs/999", headers=_auth(data[1])).status_code == 404
    assert [x.name for x in data[1].iterdir() if x.name.startswith(".den.token")] == []


def test_falsy_token_rejects_everything(data):
    with _client(data) as c:
        c.app.state.token = ""
        assert c.get("/jobs/999", headers={"Authorization": "Bearer "}).status_code == 401


def test_missing_token_401(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        assert c.get("/jobs/1").status_code == 401
        assert c.get("/jobs/1", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert caplog.text.count("event=reject where=token") == 2


def test_bad_origin_403(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = {**_auth(data[1]), "Origin": "http://evil.example/" + "x" * 500}
        assert c.get("/jobs/1", headers=h).status_code == 403
        h = {**_auth(data[1]), "Origin": "http://127.0.0.1:9999"}
        assert c.get("/jobs/1", headers=h).status_code == 403
    assert caplog.text.count("event=reject where=origin") == 2
    assert "x" * 100 not in caplog.text                 # Origin 原值截斷後才進 log


def test_no_origin_allowed(data):
    with _client(data, port=8899) as c:
        h = _auth(data[1])
        assert c.get("/jobs/999", headers=h).status_code == 404
        for o in ("http://127.0.0.1:8899", "http://localhost:8899"):
            assert c.get("/jobs/999", headers={**h, "Origin": o}).status_code == 404


# ── 路由 ──

def test_post_job_returns_202_and_persists(data):
    with _client(data, Run(released=False)) as c:
        h = _auth(data[1])
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h)
        assert r.status_code == 202
        body = r.json()
        assert body["runner"] == "claude"
        assert body["note"] == "會用你同一份訂閱額度"
        assert "estimate" in body
        jid = body["job_id"]
    c2 = db.connect(data[0])
    assert c2.execute("SELECT kind FROM job WHERE id = ?", (jid,)).fetchone()[0] == "critique"
    c2.close()


def test_post_job_twice_while_inflight_dedupes(data):
    with _client(data, Run(released=False)) as c:
        h = _auth(data[1])
        first = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()
        assert first["existing"] is False
        queued = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()
        _wait_state(c, h, first["job_id"], "running")
        running = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()
        for again in (queued, running):
            assert again["job_id"] == first["job_id"] and again["existing"] is True
            assert again["runner"] == "claude" and "estimate" in again
        c.app.state.mgr.cancel(first["job_id"])
    c2 = db.connect(data[0])
    assert c2.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
    c2.close()


def test_get_job_has_slug(data):
    with _client(data, Run(released=False)) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        assert c.get(f"/jobs/{jid}", headers=h).json()["slug"] == "mini"


def test_unknown_slug_404_mentions_importer(data):
    with _client(data) as c:
        r = c.post("/jobs", json={"kind": "critique", "slug": "nope"}, headers=_auth(data[1]))
        assert r.status_code == 404
        assert "python -m marrow.importer" in r.json()["detail"]


def test_invalid_slug_422(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        assert c.post("/jobs", json={"kind": "critique", "slug": "../x"}, headers=h).status_code == 422
        assert c.post("/jobs", json={"kind": "other", "slug": "mini"}, headers=h).status_code == 422
    assert "event=reject where=slug" in caplog.text


def test_get_job_has_no_raw_output(data):
    with _client(data) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "done")
        body = c.get(f"/jobs/{jid}", headers=h).json()
        for k in ("state", "step", "error_class", "detail"):
            assert k in body
        assert [a["step"] for a in body["attempts"]] == ["analyst", "reviewer"]
        assert set(body["attempts"][0]) == {"step", "n", "outcome", "model", "duration_ms", "tokens"}
        assert "raw_output" not in json.dumps(body)


def test_cancel_and_resume_status_codes(data, caplog):
    run = Run(released=False)
    with _client(data, run) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "running")
        assert c.post(f"/jobs/{jid}/resume", headers=h).status_code == 409   # running 不能續
        r = c.post(f"/jobs/{jid}/cancel", headers=h)
        assert (r.status_code, r.json()) == (200, {"ok": True})
        _wait_state(c, h, jid, "cancelled")
        assert c.post(f"/jobs/{jid}/resume", headers=h).json() == {"ok": True}
        run.release.set()
        _wait_state(c, h, jid, "done")
        assert c.post(f"/jobs/{jid}/cancel", headers=h).status_code == 409   # done 不能取消
        assert c.post(f"/jobs/{jid}/resume", headers=h).status_code == 409
        assert c.post("/jobs/999/cancel", headers=h).status_code == 404
        assert c.post("/jobs/999/resume", headers=h).status_code == 404
    assert "event=reject where=cancel" in caplog.text
    assert "event=reject where=resume" in caplog.text


# ── SSE ──

def test_events_sse_streams_until_done(data):
    with _client(data) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        evs = _read_sse(c, h, jid)
        assert evs[-1] == {"event": "done", "data": {"ok": True}}
        assert any(e["event"] == "phase" for e in evs)
        assert c.app.state.mgr.bus._subs == {}             # 收尾一定退訂


def test_events_terminal_without_replay_sends_state_and_ends(data):
    with _client(data) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "done")
        c.app.state.mgr.bus._events.pop(jid)               # 模擬 TTL 過了 / 上一個行程跑的
        evs = _read_sse(c, h, jid)
        assert evs == [{"event": "state", "data": {"state": "done", "step": "reviewer",
                                                   "error_class": None, "detail": None}}]
        assert c.app.state.mgr.bus._subs == {}


def test_events_ends_when_db_turns_terminal_without_event(data, monkeypatch):
    """worker 死在收尾前之類:bus 永遠不會發 done/error,靠定期看 DB 收尾。"""
    monkeypatch.setattr(den_app, "_SSE_POLL", 0.05)
    with _client(data, Run(released=False)) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "running")
        conn = c.app.state.mgr.conn

        async def fail_it():
            with conn:
                conn.execute("UPDATE job SET state = 'failed', error_class = 'crash' WHERE id = ?",
                             (jid,))
        res = []
        t = threading.Thread(target=lambda: res.extend(_read_sse(c, h, jid)), daemon=True)
        t.start()
        time.sleep(0.2)
        c.portal.call(fail_it)
        t.join(10)
        assert not t.is_alive()
        assert res[-1]["event"] == "state" and res[-1]["data"]["state"] == "failed"


def test_events_unsubscribes_on_client_disconnect(data):
    """直接驅動 ASGI:收到第一塊就回 http.disconnect,訂閱必須在有限時間內退掉。

    TestClient 會等 app 跑完才回應,測不到「中途斷線」,所以這裡不用它。
    """
    url, d = data
    app = den_app.create_app(url, d, run_factory=Run(released=False))

    async def main():
        async with app.router.lifespan_context(app):
            mgr = app.state.mgr
            jid = mgr.submit("mini")["job_id"]
            for _ in range(500):
                if mgr._step is not None:
                    break
                await asyncio.sleep(0.01)
            got_body = asyncio.Event()
            sent = []

            async def receive():
                if not sent:
                    sent.append(1)
                    return {"type": "http.request", "body": b"", "more_body": False}
                await got_body.wait()
                return {"type": "http.disconnect"}

            async def send(msg):
                if msg["type"] == "http.response.body" and msg.get("body"):
                    got_body.set()
            tok = app.state.token
            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                     "http_version": "1.1", "method": "GET", "scheme": "http",
                     "path": f"/jobs/{jid}/events", "raw_path": f"/jobs/{jid}/events".encode(),
                     "query_string": b"", "root_path": "",
                     "headers": [(b"authorization", f"Bearer {tok}".encode())],
                     "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8788)}
            await asyncio.wait_for(app(scope, receive, send), 5)
            assert got_body.is_set()
            assert jid not in mgr.bus._subs
    asyncio.run(main())


def test_events_unknown_job_404(data):
    with _client(data) as c:
        assert c.get("/jobs/999/events", headers=_auth(data[1])).status_code == 404


# ── 單一實例 / 啟動失敗 ──

def test_second_instance_refused(data):
    with _client(data):
        with pytest.raises(RuntimeError, match="已在執行"):
            with _client(data):
                pass
    with _client(data):                                     # 關掉後鎖已釋放
        pass


def test_no_claude_fails_startup_and_releases_lock(data, monkeypatch):
    monkeypatch.setattr(den_app, "find_claude", lambda: None)
    url, d = data
    with pytest.raises(RuntimeError, match="找不到 claude"):
        with TestClient(den_app.create_app(url, d)):
            pass
    with _client(data):
        pass


def test_default_factory_uses_found_claude(data, monkeypatch):
    monkeypatch.setattr(den_app, "find_claude", lambda: "/fake/claude")
    monkeypatch.setattr(den_app, "cli_version", lambda exe: "1.2.3")
    url, d = data
    with TestClient(den_app.create_app(url, d)) as c:
        mgr = c.app.state.mgr
        assert mgr._cli_version == "1.2.3"
        fn = mgr._run_factory(None)
        assert fn.args[0].exe == "/fake/claude"
        assert fn.keywords["timeout"] == den_app.PHASE_TIMEOUT
        chat = c.app.state.chat                             # 討論共用同一個 claude
        assert chat.func is den_app.stream_chat and chat.args[0].exe == "/fake/claude"
        assert chat.keywords == {"timeout": den_app.CHAT_TIMEOUT}


# ── worker 監督 ──

def test_worker_death_is_logged_and_restarted(caplog, monkeypatch):
    monkeypatch.setattr(den_app, "_RESTART_DELAY", 0)

    class Mgr:
        def __init__(self):
            self.calls = 0
            self.startups = 0
            self.second = asyncio.Event()

        def startup(self):
            self.startups += 1

        async def worker(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database is locked")
            self.second.set()
            await asyncio.Event().wait()

    async def main():
        m = Mgr()
        t = asyncio.create_task(den_app._supervise(m))
        await asyncio.wait_for(m.second.wait(), 5)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        return m
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        m = asyncio.run(main())
    assert m.calls == 2
    assert m.startups == 1                                  # 重起前把孤兒 running 收成 crash
    assert "event=worker-died" in caplog.text
    assert "database is locked" in caplog.text              # 有 traceback


# ── 切片 3:收原文 / 討論素材 / health / client → runner ──

def test_health_requires_token(data):
    with _client(data) as c:
        assert c.get("/health").status_code == 401


def test_health_returns_version(data):
    with _client(data) as c:
        r = c.get("/health", headers=_auth(data[1]))
    body = r.json()
    assert r.status_code == 200
    assert body["version"] == c.app.state.version and len(body["version"]) == 12
    assert body["pid"] == os.getpid() and body["busy"] is False


def test_post_stories_201(data):
    with _client(data) as c:
        r = c.post("/stories", json={"text": "他走進門。", "title": "T", "slug": None},
                   headers=_auth(data[1]))
    assert r.status_code == 201
    assert r.json()["slug"] == "d01" and r.json()["version"] == 1


def test_post_stories_422_blank(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        r = c.post("/stories", json={"text": "  ", "title": None, "slug": None},
                   headers=_auth(data[1]))
    assert r.status_code == 422 and "空白故事" in r.json()["detail"]
    assert "event=reject where=stories" in caplog.text


def test_post_stories_422_unknown_slug(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        r = c.post("/stories", json={"text": "x", "slug": "s07"}, headers=_auth(data[1]))
    assert r.status_code == 422
    assert "event=reject where=stories reason=unknown slug" in caplog.text


def test_post_job_records_client_and_runner(data):
    with _client(data) as c:
        h = _auth(data[1])
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini",
                                  "client": {"name": "claude-code", "version": "2.1.312"}}, headers=h)
        assert r.status_code == 202 and r.json()["runner"] == "claude"
        job = c.get(f"/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["params"] == {"client": {"name": "claude-code", "version": "2.1.312"},
                             "runner": "claude"}


def test_post_job_without_client_still_ok(data):
    with _client(data) as c:
        h = _auth(data[1])
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h)
        job = c.get(f"/jobs/{r.json()['job_id']}", headers=h).json()
    assert r.status_code == 202 and job["params"] == {"client": None, "runner": "claude"}


def test_post_job_client_name_too_long_422(data):
    with _client(data) as c:
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini",
                                  "client": {"name": "x" * 65}}, headers=_auth(data[1]))
    assert r.status_code == 422


def test_post_job_no_runner_503(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        c.app.state.available = ()
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=_auth(data[1]))
    assert r.status_code == 503 and "沒有可用的 runner" in r.json()["detail"]
    assert "event=reject where=runner" in caplog.text


# ── 生命週期:den.json、閒置退場 ──

class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _poll(pred, limit=5.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _idle_client(data, run=None, clk=None, fired=None):
    return _client(data, run, port=9999, idle_exit=10, idle_check=0.01, clock=clk,
                   on_idle=fired.set if fired is not None else None)


def test_den_json_written_and_removed(data):
    p = data[1] / "den.json"
    with _client(data, port=9999) as c:
        assert json.loads(p.read_text()) == {"port": 9999, "pid": os.getpid(),
                                             "version": c.app.state.version}
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert not p.exists()


def test_den_json_not_removed_if_other_pid(data):
    p = data[1] / "den.json"
    with _client(data):
        p.write_text(json.dumps({"port": 1, "pid": os.getpid() + 1, "version": "x"}))
    assert p.exists()


def test_den_json_unreadable_at_exit_is_left_alone(data):
    p = data[1] / "den.json"
    with _client(data):
        p.write_text("not json")
    assert p.read_text() == "not json"


def test_idle_exit_fires_after_threshold(data):
    clk, fired = Clock(), threading.Event()
    with _idle_client(data, clk=clk, fired=fired):
        time.sleep(0.1)
        assert not fired.is_set()
        clk.t = 11
        assert fired.wait(5)


def test_idle_exit_called_exactly_once(data):
    clk, calls = Clock(), []
    url, d = data
    app = den_app.create_app(url, d, run_factory=Run(), idle_exit=10, idle_check=0.01,
                             clock=clk, on_idle=lambda: calls.append(1))
    with TestClient(app):
        clk.t = 11
        assert _poll(lambda: calls)
        time.sleep(0.15)
    assert calls == [1]


def test_no_watcher_without_on_idle(data):
    clk = Clock()
    with _client(data, idle_exit=10, idle_check=0.01, clock=clk) as c:
        clk.t = 100
        time.sleep(0.05)
        assert c.get("/health", headers=_auth(data[1])).status_code == 200


def test_request_resets_idle(data):
    clk, fired = Clock(), threading.Event()
    with _idle_client(data, clk=clk, fired=fired) as c:
        clk.t = 9
        assert c.get("/health", headers=_auth(data[1])).status_code == 200
        clk.t = 18
        time.sleep(0.15)
        assert not fired.is_set()
        clk.t = 19.5
        assert fired.wait(5)


def test_rejected_request_does_not_reset_idle(data):
    clk, fired = Clock(), threading.Event()
    with _idle_client(data, clk=clk, fired=fired) as c:
        clk.t = 9
        assert c.get("/health").status_code == 401
        clk.t = 11
        assert fired.wait(5)


def test_idle_exit_waits_for_pending_jobs(data):
    clk, fired, run = Clock(), threading.Event(), Run(released=False)
    with _idle_client(data, run, clk, fired) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "running")
        clk.t = 11
        time.sleep(0.15)
        assert not fired.is_set()
        run.release.set()
        _wait_state(c, h, jid, "done")
        clk.t = 25
        assert fired.wait(5)


def test_idle_exit_waits_for_open_stream(data):
    clk, fired, run = Clock(), threading.Event(), Run(released=False)
    with _idle_client(data, run, clk, fired) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "running")
        c.post(f"/jobs/{jid}/cancel", headers=h)
        _wait_state(c, h, jid, "cancelled")   # 沒有 pending job 了
        # 開一條不會收尾的串流:手動把計數撐著(cancelled 是終態,真串流會立刻收尾)
        c.app.state.streams += 1
        clk.t = 11
        time.sleep(0.15)
        assert not fired.is_set()
        c.app.state.streams -= 1
        clk.t = 25
        assert fired.wait(5)


def test_stream_count_tracks_open_streams(data):
    run = Run(released=False)
    with _client(data, run) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, jid, "running")
        got = []
        t = threading.Thread(target=lambda: got.extend(_read_sse(c, h, jid)), daemon=True)
        t.start()
        assert _poll(lambda: c.app.state.streams == 1)
        run.release.set()
        t.join(10)
        assert _poll(lambda: c.app.state.streams == 0)


def test_idle_watcher_survives_check_error(data, monkeypatch, caplog):
    real, n = den_app.repo.has_pending_jobs, []

    def flaky(conn):
        n.append(1)
        if len(n) == 1:
            raise RuntimeError("database is locked")
        return real(conn)
    monkeypatch.setattr(den_app.repo, "has_pending_jobs", flaky)
    clk, fired = Clock(), threading.Event()
    with caplog.at_level(logging.INFO, logger="hyenovel"), _idle_client(data, clk=clk, fired=fired):
        clk.t = 11
        assert fired.wait(5)
    assert len(n) >= 2
    assert "event=idle-check-failed" in caplog.text


# ── 8b:列出 job ──

def test_list_jobs_newest_first_with_slug_title(data):
    with _client(data) as c:
        h = _auth(data[1])
        c.post("/stories", json={"text": "他走進門。", "title": "門"}, headers=h)
        a = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, a, "done")
        b = c.post("/jobs", json={"kind": "critique", "slug": "d01"}, headers=h).json()["job_id"]
        _wait_state(c, h, b, "paused")     # 假分析的引文對不上 d01 原文 → 閘門耗盡
        r = c.get("/jobs", headers=h)
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert [j["id"] for j in jobs] == [b, a]
        assert jobs[0] == {"id": b, "slug": "d01", "title": "門", "state": "paused",
                           "step": "analyst", "error_class": "gate",
                           "updated_at": jobs[0]["updated_at"], "is_latest_version": True}
        assert (jobs[1]["slug"], jobs[1]["state"]) == ("mini", "done")
        assert [j["id"] for j in c.get("/jobs?limit=1", headers=h).json()["jobs"]] == [b]


def test_list_jobs_empty_and_requires_token(data):
    with _client(data) as c:
        assert c.get("/jobs").status_code == 401
        assert c.get("/jobs", headers=_auth(data[1])).json() == {"jobs": []}


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_list_jobs_limit_out_of_range_422(data, caplog, limit):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        assert c.get(f"/jobs?limit={limit}", headers=_auth(data[1])).status_code == 422
    assert "event=reject where=list-jobs" in caplog.text


def test_list_jobs_limit_bounds_ok(data):
    with _client(data) as c:
        for limit in (1, 100):
            assert c.get(f"/jobs?limit={limit}", headers=_auth(data[1])).status_code == 200


# ── 8c:同版自動續跑、續跑防重 ──

def test_post_job_auto_resumes_cancelled_same_version(data):
    with _client(data, Run(released=False)) as c:
        h = _auth(data[1])
        first = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()
        assert first["resumed"] is False
        _wait_state(c, h, first["job_id"], "running")
        c.post(f"/jobs/{first['job_id']}/cancel", headers=h)
        _wait_state(c, h, first["job_id"], "cancelled")
        again = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h)
        assert again.status_code == 202
        body = again.json()
        assert (body["job_id"], body["existing"], body["resumed"]) == (first["job_id"], True, True)
        assert body["previous_error_class"] is None
        assert len(c.get("/jobs", headers=h).json()["jobs"]) == 1


def test_resume_409_when_other_active_job(data, caplog):
    with _client(data, Run(released=False)) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        old = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        _wait_state(c, h, old, "running")
        c.post(f"/jobs/{old}/cancel", headers=h)
        _wait_state(c, h, old, "cancelled")
        conn = c.app.state.mgr.conn
        live = []

        async def make():
            with conn:
                job = repo.get_job(conn, old)
                live.append(repo.create_job(conn, "critique", job["story_id"],
                                            job["source_version_id"], {}, time.time()))
        c.portal.call(make)
        assert c.post(f"/jobs/{old}/resume", headers=h).status_code == 409
    assert f"event=resume-rejected job={old} reason=active-job other={live[0]}" in caplog.text
    assert "event=reject where=resume" in caplog.text


def test_resume_409_on_stale_version_and_list_flags_it(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        c.post("/stories", json={"text": "第一版。"}, headers=h)
        old = c.post("/jobs", json={"kind": "critique", "slug": "d01"}, headers=h).json()["job_id"]
        _wait_state(c, h, old, "paused")                    # 閘門耗盡
        assert c.post("/stories", json={"text": "改過的第二版。", "slug": "d01"},
                      headers=h).json()["version"] == 2
        assert c.post(f"/jobs/{old}/resume", headers=h).status_code == 409
        row = next(j for j in c.get("/jobs", headers=h).json()["jobs"] if j["id"] == old)
        assert row["is_latest_version"] is False
    assert f"event=resume-rejected job={old} reason=stale-version" in caplog.text


# ── 讀取端點 + 上傳 ──

_READ_ROUTES = ["/stories", "/stories/mini/viz", "/stories/mini/source",
                "/stories/mini/conclusions", "/stories/mini/transcript"]


def test_stories_list(data):
    with _client(data) as c:
        r = c.get("/stories", headers=_auth(data[1]))
    assert r.status_code == 200 and "mini" in [s["slug"] for s in r.json()["stories"]]


def test_viz_200(data):
    with _client(data) as c:
        r = c.get("/stories/mini/viz", headers=_auth(data[1]))
    assert r.status_code == 200 and r.json()["slug"] == "mini"


NOTES = {"slug": "mini", "read": "一個人回到空屋。", "one_line": "燈等的是誰。", "points": [
    {"kind": "confused", "title": "燈為誰亮", "quotes": ["像在等誰"], "refs": ["k1"],
     "body": "以為有人要回來。", "question": "燈在等的是誰?"}]}


def _add_notes(url, version_offset=0):
    c = db.connect(url)
    try:
        with c:
            st = repo.story_by_slug(c, "mini")
            sv = repo.current_artifact(c, st["id"], "analysis")["source_version_id"]
            if version_offset:
                sv, _ = repo.add_source_version(c, st["id"], "別版。", 0.5)
            nid, _ = repo.add_artifact(c, st["id"], sv, "notes", 1, NOTES, {}, 9.0)
            repo.set_current(c, st["id"], "notes", nid)
    finally:
        c.close()


def test_viz_uses_notes_shape(data):
    _add_notes(data[0])
    with _client(data) as c:
        fb = c.get("/stories/mini/viz", headers=_auth(data[1])).json()["feedback"]
    assert fb["read"] == "一個人回到空屋。" and [p["title"] for p in fb["key_points"]] == ["燈為誰亮"]
    assert fb["key_points"][0]["quotes"][0]["quote"] == "像在等誰"


def test_viz_drops_judgment_of_other_version(data):
    _add_notes(data[0], version_offset=1)
    with _client(data) as c:
        assert c.get("/stories/mini/viz", headers=_auth(data[1])).json()["feedback"] is None


def test_viz_404_when_not_analyzed(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        c.post("/stories", json={"text": "未分析。"}, headers=h)
        r = c.get("/stories/d01/viz", headers=h)
    assert r.status_code == 404
    assert "event=reject where=viz reason=not-analyzed" in caplog.text


def test_source_is_verbatim_text(data):
    text = '甲</script>"\'乙\n'
    with _client(data) as c:
        h = _auth(data[1])
        c.post("/stories", json={"text": text}, headers=h)
        r = c.get("/stories/d01/source", headers=h)   # 未分析 → 最新版
    assert r.text == text and r.headers["content-type"].startswith("text/plain")


def test_source_follows_analysis_version(data):
    url, d = data
    conn = db.connect(url)
    st = repo.story_by_slug(conn, "mini")
    cur = repo.current_artifact(conn, st["id"], "analysis")
    old = repo.source_version(conn, cur["source_version_id"])["text"]
    repo.add_source_version(conn, st["id"], old + "新增的一段。", 9.0)
    conn.commit()
    conn.close()
    with _client(data) as c:
        r = c.get("/stories/mini/source", headers=_auth(d))
    assert r.text == old


def test_conclusions_200(data):
    with _client(data) as c:
        r = c.get("/stories/mini/conclusions", headers=_auth(data[1]))
    assert r.status_code == 200 and isinstance(r.json()["conclusions"], list)


def test_transcript_200(data):
    with _client(data) as c:
        r = c.get("/stories/mini/transcript", headers=_auth(data[1]))
    assert r.status_code == 200 and isinstance(r.json()["turns"], list)


@pytest.mark.parametrize("route", [r for r in _READ_ROUTES if r != "/stories"])
def test_slug_routes_bad_and_unknown(data, caplog, route):
    tail = route.rsplit("/", 1)[1]
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        h = _auth(data[1])
        assert c.get(f"/stories/-x/{tail}", headers=h).status_code == 400
        assert c.get(f"/stories/nope/{tail}", headers=h).status_code == 404
    assert f"event=reject where={tail} reason=bad-slug" in caplog.text
    assert f"event=reject where={tail} reason=unknown-slug" in caplog.text


@pytest.mark.parametrize("route", _READ_ROUTES)
def test_read_routes_require_token(data, route):
    with _client(data) as c:
        assert c.get(route).status_code == 401


def test_extract_ok(data):
    with _client(data) as c:
        r = c.post("/extract", files={"file": ("a.txt", "你好".encode())}, headers=_auth(data[1]))
    assert r.status_code == 200 and r.json() == {"filename": "a.txt", "text": "你好\n", "chars": 3}


def test_extract_413_logs_reject(data, caplog):
    big = b"a" * (den_config.MAX_SOURCE_BYTES + 1)
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        r = c.post("/extract", files={"file": ("a.txt", big)}, headers=_auth(data[1]))
    assert r.status_code == 413
    assert f"event=reject where=upload bytes={den_config.MAX_SOURCE_BYTES + 1}" in caplog.text


def test_extract_bad_pdf_400(data):
    with _client(data) as c:
        r = c.post("/extract", files={"file": ("a.pdf", b"%PDF-garbage")}, headers=_auth(data[1]))
    assert r.status_code == 400


def test_extract_requires_token(data):
    with _client(data) as c:
        assert c.post("/extract", files={"file": ("a.txt", b"x")}).status_code == 401


def test_get_works_query_and_limit(data):
    with _client(data) as c:
        h = _auth(data[1])
        c.post("/stories", json={"text": "海很冷。", "title": "海", "slug": None}, headers=h)
        all_ = c.get("/works", headers=h).json()["works"]
        hit = c.get("/works", params={"q": "海"}, headers=h).json()["works"]
        assert len(all_) == 2 and [w["title"] for w in hit] == ["海"]
        assert c.get("/works", params={"limit": 0}, headers=h).status_code == 422
        assert c.get("/works", params={"limit": 51}, headers=h).status_code == 422


def test_get_work_part_status_codes(data):
    with _client(data) as c:
        h = _auth(data[1])
        r = c.get("/works/mini/source", headers=h)
        assert r.status_code == 200 and "原文" in r.json()["text"]
        assert c.get("/works/mini/analysis", headers=h).status_code == 200
        r = c.get("/works/mini/feedback", headers=h)
        assert r.status_code == 409 and r.json()["detail"] == "no-feedback"
        assert c.get("/works/nope/source", headers=h).status_code == 404
        r = c.get("/works/mini/notes", headers=h)
        assert r.status_code == 409 and r.json()["detail"] == "no-notes"
        assert c.get("/works/mini/bogus", headers=h).status_code == 422


def test_post_jobs_resume_only_409_reason(data):
    with _client(data) as c:
        h = _auth(data[1])
        r = c.post("/jobs", json={"kind": "critique", "slug": "mini", "resume_only": True}, headers=h)
        assert r.status_code == 409 and r.json()["detail"] == "done"
        assert c.get("/jobs", headers=h).json()["jobs"] == []


def test_cancel_work_cancels_active_jobs(data):
    with _client(data, run=Run(released=False)) as c:
        h = _auth(data[1])
        jid = c.post("/jobs", json={"kind": "critique", "slug": "mini"}, headers=h).json()["job_id"]
        r = c.post("/works/mini/cancel", headers=h)
        assert r.status_code == 200 and r.json()["cancelled"] == [jid]
        _wait_state(c, h, jid, "cancelled")


def test_cancel_work_nothing_running_409(data):
    with _client(data) as c:
        h = _auth(data[1])
        r = c.post("/works/mini/cancel", headers=h)
        assert r.status_code == 409 and r.json()["detail"] == "nothing-running"
        assert c.post("/works/nope/cancel", headers=h).status_code == 404


def test_discussion_endpoint_gone(data):
    with _client(data) as c:
        assert c.get("/stories/mini/discussion", headers=_auth(data[1])).status_code == 404
