# hyenovel

純文學短篇的**評論 / 思考討論工具**,跑在 Claude Code(吃訂閱,不用 API token)。
不是一次性產報告,而是**會分析、給發展性回饋、能來回討論、把分析視覺化**的個人思考工具。

## 核心原則
**`analysis.json` 是唯一正本**;`viz.py`、`analysis.md`、(可選)Obsidian 都是它的下游消費者。

```
source.md ──analyst──▶ analysis.json(正本)
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
        analysis.md     viz.py→viz.html   開 Obsidian 指向
        feedback.md     ← 可視化           stories/ 即可翻讀
```

## 架構
兩個隔離的 subagent(「觀察」與「判斷」分開 context):
- **analyst** — 整篇讀一次 → 產 `analysis.json`(型別固定、內容自由,每條附逐字原文引用)。
- **criticizer** — 只看 `analysis.json` + 原文 → 產 `feedback.md`(出版編輯人格、發展性、不諂媚)。

## 用法(L1)
1. 把故事放成 `stories/<slug>/source.md`。
2. `/story-critique stories/<slug>/source.md` → 產 `analysis.json` / `analysis.md` / `feedback.md`。
3. `python viz.py <slug>` → 產 `stories/<slug>/viz.html`(瀏覽器開):
   - **意圖鏈** technique→effect→theme(看孤兒技法 / 過載主題 / 空心主題)
   - **文本軸解剖** 張力曲線 + 意象復現 + 點擊跳原文
4. `/story-discuss <slug>` → 就這篇來回討論(有據、不諂媚)。

## Schema
見 `schemas/analysis.schema.json`。節點 6 型(theme/motif/technique/effect/character/beat),
邊 8 型;意圖鏈核心 = `produces`(technique→effect)+ `serves`(effect→theme);
`effect`/`beat` 帶 `intensity`(0–1)給曲線;`evidence.quote` 必須逐字對得上原文(硬閘門)。

## 依賴
python3、cytoscape.js(CDN,免裝)。Obsidian 為可選 viewer。

## 路線
- **L1**(目前):單篇端到端跑通。
- L2:schema 硬化、rubric 細修、viz 互動打磨、headless smoke test。
- L3:多篇 corpus、3D galaxy、跨故事檢索(屆時評估 MemPalace)、可換人格。
- L4:Web app(Agent SDK 後端 + 動畫前端)。
