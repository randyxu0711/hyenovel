# hyenovel web (L4 前端)

Vite + React + TS。**只讀 den 的 DB**(切片 4a):`/api` 由 vite 代理到 den 並帶 token。

## 開發

1. 起 den:`python -m den`(或用任何 MCP tool,shim 會自動拉起)。
2. `cd web && npm install && npm run dev` → 開 localhost:5173。
3. 測試 `npm test`、型別 `npm run typecheck`。

網頁討論 4a 期間關閉(輸入框提示改用 MCP 的 `open_discussion`),用量面板隱藏;4b 恢復。
den 沒開時 web 顯示 503 提示。

## 邊界

- `src/data/client.ts` 是唯一 IO。
- 不重算座標/診斷(由 den 端產出)。
- 分享檔:`python -m export <slug> [--out DIR]` 產 `<slug>.md` + `<slug>.html`。

## 切換步驟(舊 server → den;手動做一次)

舊 `server/` 已於切片 5 刪除。從舊版升上來的話:

1. 停掉舊 server(及舊 web dev server)與正在跑的 den(它可能還在用 `server/.venv` 的 python)。
2. 建根目錄 venv(`uv venv && uv pip install -r pyproject.toml`),MCP 改註冊
   `.venv/bin/python -m den.mcp`;確認沒問題後再刪 `server/.venv`。
3. repo 根 `python -m marrow.importer`,確認輸出的 skipped 為空。
4. `python -m den`。
5. `cd web && npm run dev`。
6. 驗收:列表張數 = DB 故事數(扣隱形);開 s08 見骨架圖、原文、結論、逐字;新上傳一篇走完誕生動畫;
   討論輸入回搬家訊息;關掉 den 後 web 顯示 503 提示。
