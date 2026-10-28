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
from den.tests.conftest import FIXTURES
from den.tests.test_pipeline import _analysis, _feedback, ok
from marrow import db, importer
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
            return ok(_analysis() if schema is WORKPACKS["analyst"].schema else _feedback())
        return run


@pytest.fixture
def data(tmp_path):
    """tmp_path 當 data_dir,檔案 DB 預先 migrate + 匯入 mini。"""
    url = f"sqlite:///{tmp_path}/t.db"
    c = db.connect(url)
    db.migrate(c, tmp_path / "t.db")
    importer.import_story(c, FIXTURES / "mini", 1.0)
    c.close()
    return url, tmp_path


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
        assert [a["step"] for a in body["attempts"]] == ["analyst", "criticizer"]
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
        assert evs == [{"event": "state", "data": {"state": "done", "step": "criticizer",
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


def test_discussion_404(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        assert c.get("/stories/nope/discussion", headers=_auth(data[1])).status_code == 404
    assert "event=reject where=discussion reason=unknown-slug" in caplog.text


def test_post_stories_422_unknown_slug(data, caplog):
    with _client(data) as c, caplog.at_level(logging.INFO, logger="hyenovel"):
        r = c.post("/stories", json={"text": "x", "slug": "s07"}, headers=_auth(data[1]))
    assert r.status_code == 422
    assert "event=reject where=stories reason=unknown slug" in caplog.text


def test_discussion_422_bad_slug(data):
    with _client(data) as c:
        assert c.get("/stories/-x/discussion", headers=_auth(data[1])).status_code == 422


def test_discussion_409(data):
    with _client(data) as c:
        h = _auth(data[1])
        c.post("/stories", json={"text": "未分析。"}, headers=h)
        r = c.get("/stories/d01/discussion", headers=h)
    assert r.status_code == 409 and r.json() == {"detail": "這篇還沒分析完成"}


def test_discussion_200(data):
    with _client(data) as c:
        r = c.get("/stories/mini/discussion", headers=_auth(data[1]))
    assert r.status_code == 200 and r.json()["slug"] == "mini"


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
