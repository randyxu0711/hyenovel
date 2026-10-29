# CLAUDE.md — hyenovel 工作定向

純文學短篇的**評論 / 思考討論工具**,跑在 Claude Code(**吃訂閱、不用 API token**)。
不是一次性產報告,而是會分析、給發展性回饋、能來回討論、把分析視覺化的個人思考工具。
使用者寫**中文/台語白話的純文學短篇**(<1 萬字)。

設計全貌見 `docs/DESIGN.md`;當前進度與待辦見 `docs/STATUS.md`。**動工前先讀這兩份。**

## 核心原則
- **DB(marrow,SQLite)= 正本**(切片 4a 起):觀察層(analysis)與判斷層(feedback)由 den 的 job 寫進 `artifact`,
  web 只讀 den。`stories/<slug>/*.json` 是舊流程/匯入來源,**不再是正本**。分享檔用 `python -m export <slug>` 從 DB 匯出。
- **觀察與判斷隔離**:analyst 與 criticizer 是**兩個獨立步驟**(den 的工人各自 context),不可在同一 context 兼任,否則判斷獨立性被污染。
- **每條主張必引逐字原文**;引用閘門(`viz.py:locate`)會在原文搜尋驗證,幻覺引用直接擋(硬閘門)。
- Obsidian 為可選 viewer(匯出的 md 可放進 vault)。
- **marrow/**:DB 正本(SQLite)。切片 1–3 過渡期它曾是舊檔案的唯讀鏡像(舊 server 寫 `stories/`,
  `python -m marrow.importer` 冪等補進 DB);切片 4a 起翻案:web 改讀 den、DB 為正本,舊 `server/` 於切片 5 退役,
  importer 只作舊篇一次性匯入;根目錄 `viz.py`/`render.py` 留作函式庫,供 `export` 使用。DB 只支援 SQLite;repository 不寫方言 SQL,方言只准在 `marrow/db.py`。
  **切片 2 起 den 會寫 DB**:產物 commit 進 `artifact`,`current_artifact` 只在 job **全部步驟成功**時一次換;
  importer 只對「新建」的 artifact 切 current,不覆蓋 den 已換的。

## 架構與資料流
```
MCP start_critique(檔案路徑) ─▶ den(背景 daemon)─ analyst ▶ criticizer ─▶ DB(artifact)
                                                                            │
                                 ┌──────────────────────────────────────────┤
                                 ▼                  ▼                        ▼
                         web(讀 den /api)   open_discussion(MCP)   python -m export <slug>
                                                                    ─▶ <slug>.md + <slug>.html
```
(舊流程:`stories/<slug>/source.md` → subagent → analysis.json/feedback.json → viz.py;已不再由 skill 觸發。)

## 怎麼用(在本專案目錄開的 session)
- `/story-critique <檔案路徑>` — 呼叫 MCP `start_critique` 送文、轉告預估、問進度時 `critique_status`。
- `/story-discuss <slug>` — 先 `open_discussion` 取素材再來回討論(出版編輯人格、有據、反諂媚);**結論不會被保存**。
- `python -m export <slug> [--out DIR]` — 從 DB 匯出 `<slug>.md`(單一 front matter,先回饋後分析)與 `<slug>.html`(viz);預設輸出到 `stories/<slug>/`。
- `python -m den [--port N]` — 本機 daemon(127.0.0.1:8788,token 在 `~/.local/share/hyenovel/den.token`);
  舊 `stories/` 的篇要先 `python -m marrow.importer` 匯入;新篇由 `start_critique` 建立。工人 env 是白名單(無 `CLAUDE*`、
  無 `ANTHROPIC_API_KEY`、無 proxy 變數 / `CLAUDE_CONFIG_DIR`)。
  **MCP shim 會自動把 den 脫離拉起**(`den.json` 探索檔記 port/pid/指紋);den 閒置 3 小時無 job 自己結束。
  版本指紋不符才重啟,**忙碌中的 den 不重啟**(新版等跑完);`git pull` 後在 agent 內跑 `/mcp` 重載 shim。
  MCP 建立的故事 slug 是 `dNN`。
- web:`cd web && npm run dev`(vite 代理 `/api` 到 den 並帶 token)。網頁討論與用量面板在切片 4b 前關閉(討論改用 `open_discussion`)。
- 註冊 MCP:`claude mcp add hyenovel -- ~/projects/hyenovel/server/.venv/bin/python -m den.mcp`。五個 tool:
  `start_critique`(送文開分析)/ `critique_status`(進度)/ `cancel_critique`(取消)/
  `resume_critique`(續跑)/ `open_discussion`(取討論素材開聊)。
- `python viz.py <slug> [--check]` — 舊式出圖/驗引用(函式庫仍在,`export` 內部使用)。
- `server/.venv/bin/python -m pytest` — 跑全部測試(零成本、不燒訂閱)。CI 在 push 時跑同一套。
- subagent 定義在 `.claude/agents/{analyst,criticizer}.md`(den 工人沿用);skill 在 `.claude/skills/`。
- **slash command 與 subagent 綁工作目錄**:必須在 `~/projects/hyenovel` 開的 session 才載入。

## 慣例
- node id:theme=t* / motif=m* / technique=k* / effect=e* / character=c* / beat=b*。
- 意圖鏈核心邊:`produces`(technique→effect)、`serves`(effect→theme)。
- `effect`/`beat` 節點帶 `intensity`(0–1);beat 用 `precedes` 串成文本軸。
- feedback 的 `refs` 綁 analysis 的 node id(viz 靠它把回饋錨定到圖)。
- 改視覺化動 `viz/{template.html,viz.css,viz.js}`;`viz.py` 只負責驗證+注入。
- **故事內容(stories/<slug>/)是使用者創作,預設不 commit。** 程式碼才進版控。
- **討論兩份正本**:`transcript.jsonl`(逐字,`server/transcript.py` 逐輪寫)、
  `conclusions.jsonl`(蒸餾結論,`conclusions.py` 是唯一寫入者與閘門)。
  結論的型別欄位叫 `kind` 不叫 `type`(`type` 已被 analysis node/edge 佔用)。
- **收束是自動的,沒有使用者入口**:討論局被 `sweep_idle` 回收後,`server/settle.py` 開專用
  client 從逐字煉成結論。水位在 `settled.jsonl`(根層 `settled.py`),**判定同時看它與
  conclusions 的 `provenance.session`** —— 單看任一邊都有一個會重複花錢的洞。
  `sweep_settle` 必須序列跑,不可扇出(會煉兩次)。
- 討論的 LLM 全程唯讀:結論由它吐 JSON 文字、確定性層驗過才落地。唯讀是**兩層**——
  `allowed_tools=["Read"]` 加上 `_READONLY_GUARD_HOOKS`(寫入根為空,任何檔案寫入硬擋)。
  **唯讀 client(discuss/settle/align)不共用 critique 的寫入白名單**:共用時它們對整棵
  `stories/` 是暢通的,「唯讀」只剩 SDK 那一層在守,而那一層擋不擋從未被證實。
  新增任何宣稱唯讀的 client,掛 `_READONLY_GUARD_HOOKS`,別掛 `_CRITIQUE_GUARD_HOOKS`。

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
