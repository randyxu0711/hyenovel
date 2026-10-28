"""den.client 行為契約:探索、拉起、版本不符重啟、斷線重試一次、絕不對檔案裡的 pid 送訊號。

假 den = TestClient(create_app(...)):「拉起」= 進入 lifespan(寫 den.json、取 den.lock),
「kill」= 離開 lifespan。`http` 注入的 client 走一個開關 transport:den 不在時丟 ConnectError,
跟真的連不上一樣。絕不 spawn 真 den / 真 claude,data dir 一律 tmp_path。
"""
import json
import os
import subprocess
import sys
import threading
import time

import filelock
import httpx
import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den import client as den_client
from den.client import DenClient, DenUnavailable
from den.tests.test_app import Run
from den.version import fingerprint


class FakeDen:
    """可起可停的假 den;transport 記下每個請求的 Authorization 與回應碼。"""

    def __init__(self, data, run=None):
        self.url, self.dir = data
        self.run = run or Run()
        self.tc = None
        self.auth: list[str | None] = []
        self.statuses: list[int] = []
        self.spawns = 0
        self.kills: list[int] = []

    # 注入點 ------------------------------------------------------------
    def start(self):
        self.tc = TestClient(den_app.create_app(self.url, self.dir, run_factory=self.run))
        self.tc.__enter__()

    def stop(self):
        if self.tc is not None:
            self.tc.__exit__(None, None, None)
            self.tc = None

    def spawn(self):
        self.spawns += 1
        self.start()

    def kill(self, pid):
        self.kills.append(pid)
        self.stop()

    def http(self, base_url):
        fake = self

        class Switch(httpx.BaseTransport):
            def handle_request(self, request):
                if fake.tc is None:
                    raise httpx.ConnectError("connection refused", request=request)
                fake.auth.append(request.headers.get("authorization"))
                r = fake.tc._transport.handle_request(request)
                r.read()   # starlette 的回應 stream 不是 httpx.SyncByteStream,轉成一般回應
                fake.statuses.append(r.status_code)
                return httpx.Response(r.status_code, headers=r.headers, content=r.content)

        return httpx.Client(base_url="http://testserver", transport=Switch())

    def client(self, **kw):
        kw.setdefault("spawn", self.spawn)
        kw.setdefault("kill", self.kill)
        kw.setdefault("http", self.http)
        kw.setdefault("spawn_wait", 2.0)
        kw.setdefault("poll", 0.01)
        return DenClient(self.dir, **kw)


@pytest.fixture
def den(data):
    d = FakeDen(data)
    yield d
    d.stop()


def test_ensure_uses_running_den(den):
    den.start()
    den.client().ensure()
    assert den.spawns == 0 and den.kills == []


def test_ensure_spawns_when_absent(den):
    assert not (den.dir / "den.json").exists()
    c = den.client()
    c.ensure()
    assert den.spawns == 1
    assert c.request("GET", "/health").status_code == 200


def test_ensure_restarts_on_version_mismatch(den):
    den.start()
    c = den.client(disk_version=lambda: "other")
    c.ensure()
    assert den.kills == [os.getpid()]   # 假 den 跑在本行程,/health 回報的就是本行程 pid
    assert den.spawns == 1


def test_request_respawns_after_den_exit(den):
    den.start()
    c = den.client()
    assert c.request("GET", "/health").status_code == 200
    den.stop()   # 模擬閒置退場
    assert c.request("GET", "/health").status_code == 200
    assert den.spawns == 1


def test_request_retries_only_once(den):
    den.start()
    calls = []
    c = den.client(spawn=lambda: calls.append(1), spawn_wait=0.2)
    c.ensure()
    den.stop()
    with pytest.raises(DenUnavailable):
        c.request("GET", "/health")
    assert len(calls) == 1


def test_spawn_failure_reports_log_tail(den):
    def spawn():
        with open(den.dir / "den.log", "a", encoding="utf-8") as f:
            f.write("starting\nRuntimeError: 找不到 claude CLI\n")
    c = den.client(spawn=spawn, spawn_wait=0.3)
    t0 = time.monotonic()
    with pytest.raises(DenUnavailable) as ei:
        c.ensure()
    assert time.monotonic() - t0 < 1.0
    assert "RuntimeError: 找不到 claude CLI" in str(ei.value)


def test_spawn_failure_without_log(den):
    c = den.client(spawn=lambda: None, spawn_wait=0.1)
    with pytest.raises(DenUnavailable, match="den"):
        c.ensure()


def test_concurrent_ensure_spawns_once(den):
    lock = threading.Lock()

    def spawn():
        with lock:
            den.spawns += 1
        time.sleep(0.1)
        den.start()

    clients = [den.client(spawn=spawn), den.client(spawn=spawn)]
    errs: list = []

    def go(c):
        try:
            c.ensure()
        except Exception as e:   # pragma: no cover - 失敗時才走到
            errs.append(e)

    ts = [threading.Thread(target=go, args=(c,)) for c in clients]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    assert errs == [] and den.spawns == 1


