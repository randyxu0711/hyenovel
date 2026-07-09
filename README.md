<div align="center">

<img src="assets/banner.svg" alt="hyenovel — 陪你拆解故事骨幹的討論夥伴" width="100%">

<br>

![runs on Claude Code](https://img.shields.io/badge/runs%20on-Claude%20Code-d97757?style=flat-square)
![stack](https://img.shields.io/badge/stack-Python%20%2B%20Node-c9a45e?style=flat-square)
![runtime](https://img.shields.io/badge/runtime-localhost%20only-8fb89a?style=flat-square)

**繁體中文** · [English](README.en.md)

</div>

> 純文學短篇的**評論 / 思考討論工具**,跑在 [Claude Code](https://claude.com/claude-code) —— **吃訂閱、不燒 API token**。

## 這是什麼 · 給誰

給**寫中文 / 台語白話純文學短篇(< 1 萬字)的人**。

它不是「貼進去、產一份讀後感」就結束的工具,而是一個會**分析、給發展性回饋、能來回討論、把分析視覺化**的個人思考夥伴 —— 陪你把一篇讀透、讀出所以然。一篇故事進來,兩個**刻意隔離**的 AI 分工:一個只**觀察**(拆出主題 / 意象 / 技法 / 效果 / 角色 / 節拍,每條掛逐字原文),另一個只**判斷**(出版編輯人格,給有輕重、不諂媚的發展性回饋)。觀察與判斷分開,判斷才獨立。

## 介面一覽

進站是一片星空,每篇故事是一根**資料驅動的星骨**(脊椎=張力曲線、肋=主題與意象);挑一篇俯衝進去,就進到單篇的三個視角。

<div align="center">
<img src="assets/demo.gif" alt="hyenovel 動態旅程:進站 → 選篇 → 俯衝 → 解剖" width="80%">
</div>

<div align="center">
<img src="assets/shot-catalog.png" alt="目錄星空:每篇是一根星骨" width="80%">
</div>

| 意圖鏈 | 文本軸解剖 | 發展性回饋 |
|:---:|:---:|:---:|
| ![意圖鏈](assets/shot-chain.png) | ![文本軸](assets/shot-axis.png) | ![回饋](assets/shot-feedback.png) |
| 技法 → 效果 → 主題,一條一條看懂「這招造成什麼後座力」 | 張力曲線 + 意象復現 + 技法/效果打點,沿文本軸攤開 | 編輯總覽、最關鍵的幾件事、強處、若只能改一件事 —— 每條錨定原文 |

## 為什麼不同

| 面向 | hyenovel | 一般「貼進 AI」的讀後感 |
|---|---|---|
| **觀察 vs 判斷** | 兩個隔離的 subagent:先觀察、再判斷,判斷獨立 | 單一模型一口氣寫完,觀察被判斷污染 |
| **引用** | 每條主張**必附逐字原文**;硬閘門搜原文驗證,幻覺引用直接擋 | 常憑印象發揮,難回溯到原文 |
| **計費** | 跑在 Claude Code、**吃訂閱**,不按 token 計費 | 按 API token 計費,越聊越貴 |
| **隱私** | 只跑 **localhost、單人**;你的創作不出本機 | 內容上傳雲端第三方 |
| **視覺化** | 意圖鏈(技法→效果→主題)+ 文本軸張力曲線 | 純文字條列 |
| **互動** | 能就一篇**來回討論**,反諂媚、有主見、會反問 | 一次性、傾向諂媚綜述 |

## 安裝

**前置**

- [Claude Code](https://claude.com/claude-code) 已安裝並登入 —— 本工具吃訂閱、不走 API 計費。
- Python 3、Node.js。

**步驟**

```bash
git clone https://github.com/randyxu0711/hyenovel.git
cd hyenovel

# 後端(Python)
python3 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements.txt

# 前端(Node);dev.sh 首次啟動也會自動補跑
cd web && npm install && cd ..
```

## 啟動與使用

### Web app(推薦)

```bash
./dev.sh          # 一鍵起前後端,Ctrl+C 一起收
```

開 http://localhost:5173 —— 挑一篇故事潛入,看意圖鏈 / 文本軸,讀編輯回饋,或就地來回討論。

> 只跑 localhost、單人使用;訂閱認證綁本機憑證,**別部署到雲端**。

### 命令列(在 repo 目錄開的 Claude Code session)

1. 把故事放成 `stories/<slug>/source.md`。
2. `/story-critique stories/<slug>/source.md` —— 跑完整評論鏈,產出分析 + 回饋。
3. `python viz.py <slug>` —— 出 `viz.html`(瀏覽器開):意圖鏈 + 文本軸解剖。
4. `/story-discuss <slug>` —— 就這篇來回討論(有據、不諂媚)。

## 運作原理

```
stories/<slug>/source.md ──analyst(subagent)──▶ analysis.json   觀察層正本
                                                     │
analysis.json + source.md ──criticizer(subagent)──▶ feedback.json 判斷層正本
                                                     │
                    ┌────────────────┬────────────────┘
                    ▼                ▼
        analysis.md / feedback.md(人讀)      viz.py ─▶ viz.html
```

觀察者與判斷者是**兩個各自 context 的 subagent**,不在同一 context 兼任 —— 判斷獨立性才不被污染。兩者的產物再餵給視覺化,把「技法 → 效果 → 主題」的意圖鏈與文本張力曲線畫出來。**每條主張都必須逐字對得上原文**(硬閘門,擋幻覺引用)。

> 想看內部契約與設計:`schemas/analysis.schema.json`、`docs/DESIGN.md`。

---

<div align="center">
<img src="assets/footer.svg" alt="hyenovel" width="100%">

<sub>故事內容(<code>stories/</code>)是使用者創作,不進版控;本 repo 只含程式碼與工具。</sub>
</div>
