# hyenovel web (L4 前端骨架)

Vite + React + TS。讀既有靜態資料契約(index.json / viz.json / source.md)呈現分析旅程。

## 開發

1. repo 根先 `python index.py`(生 stories/index.json)。
2. `cd web && npm install && npm run dev` → 開 localhost:5173。
   dev server 把 repo `stories/` 唯讀映射到 `/data`(見 vite-plugin-data.ts)。
3. 測試 `npm test`、型別 `npm run typecheck`。

## 邊界

- `src/data/client.ts` 是唯一 IO。之後接後端(＋新增故事 / 即時討論)只改這層。
- 不重算座標/診斷(viz.py 已產於 viz.json)。
