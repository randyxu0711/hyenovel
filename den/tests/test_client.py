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
        self.paths: list[tuple[str, str]] = []   # 真的送到假 den 的 (method, path)
        self.fake_401 = 0          # 非 /health 請求:接下來幾次直接回 401(不送進 den)
        self.raise_after = None    # 非 /health 請求:den 處理完後丟這個例外(回應在路上丟了)

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
                api = request.url.path != "/health"
                if api and fake.fake_401:
                    fake.fake_401 -= 1
                    fake.statuses.append(401)
                    return httpx.Response(401, json={"detail": "bad token"})
                fake.paths.append((request.method, request.url.path))
                r = fake.tc._transport.handle_request(request)
                if api and fake.raise_after is not None:
                    raise fake.raise_after("lost", request=request)
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


def test_spawned_den_exits_fails_fast(den):
    """den 一起來就死(例:沒有 claude CLI)→ 立刻回報 log 尾巴,不等滿 spawn_wait。"""
    class Dead:
        def poll(self):
            return 1

    def spawn():
        with open(den.dir / "den.log", "a", encoding="utf-8") as f:
            f.write("RuntimeError: 找不到 claude CLI\n")
        return Dead()
    c = den.client(spawn=spawn, spawn_wait=10.0)
    t0 = time.monotonic()
    with pytest.raises(DenUnavailable) as ei:
        c.ensure()
    assert time.monotonic() - t0 < 1.0
    assert "結束" in str(ei.value) and "1" in str(ei.value)
    assert "RuntimeError: 找不到 claude CLI" in str(ei.value)


def test_spawned_den_still_running_keeps_waiting(den):
    """poll() 回 None = 還活著:照常等它起來。"""
    class Alive:
        def poll(self):
            return None

    def spawn():
        den.spawn()
        return Alive()
    den.client(spawn=spawn).ensure()
    assert den.spawns == 1


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
    lock = threading.Lock()

    def spawn():
        with lock:
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
    den.auth.clear()
    assert c.request("GET", "/jobs/999").status_code == 404
    assert set(den.auth) == {f"Bearer {new}"}   # 每次 request 前的 ensure 重讀了 token
    assert den.spawns == 0 and den.kills == []


def test_request_retries_once_on_401(den):
    den.start()
    c = den.client()
    den.fake_401 = 1
    den.statuses.clear()
    assert c.request("GET", "/jobs/999").status_code == 404
    assert 401 in den.statuses and den.spawns == 0


def test_request_401_twice_returned_as_is(den):
    den.start()
    c = den.client()
    den.fake_401 = 5
    assert c.request("GET", "/jobs/999").status_code == 401
    assert den.fake_401 == 3   # 原送一次 + 重試一次,不多


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
    assert isinstance(den_client.default_spawn(tmp_path)(), P)   # 留著 handle,死了才知道
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


def test_read_timeout_after_den_handled_is_not_retried(den):
    """回應在路上丟了(den 已 commit job):不可重送,否則第二個 job、第二份花費。"""
    den.start()
    c = den.client()
    den.raise_after = httpx.ReadTimeout
    with pytest.raises(DenUnavailable):
        c.request("POST", "/jobs", json={"kind": "critique", "slug": "mini"})
    assert den.paths.count(("POST", "/jobs")) == 1
    assert den.spawns == 0


def test_connect_timeout_is_retried(den):
    den.start()
    real = den.http
    n = []

    def http(base_url):
        cl = real(base_url)
        orig = cl.request

        def request(method, path, **kw):
            if path != "/health" and not n:
                n.append(1)
                raise httpx.ConnectTimeout("slow connect")
            return orig(method, path, **kw)
        cl.request = request
        return cl
    c = den.client(http=http)
    assert c.request("GET", "/jobs/999").status_code == 404
    assert n == [1] and den.spawns == 0


def test_request_restarts_when_disk_version_changes(den):
    den.start()
    ver = {"v": den.tc.app.state.version}
    c = den.client(disk_version=lambda: ver["v"])
    c.loaded_version = ver["v"]
    assert c.request("GET", "/health").status_code == 200
    ver["v"] = "new"   # git pull 了
    assert c.request("GET", "/health").status_code == 200
    assert den.kills == [os.getpid()] and den.spawns == 1


def test_request_busy_den_kept_on_disk_change(data):
    den = FakeDen(data, run=Run(released=False))
    try:
        den.start()
        ver = {"v": den.tc.app.state.version}
        c = den.client(disk_version=lambda: ver["v"])
        c.loaded_version = ver["v"]
        assert c.request("POST", "/jobs", json={"kind": "critique", "slug": "mini"}).status_code == 202
        ver["v"] = "new"
        assert c.request("GET", "/health").status_code == 200
        assert den.kills == [] and den.spawns == 0
        assert den_client.NOTICE_BUSY in c.take_notices()
    finally:
        den.run.release.set()
        den.stop()


def test_request_stale_shim_no_restart(den):
    den.start()
    c = den.client()
    c.loaded_version = "old-shim"
    for _ in range(3):
        assert c.request("GET", "/health").status_code == 200
    assert den.kills == [] and den.spawns == 0
    assert c.take_notices() == [den_client.NOTICE_STALE]


def test_take_notices_clears(den):
    den.start()
    c = den.client()
    c.loaded_version = "old-shim"
    c.ensure()
    assert c.take_notices() == [den_client.NOTICE_STALE]
    assert c.take_notices() == [] and c.notices == []


def test_kill_process_gone_still_starts(den):
    den.start()

    def kill(pid):
        den.kills.append(pid)
        den.stop()   # 在 /health 與 SIGTERM 之間自己退場了
        raise ProcessLookupError(pid)
    den.client(disk_version=lambda: "other", kill=kill).ensure()
    assert den.kills == [os.getpid()] and den.spawns == 1


def test_kill_permission_denied_is_den_unavailable(den):
    den.start()

    def kill(pid):
        raise PermissionError(pid)
    with pytest.raises(DenUnavailable, match="無權"):
        den.client(disk_version=lambda: "other", kill=kill).ensure()
    assert den.spawns == 0


def test_probe_uses_short_timeout(den, monkeypatch):
    den.start()
    seen = []
    orig = httpx.Client.get

    def get(self, url, **kw):
        seen.append(kw.get("timeout"))
        return orig(self, url, **kw)
    monkeypatch.setattr(httpx.Client, "get", get)
    den.client().ensure()
    assert seen == [den_client._PROBE_TIMEOUT]
