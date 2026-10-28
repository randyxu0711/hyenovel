"""stdio shim 找 den 的客戶端:讀 den.json 探索、沒有就 detached 拉起、版本不符重啟、斷線重試一次。

- 絕不對 den.json 裡的 pid 送訊號:den 被 SIGKILL 時檔案會殘留,pid 可能已被別人重用。
  要殺只殺 /health(帶 token 驗過)當下回報的 pid。
- 版本比的是「磁碟上現在的指紋」(每次現算),不是 shim 自己 import 時的值;否則 git pull 後
  舊 shim 會把新 den 判成不符,每次呼叫都重啟。den 忙時不重啟,只留提示。
- 本模組不 print:stdout 屬於 MCP 協定。預設拉起的 den 輸出一律進 `<data_dir>/den.log`。
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import filelock
import httpx

from den.config import SPAWN_WAIT
from den.version import fingerprint

_REPO = Path(__file__).resolve().parent.parent
_LOG_TAIL = 20
NOTICE_BUSY = "hyenovel 已更新,目前的分析跑完後才會換新版。"
NOTICE_STALE = "hyenovel 已更新,請在 Claude Code 執行 `/mcp` 重新連線。"


class DenUnavailable(Exception):
    """den 起不來 / 連不上;訊息給人看(有 den.log 時附尾巴)。"""


def default_spawn(data_dir: Path) -> Callable[[], None]:
    """detached 拉起 `python -m den`:新 session(Claude Code 關掉不會帶走它)、
    stdin 接 /dev/null、stdout/stderr 進 den.log(絕不繼承 shim 的 stdout)、env 去掉 CLAUDE*。"""
    def spawn() -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        with open(data_dir / "den.log", "ab") as log:   # 子行程已 dup 了 fd,父行程關掉無妨
            subprocess.Popen([sys.executable, "-m", "den"], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             cwd=_REPO, env=env)
    return spawn


def _sigterm(pid: int) -> None:
    os.kill(pid, signal.SIGTERM)


def _http(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=httpx.Timeout(60.0, connect=3.0))


class DenClient:
    def __init__(self, data_dir: Path, *, spawn: Callable[[], None] | None = None,
                 kill: Callable[[int], None] = _sigterm,
                 http: Callable[[str], httpx.Client] = _http,
                 disk_version: Callable[[], str] = fingerprint,
                 spawn_wait: float = SPAWN_WAIT, poll: float = 0.1):
        self.data_dir = Path(data_dir)
        self._spawn = spawn or default_spawn(self.data_dir)
        self._kill = kill
        self._http_factory = http
        self.disk_version = disk_version
        self.spawn_wait = spawn_wait
        self.poll = poll
        self.loaded_version = fingerprint()
        self.notices: list[str] = []
        self._lock = threading.Lock()          # 同一個 client 跨 thread 的 ensure 序列化
        self._conn: tuple[httpx.Client, str] | None = None   # (client, token);None = 需要 ensure
        self._clients: dict[str, httpx.Client] = {}

    @property
    def stale_shim(self) -> bool:
        return self.loaded_version != self.disk_version()

    def _notice(self, msg: str) -> None:
        if msg not in self.notices:
            self.notices.append(msg)

    # 探測 ---------------------------------------------------------------
    def _client_for(self, port: int) -> httpx.Client:
        base = f"http://127.0.0.1:{port}"
        if base not in self._clients:
            self._clients[base] = self._http_factory(base)
        return self._clients[base]

    def _probe(self):
        """重讀 den.token 與 den.json 打 /health。成功 → (client, token, health);否則 None。
        den.json 的 pid 在這裡就丟掉,不往外傳。"""
        try:
            token = (self.data_dir / "den.token").read_text(encoding="utf-8").strip()
            port = int(json.loads((self.data_dir / "den.json").read_text(encoding="utf-8"))["port"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        client = self._client_for(port)
        try:
            r = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        except httpx.TransportError:
            return None
        if r.status_code != 200:
            return None   # 401:token 對不上(可能是別的服務佔了 port,或 den 剛重產)
        try:
            h = r.json()
            ok = isinstance(h, dict) and isinstance(h.get("version"), str) \
                and type(h.get("pid")) is int and isinstance(h.get("busy"), bool)
        except ValueError:
            ok = False
        return (client, token, h) if ok else None   # 形狀不對 = 不是 den,更不能拿它的 pid 去殺

    def _accept(self, probe, disk: str) -> bool:
        """版本相符,或不符但忙(留提示)→ 收下這個 den。"""
        client, token, health = probe
        if health["version"] != disk:
            if not health["busy"]:
                return False
            self._notice(NOTICE_BUSY)
        self._conn = (client, token)
        return True

    # ensure -------------------------------------------------------------
    def ensure(self) -> None:
        # 不在開頭清 _conn:別的 thread 的 request 可能正拿著它;失敗才清
        with self._lock:
            try:
                disk = self.disk_version()
                if self.loaded_version != disk:
                    self._notice(NOTICE_STALE)
                p = self._probe()
                if p is not None:
                    if self._accept(p, disk):
                        return
                    self._conn = None
                    self._kill(p[2]["pid"])   # /health 當下回報的 pid,不是 den.json 的
                self._start(disk)
            except BaseException:
                self._conn = None
                raise

    def _start(self, disk: str) -> None:
        spawn_lock = filelock.FileLock(self.data_dir / "den.spawn.lock")
        try:
            spawn_lock.acquire(timeout=2 * self.spawn_wait + 1)
        except filelock.Timeout:
            raise DenUnavailable("另一個 shim 正在拉起 den,等太久;稍後再試。") from None
        try:
            if self._wait_lock_free(disk):
                return
            try:
                self._spawn()
            except OSError as e:
                raise DenUnavailable(f"拉不起 den:{e}") from None
            deadline = time.monotonic() + self.spawn_wait
            while True:
                p = self._probe()
                # 剛拉起的就是磁碟上的新版;舊 den 已放鎖才會走到這裡,不必再挑版本
                if p is not None:
                    self._conn = (p[0], p[1])
                    return
                if time.monotonic() >= deadline:
                    raise DenUnavailable(self._failure_message())
                time.sleep(self.poll)
        finally:
            spawn_lock.release()

    def _wait_lock_free(self, disk: str) -> bool:
        """持 spawn 鎖後:別的 shim 可能剛拉起(→ 收下,回 True);舊 den 可能還在退場
        (→ 等它放 den.lock,回 False 表示該拉起了)。"""
        deadline = time.monotonic() + self.spawn_wait
        while True:
            p = self._probe()
            if p is not None and self._accept(p, disk):
                return True
            den_lock = filelock.FileLock(self.data_dir / "den.lock")
            try:
                den_lock.acquire(timeout=0)
            except filelock.Timeout:
                pass
            else:
                den_lock.release()   # 只是確認舊 den 已放手;馬上還,讓新 den 拿得到
                return False
            if time.monotonic() >= deadline:
                raise DenUnavailable(
                    f"den.lock 被佔超過 {self.spawn_wait:g} 秒,但 den 連不上:"
                    f"檢查是否有卡住的 den 行程({self.data_dir / 'den.lock'})。")
            time.sleep(self.poll)

    def _failure_message(self) -> str:
        msg = f"den 沒在 {self.spawn_wait:g} 秒內起來。"
        try:
            lines = (self.data_dir / "den.log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return msg
        return msg + f"\nden.log 最後 {_LOG_TAIL} 行:\n" + "\n".join(lines[-_LOG_TAIL:])

    # request ------------------------------------------------------------
    def _send(self, method: str, path: str, json: dict | None) -> httpx.Response:
        conn = self._conn   # 取一次快照:別的 thread 可能同時換掉它
        if conn is None:
            self.ensure()
            conn = self._conn
        client, token = conn
        return client.request(method, path, json=json, headers={"Authorization": f"Bearer {token}"})

    def request(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        try:
            r = self._send(method, path, json)
            if r.status_code != 401:
                return r
        except httpx.TransportError:
            pass
        self.ensure()   # 只重試一次
        try:
            return self._send(method, path, json)
        except httpx.TransportError as e:
            raise DenUnavailable(f"den 連線中斷:{e}") from None
