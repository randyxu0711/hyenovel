"""den 的政策常數。值沿用 server/config.py,§3.7 刻意不開放設定。

不 import server.config:它 import 時有副作用,且 server/ 在切片 5 退役。
"""
import re

_SLUG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}")


def valid_slug(slug: str) -> bool:
    """slug 是否安全(可拼路徑、可當 argv 位置參數)。"""
    return bool(slug) and _SLUG_RE.fullmatch(slug) is not None


MAX_GATE_RETRIES = 2
TRANSIENT_MAX_RETRIES = 2
BACKOFF_BASE = 2.0
PHASE_TIMEOUT = 600
# 工人異常門檻(只記 WARNING、不設輸出上限):現行配方每次呼叫正常 1 輪、約 2–8k output tokens,
# 多一輪就是無法解釋的
ANOMALY_TURNS = 1
ANOMALY_OUTPUT_TOKENS = 20000

HOST = "127.0.0.1"
PORT = 8788  # 舊 server 佔 8787,過渡期並存;被佔就自動選(den.json 記實際值)
IDLE_EXIT = 3 * 3600  # 沒人理 den 超過這麼久(且沒 job、沒串流)就自己結束
IDLE_CHECK = 60
SPAWN_WAIT = 15  # 秒:shim 拉起 den 後最多等這麼久(也是等舊 den 放鎖的上限)

# 工人環境白名單:不含任何 CLAUDE*、不含 ANTHROPIC_API_KEY(吃訂閱的既有政策)。
ENV_WHITELIST = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
                 "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")

MAX_SOURCE_BYTES = 5 * 1024 * 1024   # 沿用 server/config.MAX_UPLOAD_BYTES 的值,不 import 它

# clientInfo.name 是提示不是授權(R14):只拿來挑預設 runner。對照表是資料,新增一家只改這裡。
CLIENT_RUNNERS: dict[str, str] = {"claude-code": "claude"}
RUNNER_ORDER = ("claude",)
