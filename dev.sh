#!/usr/bin/env bash
# 一鍵起 hyenovel 開發環境(WSL/本機)。Ctrl+C 收前端。
#   後端 den    127.0.0.1(吃訂閱;port/token 記在 den.json/den.token,vite 自己讀)
#   前端 vite   localhost:5173(已 proxy /api → den)
#
# den 是單例(檔案鎖),MCP shim 也可能已經把它拉起來。這裡走跟 MCP shim 同一條
# DenClient.ensure():已有健康的 den 就沿用,沒有才脫離拉起(閒置 3 小時自己結束)。
# 因為 den 是脫離的、可能被多方共用,所以 Ctrl+C 只收前端,不去殺 den。
set -euo pipefail
cd "$(dirname "$0")"

readonly FRONTEND_PORT=5173
readonly LOG_DIR=logs            # web.log(vite)

start_backend=true
start_frontend=true

usage() {
  cat <<EOF
用法: ${0##*/} [選項]

  無選項 = 確保 den 在跑,並起前端(預設)。

  -b, --backend-only    只確保 den 在跑(不起前端)
  -f, --frontend-only   只起前端 vite(localhost:${FRONTEND_PORT}),不管 den
  -h, --help            顯示此說明

  Ctrl+C 收前端;den 脫離運行,閒置 3 小時自己結束。
EOF
}

die() { echo "✗ $*" >&2; exit 1; }

# ── 解析參數 ──────────────────────────────────────────────
while (($#)); do
  case $1 in
    -b|--backend-only)  start_frontend=false ;;
    -f|--frontend-only) start_backend=false ;;
    -h|--help)          usage; exit 0 ;;
    *) usage >&2; die "未知參數:$1" ;;
  esac
  shift
done
$start_backend || $start_frontend \
  || die "--backend-only 與 --frontend-only 不能同時給(那樣什麼都不會起)"

# ── 前置檢查(只查要起的那邊)─────────────────────────────
if $start_backend && [[ ! -x .venv/bin/python ]]; then
  die "找不到 .venv/bin/python — 先建 venv:uv venv && uv pip install -r pyproject.toml -r requirements-dev.txt"
fi
if $start_frontend && [[ ! -d web/node_modules ]]; then
  echo "· web/node_modules 不存在,先跑 npm install…"
  (cd web && npm install) || die "npm install 失敗"
fi
mkdir -p "$LOG_DIR"

# ── 確保 den + 起前端 ─────────────────────────────────────
pids=()
cleanup() {
  echo
  echo "收工,關閉前端…"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

if $start_backend; then
  echo "▶ 後端  den(沿用已在跑的,否則脫離拉起)"
  .venv/bin/python -c "
from den.client import DenClient
from marrow import db
DenClient(db.data_dir()).ensure()
" || die "den 起不來 — 手動跑 .venv/bin/python -m den 看錯誤"
  echo "✓ den 就緒"
fi
if $start_frontend; then
  printf '▶ 前端  %-8s →  http://localhost:%s\n' vite "$FRONTEND_PORT"
  (cd web && npm run dev) >"${LOG_DIR}/web.log" 2>&1 &
  pids+=($!)
fi

if $start_frontend; then
  echo
  printf '  開啟   http://localhost:%s\n' "$FRONTEND_PORT"
  printf '  日誌   tail -f %s/web.log\n' "$LOG_DIR"
  printf '  收工   Ctrl+C\n'
  printf '  (不開發只要用:cd web && npm run build,再 .venv/bin/python -m den.open)\n'
  wait
fi
