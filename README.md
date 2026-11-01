<div align="center">

<img src="assets/banner.svg" alt="hyenovel — 陪你拆解故事骨幹的討論夥伴" width="100%">

<br>

![runs on Claude Code](https://img.shields.io/badge/runs%20on-Claude%20Code-d97757?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square)
![runtime](https://img.shields.io/badge/runtime-localhost%20only-6B7280?style=flat-square)

**繁體中文** · [English](README.en.md)

</div>

> 純文學短篇的**評論 / 思考討論工具**,跑在 [Claude Code](https://claude.com/claude-code) —— **吃訂閱、不燒 API token**。

## 這是什麼 · 給誰

給**寫中文 / 台語白話純文學短篇(< 1 萬字)的人**。

它不是「貼進去、產一份讀後感」就結束的工具,而是一個**陪讀者**:讀完你的稿、跟你來回聊、把分析視覺化 —— 陪你把一篇讀透、讀出所以然。一篇故事進來,背景有兩個**刻意隔離**的 AI 分工:一個只**觀察**(拆出主題 / 意象 / 技法 / 效果 / 角色 / 節拍,每條掛逐字原文),另一個是**中性讀者**,寫下真的讀到的感受、困惑與判斷(備課筆記,依輕重排序、不諂媚)。觀察與判斷分開,判斷才獨立。跟你聊的陪讀者只拿原文與精簡分析,**不看筆記**,用自己的讀法開口。

## 介面一覽

<!-- 截圖與 demo 待補 -->

點陣字、斑點、晝夜一鍵切換;三個畫面:

- **進門**:一句話、一個輸入框。直接交稿或開聊,下方列最近的作品,可以挑今天的陪讀者。
- **作品**:左邊是稿(紙面、讀者留下的痕跡、版本切換),右欄三個分頁 ——
  - **對話**:跟陪讀者來回聊;它引到哪一句,稿上就畫線到哪一句。
  - **筆記**:中性讀者的備課筆記,依輕重排序,每條錨定原文。
  - **結構圖**:點陣畫出的意圖鏈(技法 → 效果 → 主題)與文本張力。
- **設定**:外觀、語言、陪讀者、資料,都在獨立設定頁。

窄螢幕會變成單窗格切換;`⌘K` 開指令框,支援鍵盤操作。

## 為什麼不同

| 面向 | hyenovel | 一般「貼進 AI」的讀後感 |
|---|---|---|
| **觀察 vs 判斷** | 兩個隔離的 subagent:先觀察、再判斷,判斷獨立 | 單一模型一口氣寫完,觀察被判斷污染 |
| **引用** | 每條主張**必附逐字原文**;硬閘門搜原文驗證,幻覺引用直接擋 | 常憑印象發揮,難回溯到原文 |
| **計費** | 跑在 Claude Code、**吃訂閱**,整條 pipeline 不另按 token 計價;以 API 價目表估算,單篇 critique 約 **$0.7–0.9**(analyst + reviewer + 確定性層),多輪討論走快取更便宜 —— 這就是訂閱相對按 token 付費省下的部分 | 按 API token 計費,越聊越貴 |
| **隱私** | 只跑 **localhost、單人**;故事經你自己的 Claude Code 訂閱送給 Anthropic 處理,不進任何第三方審稿服務、也不另存廠商資料庫,創作留在本機資料庫 | 內容上傳雲端第三方審稿網站 |
| **視覺化** | 意圖鏈(技法→效果→主題)+ 文本張力,陪讀者說到哪句、稿上畫到哪句 | 純文字條列 |
| **互動** | 陪讀者能就一篇**來回聊**,三種讀法(直說 / 慢讀 / 想像);不附和、不教你改、會反問 | 一次性、傾向諂媚綜述 |

## 安裝

**前置**

- [Claude Code](https://claude.com/claude-code) 已安裝並登入 —— 本工具吃訂閱、不走 API 計費。
- Python 3、Node.js。

**步驟**

```bash
git clone https://github.com/randyxu0711/hyenovel.git
cd hyenovel

# 後端(Python)
uv venv --python 3.14
uv pip install -r pyproject.toml

# 前端(Node);dev.sh 首次啟動也會自動補跑
cd web && npm install && cd ..
```

## 啟動與使用

### Dashboard(主入口)

```bash
cd web && npm run build && cd ..   # 第一次與每次拉新版後
.venv/bin/python -m den.open       # 確保 den 在跑、開瀏覽器
```

`den.open` 會換一張一次性啟動碼(120 秒內有效)並開預設瀏覽器;開不了(WSL 常見)就點它印出的網址。den 同源送出 dashboard,API 都在 `/api`。

開發前端時改用 `./dev.sh`(確保 den 在跑 + 起 vite,開 http://localhost:5173;Ctrl+C 只收前端)。

舊用戶:舊 `stories/` 裡的篇要先跑一次 `python -m marrow.importer` 匯入。

> 只跑 localhost、單人使用;訂閱認證綁本機憑證,**別部署到雲端**。

### 在 agent 裡(任何目錄的 Claude Code session,需先註冊 hyenovel MCP,見 CLAUDE.md)

1. `/hyenovel:companion` —— 給一個 .md/.txt 路徑交稿(分析在背景跑),companion 先開口,接著來回聊。
2. `/hyenovel:continue` —— 接著聊最近那篇。找作品、看分析、停下分析直接用說的(「我有哪些作品」「給我看海那篇的分析」)。
3. `python -m export <slug>` —— 匯出可分享的 `<slug>.md` 與 `<slug>.html`(意圖鏈 + 文本軸解剖)。

## 運作原理

```
submit_work(檔案路徑)  ─▶ den ─ analyst ▶ reviewer ─▶ DB(正本:觀察層 + 判斷層)
                                                        │
                    ┌──────────────────┬────────────────┴────────────────┐
                    ▼                  ▼                                 ▼
            web(讀 den /api)   talk_to_companion(MCP)        python -m export ─▶ md + html
```

觀察者與判斷者是**兩個各自 context 的獨立步驟**,不在同一 context 兼任 —— 判斷獨立性才不被污染。分析一好陪讀者就能開聊,不必等筆記。兩者的產物再餵給視覺化,把「技法 → 效果 → 主題」的意圖鏈與文本張力曲線畫出來。**每條主張都必須逐字對得上原文**(硬閘門,擋幻覺引用)。

> 想看內部契約與設計:`schemas/analysis.schema.json`、`docs/DESIGN.md`。

---

<div align="center">
<img src="assets/footer.svg" alt="hyenovel" width="100%">
</div>
