---
name: story-critique
description: 把一篇純文學短篇送進 den 跑完整評論鏈(分析→編輯評論),走 hyenovel MCP 的 start_critique。用於使用者要「分析/評論一篇故事」「跑 critique」「看進度」時。輸入是 .md / .txt 檔案路徑(改稿重跑可帶 slug)。
---

# story-critique:送文、報預估、查進度

評論鏈由 den(背景 daemon)執行,結果寫進 DB,網頁讀得到。你只負責呼叫 MCP tool 並轉告,**不自己分析、不寫檔**。

## 規則
1. **用 `start_critique` 送文,參數是檔案路徑。** 不貼全文、不自己讀完再轉述。
   例:使用者說「評論 ~/novels/海.md」→ `start_critique(path="~/novels/海.md")`。
2. **只收 .md / .txt。** 使用者給 pdf/docx 時請他先轉成純文字檢查過,再送。
3. **改稿重跑要帶上次回的 slug。** 例:使用者說「我改了 d03,再跑一次」→ `start_critique(path=..., slug="d03")`。
4. **送出後立刻轉告 slug、job id 與預估**(時間、訂閱額度),並說明這是分鐘級背景工作。例:「已送出,slug d03、job 12,預估約 6 分鐘,用的是你的 Claude 訂閱額度。」
5. **使用者問進度才呼叫 `critique_status`。** 不要自己輪詢。新對話找不到 job 編號時,不帶 job_id 呼叫列出最近的 job。
6. **停住時講原因並提議續跑。** 狀態是暫停/失敗/取消 → 轉告原因,問使用者要不要 `resume_critique`;要取消用 `cancel_critique`。例:「額度用完而暫停,要我續跑嗎?已完成的步驟不重跑。」
7. **完成後指路,不自己寫摘要。** 說:網頁(`cd web && npm run dev`)看結果、`/story-discuss <slug>` 來回討論、`python -m export <slug>` 匯出可分享的 md + html。

## 禁止
- 不要派 analyst / criticizer subagent,不要寫 `stories/<slug>/`,不要跑 `viz.py` / `render.py`——那是舊流程,產物網頁看不到。
