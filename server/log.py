"""本 system 的 logger:結構化 critique 進度 / 容量失敗訊號落地。
只記 safe-to-log 欄位(phase 名、status code、rate-limit 欄位),不記 prompt/回應文本。
輸出雙軌:stderr(dev.sh 即時看)+ 輪替檔(活過 Run 的 10 分鐘 TTL,事後查得到)。
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
    logdir = config.ROOT / "server" / "logs"
    logdir.mkdir(exist_ok=True)
    sh = logging.StreamHandler()
    fh = logging.handlers.RotatingFileHandler(
        logdir / "critique.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    for h in (sh, fh):
        h.setFormatter(fmt)
        log.addHandler(h)
