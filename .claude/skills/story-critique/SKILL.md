---
name: story-critique
description: 對一篇純文學短篇跑完整評論鏈。編排 analyst(產 analysis.json)→ criticizer(產 feedback.md)→ 渲染 analysis.md → 產 viz.html。用於使用者要「分析/評論一篇故事」「跑 critique」時。輸入是 stories/<slug>/source.md 的路徑或 slug。
---

# story-critique:故事評論編排

對一篇短篇跑完整鏈:**analyst → criticizer → 渲染 → 視覺化**。
核心原則:`analysis.json` 是唯一正本,其餘都是它的下游。analyst 與 criticizer **必須用獨立 subagent 跑**(隔離 context,保判斷獨立)。

## 輸入
使用者給 `stories/<slug>/source.md` 路徑或 `<slug>`。解析出 `<slug>` 與資料夾。
若 `source.md` 不存在,請使用者先把故事放進去,停止。

## 步驟

### 1. analyst(隔離 subagent)
用 Task 工具呼叫 `analyst` subagent,prompt 給它故事資料夾路徑,要求:
> 分析 `stories/<slug>/`,讀 source.md 與 schemas/analysis.schema.json,產出 stories/<slug>/analysis.json。

等它完成。確認 `stories/<slug>/analysis.json` 已生成。

### 2. 驗證引用硬閘門
跑 `python viz.py <slug> --check`(只驗證、不出圖)。
- 若有 quote 對不上原文 → 把對不上的清單回報,**請 analyst 修正**(再呼叫一次 analyst,指出哪些 quote 找不到),直到全數通過。
- 全通過才往下。

### 3. criticizer(隔離 subagent)
用 Task 工具呼叫 `criticizer` subagent,prompt 給它故事資料夾路徑,要求:
> 讀 stories/<slug>/analysis.json、source.md 與 schemas/feedback.schema.json,產出 stories/<slug>/feedback.json(發展性、有輕重、不諂媚,每點掛逐字 quotes 並用 refs 綁 node id)。

等它完成。確認 `feedback.json` 已生成。

### 4. 渲染 analysis.md / feedback.md(人讀,Obsidian 友善)
- 讀 analysis.json → `stories/<slug>/analysis.md`:YAML frontmatter(title、slug、tags:[hyenovel, story-analysis]);主題/意象/技法/效果/角色分節,每條附 note 與引文;意圖鏈清單(technique →produces→ effect →serves→ theme);主題與意象間用 `[[wikilink]]` 互連。
- 讀 feedback.json → `stories/<slug>/feedback.md`:編輯給作者的信口吻;依序「這篇在做什麼 / 最有效的地方 / 我會往下推的 2–3 件事(含實驗與提問)/ 枝節 / 一句話」。

### 5. 視覺化
跑 `python viz.py <slug>` → 產 `stories/<slug>/viz.html`(viz.py 會同時讀 analysis.json 與 feedback.json,把回饋接進常駐「編輯」欄並錨定節點)。回報路徑。

### 6. 回報
摘要:核心主題、criticizer 點出的 2–3 件關鍵事、節點/邊數、viz.html 路徑。
提示使用者可用 `/story-discuss <slug>` 深入討論、或瀏覽器開 viz.html。

## 注意
- analyst / criticizer 一定要走 subagent(不要自己在主 context 直接寫 json/feedback),否則隔離失效。
- 全程不需任何 API key、不接 MCP/DB。
