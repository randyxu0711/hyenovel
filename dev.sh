#!/usr/bin/env bash
# 一鍵起 hyenovel 前後端(WSL/本機)。Ctrl+C 一起收。
# 後端:uvicorn 127.0.0.1:8787(吃訂閱,config.py 會自動拔 ANTHROPIC_API_KEY)
# 前端:vite 5173(已 proxy /api → 8787)
set -euo pipefail
cd "$(dirname "$0")"

LOGS=server/logs          # 所有 log 收攏一窩:server.log / web.log 與 logger 的 critique.log 同處
mkdir -p "$LOGS"

if [ ! -x server/.venv/bin/uvicorn ]; then
  echo "✗ 找不到 server/.venv — 先建 venv 並 pip install -r server/requirements.txt" >&2
  exit 1
fi
if [ ! -d web/node_modules ]; then
  echo "· web/node_modules 不存在,先跑 npm install…"
  (cd web && npm install)
fi

pids=()
cleanup() { echo; echo "收工,關閉前後端…"; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

echo "▶ 後端 uvicorn → http://127.0.0.1:8787  (log: $LOGS/server.log)"
server/.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8787 >"$LOGS/server.log" 2>&1 &
pids+=($!)

echo "▶ 前端 vite   → http://localhost:5173   (log: $LOGS/web.log)"
(cd web && npm run dev) >"$LOGS/web.log" 2>&1 &
pids+=($!)

# 等後端起來
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8787/api/health >/dev/null 2>&1 || curl -sf http://127.0.0.1:8787/ >/dev/null 2>&1; then
    echo "✓ 後端就緒"
    break
  fi
  sleep 0.5
done

echo
echo "都起來了。開 http://localhost:5173  · Ctrl+C 收工。"
echo "(即時 log:tail -f $LOGS/server.log  或  $LOGS/web.log)"
wait
