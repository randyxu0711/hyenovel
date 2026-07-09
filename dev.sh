#!/usr/bin/env bash
# 一鍵起 hyenovel 開發環境(WSL/本機)。Ctrl+C 前後端一起收。
#   後端 uvicorn 127.0.0.1:8787(吃訂閱,config.py 會自動拔 ANTHROPIC_API_KEY)
#   前端 vite   localhost:5173(已 proxy /api → 後端)
set -euo pipefail
cd "$(dirname "$0")"

readonly BACKEND_HOST=127.0.0.1
readonly BACKEND_PORT=8787       # 與 server/config.py 和 web/vite.config.ts 綁定;改這裡要同步那兩處
readonly FRONTEND_PORT=5173
readonly LOG_DIR=server/logs     # server.log / web.log 與 logger 的 critique.log 同窩

start_backend=true
start_frontend=true

usage() {
  cat <<EOF
用法: ${0##*/} [選項]

  無選項 = 前後端一起起(預設)。

  -b, --backend-only    只起後端 uvicorn(${BACKEND_HOST}:${BACKEND_PORT})
  -f, --frontend-only   只起前端 vite(localhost:${FRONTEND_PORT})
  -h, --help            顯示此說明

  Ctrl+C 收工,前後端一起關。
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
if $start_backend && [[ ! -x server/.venv/bin/uvicorn ]]; then
  die "找不到 server/.venv/bin/uvicorn — 先建 venv:python -m venv server/.venv && server/.venv/bin/pip install -r server/requirements.txt"
fi
if $start_frontend && [[ ! -d web/node_modules ]]; then
  echo "· web/node_modules 不存在,先跑 npm install…"
  (cd web && npm install) || die "npm install 失敗"
fi
mkdir -p "$LOG_DIR"

# ── 起服務 + 一起收 ───────────────────────────────────────
pids=()
cleanup() {
  echo
  echo "收工,關閉前後端…"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

backend_pid=
if $start_backend; then
  printf '▶ 後端  %-8s →  http://%s:%s\n' uvicorn "$BACKEND_HOST" "$BACKEND_PORT"
  server/.venv/bin/uvicorn server.app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    >"${LOG_DIR}/server.log" 2>&1 &
  backend_pid=$!
  pids+=("$backend_pid")
fi
if $start_frontend; then
  printf '▶ 前端  %-8s →  http://localhost:%s\n' vite "$FRONTEND_PORT"
  (cd web && npm run dev) >"${LOG_DIR}/web.log" 2>&1 &
  pids+=($!)
fi

# ── 等後端就緒(前端交給 vite 自己報)───────────────────────
if $start_backend; then
  ready=false
  for _ in $(seq 1 30); do
    if curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
      ready=true
      break
    fi
    kill -0 "$backend_pid" 2>/dev/null \
      || die "後端啟動即退出 — 看 ${LOG_DIR}/server.log:"$'\n'"$(tail -n 5 "${LOG_DIR}/server.log" 2>/dev/null)"
    sleep 0.5
  done
  $ready \
    && echo "✓ 後端就緒" \
    || echo "⚠ 後端 15s 內未回應 /api/health(可能還在起或卡住)— 看 ${LOG_DIR}/server.log" >&2
fi

# ── 摘要 ──────────────────────────────────────────────────
if $start_frontend; then
  open_url="http://localhost:${FRONTEND_PORT}"
else
  open_url="http://${BACKEND_HOST}:${BACKEND_PORT}"
fi
if $start_backend && $start_frontend; then
  tail_target="${LOG_DIR}/{server,web}.log"
elif $start_backend; then
  tail_target="${LOG_DIR}/server.log"
else
  tail_target="${LOG_DIR}/web.log"
fi

echo
printf '  開啟   %s\n' "$open_url"
printf '  日誌   tail -f %s\n' "$tail_target"
printf '  收工   Ctrl+C\n'
wait
