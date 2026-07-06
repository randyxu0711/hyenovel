"""後端設定常數 + 強制訂閱認證。"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 專案根(viz.py / stories/ 所在)
STORIES = ROOT / "stories"

# slug 來自 HTTP path,會拼進檔案路徑、也會當 argv 餵子行程。嚴格白名單:
# 首字限英數/底線(擋掉開頭 '-' 的 argv flag 注入),其餘允許英數/底線/連字號;
# 字元集不含 '/'、'.' → 連帶擋掉路徑穿越(../、絕對路徑)。
_SLUG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}")


def valid_slug(slug: str) -> bool:
    """slug 是否安全(可拼路徑、可當 argv 位置參數)。"""
    return bool(slug) and _SLUG_RE.fullmatch(slug) is not None

# ── 強制訂閱認證:絕不走 API token 計費 ──────────────────────────────
# 核心前提「吃訂閱、不用 API token」。把 ANTHROPIC_API_KEY 拔掉,SDK 會
# 改讀 ~/.claude/.credentials.json(Claude Code 登入)。匯入本模組即生效。
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── 模型 ────────────────────────────────────────────────────────────
# critique 協調者用 sonnet(子代理 frontmatter 也 pin sonnet);討論用 sonnet
# 較省,改成 "opus" 可換更強的對話品質(成本上升,呼應計費風險)。
CRITIQUE_MODEL = "sonnet"
DISCUSS_MODEL = "sonnet"

# ── 安全閥 ──────────────────────────────────────────────────────────
CRITIQUE_BUDGET_USD = 3.0        # 單次 critique 成本上限(SDK max_budget_usd)
MAX_GATE_RETRIES = 2             # 閘門失敗後最多重派 subagent 幾次
PHASE_TIMEOUT = 600             # 單格(analyst/criticizer)LLM 回合逾時上限(秒)—— 防無界卡住
AGENT_MAX_TURNS = 12            # 單一代理最多回合(讀幾檔 + 寫一次;綁上限防失控)
DISCUSS_IDLE_TIMEOUT = 30 * 60   # 討論 session 閒置幾秒後回收(秒)

# ── 服務 ────────────────────────────────────────────────────────────
# 訂閱認證綁本機 credentials → 只跑 localhost、單人。別丟雲端。
HOST = "127.0.0.1"
PORT = 8787
