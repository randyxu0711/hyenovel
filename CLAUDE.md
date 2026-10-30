# CLAUDE.md — hyenovel 工作定向

純文學短篇的**評論 / 思考討論工具**,跑在 Claude Code(**吃訂閱、不用 API token**)。
不是一次性產報告,而是會分析、給發展性回饋、能來回討論、把分析視覺化的個人思考工具。
使用者寫**中文/台語白話的純文學短篇**(<1 萬字)。

設計全貌見 `docs/DESIGN.md`;當前進度與待辦見 `docs/STATUS.md`。**動工前先讀這兩份。**

## 核心原則
- **DB(marrow,SQLite)= 正本**(切片 4a 起):觀察層(analysis)與判斷層(notes 備課筆記;舊作品是 feedback)由 den 的 job 寫進 `artifact`,
  web 只讀 den。`stories/<slug>/*.json` 是舊流程/匯入來源,**不再是正本**。分享檔用 `python -m export <slug>` 從 DB 匯出。
- **觀察與判斷隔離**:analyst 與 reviewer 是**兩個獨立步驟**(den 的工人各自 context),不可在同一 context 兼任,否則判斷獨立性被污染。
- **每條主張必引逐字原文**;引用閘門(`viz.py:locate`)會在原文搜尋驗證,幻覺引用直接擋(硬閘門)。
- Obsidian 為可選 viewer(匯出的 md 可放進 vault)。
- **marrow/**:DB 正本(SQLite)。切片 1–3 過渡期它曾是舊檔案的唯讀鏡像(舊 server 寫 `stories/`,
  `python -m marrow.importer` 冪等補進 DB);切片 4a 起翻案:web 改讀 den、DB 為正本;舊 `server/`(claude-agent-sdk 版後端)已於切片 5 刪除,
  importer 只作舊篇一次性匯入;根目錄 `viz.py`/`render.py` 留作函式庫,供 `export` 使用。DB 只支援 SQLite;repository 不寫方言 SQL,方言只准在 `marrow/db.py`。
  **切片 2 起 den 會寫 DB**:產物 commit 進 `artifact`,`current_artifact` 在 job 的**每一步成功時**換該 kind(analyst 好了 companion 就能用,不等 reviewer);
  importer 只對「新建」的 artifact 切 current,不覆蓋 den 已換的。

## 架構與資料流
```
MCP submit_work(檔案路徑) ─▶ den(背景 daemon)─ analyst ▶ reviewer ─▶ DB(artifact)
                                                                            │
                                 ┌──────────────────────────────────────────┤
                                 ▼                  ▼                        ▼
                         web(讀 den /api)  talk_to_companion(MCP)  python -m export <slug>
                                                                    ─▶ <slug>.md + <slug>.html
```
(舊流程:`stories/<slug>/source.md` → subagent → analysis.json/feedback.json → viz.py;已不再由 skill 觸發。)

## 怎麼用(任何目錄的 session,註冊 MCP 後都有)
- 入口是 MCP prompt:`/hyenovel:companion`(開始陪讀:交稿或直接聊)、`/hyenovel:continue`(接著聊最近那篇)。都不收參數(Claude Code 以空白切參數,路徑在對話裡給)。
- 陪讀 companion:宿主呼叫 MCP `talk_to_companion`(den 工人扮演、宿主原文轉述;模式 `direct`/`slow`/`imaginative`,人格在 `marrow/prompts/companion/`;素材只給原文+精簡分析,**不給 notes/feedback/結論**)。
- 作品用標題或開頭關鍵詞指定(`work="海"`),den 的 `GET /works` 比對(只看標題+開頭 200 字);多篇符合時回候選讓宿主問作者。
- `python -m export <slug> [--out DIR]` — 從 DB 匯出 `<slug>.md`(單一 front matter,先回饋後分析)與 `<slug>.html`(viz);預設輸出到 `stories/<slug>/`。
- `python -m den [--port N]` — 本機 daemon(127.0.0.1:8788,token 在 `~/.local/share/hyenovel/den.token`);
  舊 `stories/` 的篇要先 `python -m marrow.importer` 匯入;新篇由 `submit_work` 建立。工人 env 是白名單(無 `CLAUDE*`、
  無 `ANTHROPIC_API_KEY`、無 proxy 變數 / `CLAUDE_CONFIG_DIR`)。
  **MCP shim 會自動把 den 脫離拉起**(`den.json` 探索檔記 port/pid/指紋);den 閒置 3 小時無 job 自己結束。
  版本指紋不符才重啟,**忙碌中的 den 不重啟**(新版等跑完);`git pull` 後在 agent 內跑 `/mcp` 重載 shim。
  MCP 建立的故事 slug 是 `dNN`。
- web:`cd web && npm run dev`(vite 代理 `/api` 到 den 並帶 token)。用量面板關閉。
- 註冊 MCP:`claude mcp add hyenovel -- ~/projects/hyenovel/.venv/bin/python -m den.mcp`。五個 tool:
  `submit_work`(交稿,**只收 .md/.txt 路徑**;不給 path = 只續跑,絕不重跑)/ `talk_to_companion`(跟 companion 說話)/
  `find_works`(列作品+狀態,唯讀)/ `read_work`(原文/分析/備課筆記/舊回饋,唯讀)/ `cancel_work`(停下分析)。
  `readOnlyHint` 在 Claude Code **不會免確認**(只影響平行),要免問請加 allow 規則。
- `python viz.py <slug> [--check]` — 舊式出圖/驗引用(函式庫仍在,`export` 內部使用)。
- `.venv/bin/python -m pytest` — 跑全部測試(venv:`uv venv && uv pip install -r pyproject.toml -r requirements-dev.txt`)(零成本、不燒訂閱)。CI 在 push 時跑同一套。
- den 工人的 prompt 在 `marrow/prompts/{analyst,reviewer}.md`(`.claude/agents/analyst.md` 是舊流程遺留,den 不讀);舊 skill `story-critique`/`story-discuss` 已於 companion 第 2 批刪除。

## 慣例
- node id:theme=t* / motif=m* / technique=k* / effect=e* / character=c* / beat=b*。
- 意圖鏈核心邊:`produces`(technique→effect)、`serves`(effect→theme)。
- `effect`/`beat` 節點帶 `intensity`(0–1);beat 用 `precedes` 串成文本軸。
- notes(與舊 feedback)的 `refs` 綁 analysis 的 node id(viz 靠它錨定到圖);判斷層只配**同版**分析(`vizdata.pick_judgment`)。
- 改視覺化動 `viz/{template.html,viz.css,viz.js}`;`viz.py` 只負責驗證+注入。
- **故事內容(stories/<slug>/)是使用者創作,預設不 commit。** 程式碼才進版控。
- 討論逐字與結論存在 DB(`utterance` / `conclusion`)。結論的型別欄位叫 `kind` 不叫 `type`
  (`type` 已被 analysis node/edge 佔用)。
- **收束(從逐字煉結論)與跨篇 align 目前沒有**:舊實作(`server/settle.py`、`server/align.py`、
  根層 `settled.py`/`label_map.py`/`conclusions.py`/`recall.py`)隨切片 5 刪除,要看去 commit `e5b1724`;
  之後另開切片以 DB 重設計。舊版的硬教訓仍適用:冪等判定別只看單一來源(會重複花錢)、sweep 必須序列跑。
- 討論工人全程唯讀(`--tools ""`);den 端只寫 `discussion`/`utterance`。

## 測試(判準:這行的行為「是誰決定的」)
- **我們的政策 → 測**(即使長在 LLM 路徑上):重試/分流、閘門決策、slug 白名單、成本換算、
  fresh 才清孤兒…… SDK 不知道也不管這些。
- **外部 SDK/lib 的行為 → 不測**:`ClaudeSDKClient` 的 wire 行為、`jsonschema`/`pypdf` 本身。
  測它等於測自己寫的假 SDK,SDK 一改版會集體假綠(`total_cost_usd` 那個累計值 bug,任何 mock 都測不出來)。
- **確定性層(viz/render/export/atomicio/marrow)覆蓋門檻 100%**,CI 少一行就紅;
  `den/` 不設數字門檻,靠行為契約逐條有測。對純函式 100% 是真的,對混了接線的模組是演出來的。
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