def test_concurrent_ensure_same_client(den):
    def spawn():
        den.spawns += 1
        time.sleep(0.1)
        den.start()
    c = den.client(spawn=spawn)
    ts = [threading.Thread(target=c.ensure) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    assert den.spawns == 1


def test_token_sent(den):
    den.start()
    c = den.client()
    c.request("GET", "/health")
    token = (den.dir / "den.token").read_text().strip()
    assert den.auth and set(den.auth) == {f"Bearer {token}"}


def test_token_reread_after_regen(den):
    den.start()
    c = den.client()
    c.ensure()
    new = "n" * 43
    (den.dir / "den.token").write_text(new + "\n")
    den.tc.app.state.token = new   # 模擬 den 重產 token
    den.statuses.clear()
    assert c.request("GET", "/health").status_code == 200
    assert den.statuses[0] == 401 and den.statuses[-1] == 200
    assert den.spawns == 0 and den.kills == []


def test_no_restart_loop_when_shim_stale(den):
    den.start()
    ver = den.tc.app.state.version
    c = den.client(disk_version=lambda: ver)
    c.loaded_version = "old-shim"
    for _ in range(3):
        c.ensure()
        assert c.request("GET", "/health").status_code == 200
    assert den.kills == [] and den.spawns == 0
    assert c.stale_shim is True
    assert any("/mcp" in n for n in c.notices)
    assert len(c.notices) == 1   # 重複提示不疊


def test_fresh_shim_is_not_stale(den):
    c = den.client()
    assert c.stale_shim is False and c.loaded_version == fingerprint()


def test_mismatch_but_busy_keeps_old_den(data):
    den = FakeDen(data, run=Run(released=False))
    try:
        den.start()
        c = den.client(disk_version=lambda: "new")
        c.loaded_version = "new"
        # 版本不符但沒忙前不能讓它被重啟:先用正確版本的 client 送一個 job 進去
        ok = den.client()
        r = ok.request("POST", "/jobs", json={"kind": "critique", "slug": "mini"})
        assert r.status_code == 202
        c.ensure()
        assert den.kills == [] and den.spawns == 0
        assert any("跑完後才會換新版" in n for n in c.notices)
    finally:
        den.run.release.set()
        den.stop()


def test_kill_uses_health_pid_not_file(den):
    den.start()
    p = den.dir / "den.json"
    info = json.loads(p.read_text())
    info["pid"] = 999999
    p.write_text(json.dumps(info))
    den.client(disk_version=lambda: "other").ensure()
    assert den.kills == [os.getpid()]


def test_stale_den_json_never_signals(den):
    (den.dir / "den.json").write_text(json.dumps({"port": 1, "pid": 4242, "version": "x"}))
    den.client().ensure()
    assert den.kills == [] and den.spawns == 1


def test_bad_den_json_treated_as_absent(den):
    (den.dir / "den.json").write_text("{not json")
    den.client().ensure()
    assert den.spawns == 1


def test_spawn_waits_for_lock_release(den):
    # filelock 預設 thread-local:同一條 thread 取、放
    holding = threading.Event()
    released_at = []

    def release():
        held = filelock.FileLock(den.dir / "den.lock")
        held.acquire()
        holding.set()
        time.sleep(0.2)
        released_at.append(time.monotonic())
        held.release()

    spawned_at = []

    def spawn():
        spawned_at.append(time.monotonic())
        den.start()

    t = threading.Thread(target=release)
    t.start()
    assert holding.wait(5)
    den.client(spawn=spawn).ensure()
    t.join()
    assert spawned_at and released_at and spawned_at[0] >= released_at[0]


def test_lock_never_released_gives_up(den):
    held = filelock.FileLock(den.dir / "den.lock")
    held.acquire()
    try:
        calls = []
        c = den.client(spawn=lambda: calls.append(1), spawn_wait=0.2)
        with pytest.raises(DenUnavailable, match="den.lock"):
            c.ensure()
        assert calls == []
    finally:
        held.release()


def test_spawn_env_strips_claude(tmp_path, monkeypatch):
    seen = {}

    class P:
        def __init__(self, args, **kw):
            seen["args"] = args
            seen["kw"] = kw

    monkeypatch.setattr(subprocess, "Popen", P)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    den_client.default_spawn(tmp_path)()
    kw = seen["kw"]
    assert seen["args"] == [sys.executable, "-m", "den"]
    assert "CLAUDE_CODE_SESSION_ID" not in kw["env"] and "CLAUDECODE" not in kw["env"]
    assert kw["env"]["DATABASE_URL"] == "sqlite:///x.db"
    assert kw["start_new_session"] is True
    assert kw["stdin"] is subprocess.DEVNULL
    assert kw["stdout"] is not None and kw["stdout"] is not sys.stdout
    assert kw["stderr"] is not None and kw["stderr"] is not sys.stdout
    assert (tmp_path / "den.log").exists()


def test_non_den_health_shape_never_signals(den):
    """port 上是別的服務、回了 200 但形狀不對 → 當作 den 不在,不殺任何人。"""
    (den.dir / "den.token").write_text("t" * 43)
    (den.dir / "den.json").write_text(json.dumps({"port": 1, "pid": 4242, "version": "x"}))

    def http(base_url):
        return httpx.Client(base_url="http://x", transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"pid": 1})))
    calls = []
    with pytest.raises(DenUnavailable):
        den.client(http=http, spawn=lambda: calls.append(1), spawn_wait=0.1).ensure()
    assert den.kills == [] and calls == [1]


def test_spawn_oserror_is_den_unavailable(den):
    def spawn():
        raise FileNotFoundError("python 不見了")
    with pytest.raises(DenUnavailable, match="python 不見了"):
        den.client(spawn=spawn).ensure()
