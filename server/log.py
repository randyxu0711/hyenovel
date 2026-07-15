"""本 system 的 logger:結構化事件落地(critique 進度 / 容量失敗 / 意外)。

格式約定:訊息一律 `event=<短動詞> key=value …`,第一個 key 固定 event。
只記 safe-to-log 欄位(event/phase/status/slug/attempt/reason…),不記 prompt/回應/故事內容/逐字引用。
層級三級:INFO=進度里程碑、WARNING=降級但自救/吞掉、ERROR=這次跑掛了(意外用 log.exception 帶 traceback)。
單一正本:logs/app.log(輪替,1MB×3)。dev.sh 另把 uvicorn→logs/server.log、vite→logs/web.log,各一關注點。
"""
import logging
import logging.handlers

from . import config

log = logging.getLogger("hyenovel")


def setup() -> None:
    """裝 handler。冪等:重複呼叫不重複加。app 啟動 + orchestrator 進入時各呼一次。"""
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    logdir = config.ROOT / "logs"
    logdir.mkdir(exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        logdir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
