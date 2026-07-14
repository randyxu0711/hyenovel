# CLAUDE.md — hyenovel 工作定向

純文學短篇的**評論 / 思考討論工具**,跑在 Claude Code(**吃訂閱、不用 API token**)。
不是一次性產報告,而是會分析、給發展性回饋、能來回討論、把分析視覺化的個人思考工具。
使用者寫**中文/台語白話的純文學短篇**(<1 萬字)。

設計全貌見 `docs/DESIGN.md`;當前進度與待辦見 `docs/STATUS.md`。**動工前先讀這兩份。**

## 核心原則
- **`analysis.json` = 觀察層正本**(analyst 產);**`feedback.json` = 判斷層正本**(criticizer 產)。
  其餘(analysis.md / feedback.md / viz.html)都是它們的下游消費者。
- **觀察與判斷隔離**:analyst 與 criticizer 是**兩個獨立 subagent**(各自 context),不可在同一 context 兼任,否則判斷獨立性被污染。
- **每條主張必引逐字原文**;`viz.py` 會在 source.md 搜尋驗證,幻覺引用直接擋(硬閘門)。
- v1 **不接任何 DB**(MemPalace 退到 L3);Obsidian 為可選 viewer(`stories/` 即 vault)。

## 架構與資料流
```
stories/<slug>/source.md ──analyst(subagent)──▶ analysis.json
                                                     │
analysis.json + source.md ──criticizer(subagent)──▶ feedback.json
                                                     │
       ┌──────────────┬──────────────────────────────┘
       ▼              ▼
  analysis.md / feedback.md(人讀,Obsidian 友善)   viz.py ─▶ viz.html
```

## 怎麼用(在本專案目錄開的 session)
- `/story-critique stories/<slug>/source.md` — 跑完整鏈(analyst→引用閘門→criticizer→渲染→viz)。
- `/story-discuss <slug>` — 就一篇來回討論(出版編輯人格、有據、反諂媚)。
- `python viz.py <slug>` — 出 viz.html;`python viz.py <slug> --check` — 只驗引用(編排當閘門用)。
- `server/.venv/bin/python -m pytest` — 跑全部測試(零成本、不燒訂閱)。CI 在 push 時跑同一套。
- subagent 定義在 `.claude/agents/{analyst,criticizer}.md`;skill 在 `.claude/skills/`。
- **slash command 與 subagent 綁工作目錄**:必須在 `~/projects/hyenovel` 開的 session 才載入。

## 慣例
- node id:theme=t* / motif=m* / technique=k* / effect=e* / character=c* / beat=b*。
- 意圖鏈核心邊:`produces`(technique→effect)、`serves`(effect→theme)。
- `effect`/`beat` 節點帶 `intensity`(0–1);beat 用 `precedes` 串成文本軸。
- feedback 的 `refs` 綁 analysis 的 node id(viz 靠它把回饋錨定到圖)。
- 改視覺化動 `viz/{template.html,viz.css,viz.js}`;`viz.py` 只負責驗證+注入。
- **故事內容(stories/<slug>/)是使用者創作,預設不 commit。** 程式碼才進版控。

## 測試(判準:這行的行為「是誰決定的」)
- **我們的政策 → 測**(即使長在 LLM 路徑上):重試/分流、閘門決策、slug 白名單、成本換算、
  fresh 才清孤兒…… SDK 不知道也不管這些。
- **外部 SDK/lib 的行為 → 不測**:`ClaudeSDKClient` 的 wire 行為、`jsonschema`/`pypdf` 本身。
  測它等於測自己寫的假 SDK,SDK 一改版會集體假綠(`total_cost_usd` 那個累計值 bug,任何 mock 都測不出來)。
- **確定性層(viz/render/index/atomicio/ingest)覆蓋門檻 100%**,CI 少一行就紅;
  `server/` 不設數字門檻,靠行為契約逐條有測。對純函式 100% 是真的,對混了接線的模組是演出來的。
- **測試絕不碰 `stories/` 真實內容**(不可重現、CI runner 上根本沒有)。用 `tests/fixtures/mini` 合成樣本 + `tmp_path`。
- 引用閘門是**三層寬鬆匹配**(逐字→標點正規化→忽略空白),不是子字串比對。
  寫測試前先讀 `viz.py:locate`,否則「非子字串必擋」這種錯性質會抓到一堆假 bug。

## 視覺化(viz.html)
- ① 意圖鏈(cytoscape 分欄)② 文本軸解剖(SVG 張力曲線+意象復現+技法/效果打點)。
- 右側**常駐「編輯·討論」欄**:沒選→編輯總覽+最想聊的事;點節點→該節點分析+編輯回饋與提問(錨定)。
- `💬`/金邊 = 編輯點過的節點。網頁即時討論為 Phase 2(此欄即其座位)。

## 環境
WSL;使用者 Windows 檔在 `/mnt/c/Users/<user>/...`。viz.html 可複製到
`/mnt/c/Users/<user>/OneDrive/文件/stories/` 讓使用者於 Windows 雙擊(需網路,cytoscape 走 CDN)。
