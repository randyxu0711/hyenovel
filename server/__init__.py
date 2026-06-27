"""hyenovel L4 後端 — 編排層程式化(B 方案:Claude Agent SDK 訂閱認證)。

職責三段(對應使用者需求):
  1. 受理前端觸發的分析任務          → POST /api/critique/{slug}
  2. 確定性編排兩個 subagent + 閘門   → orchestrator.run_critique
  3. 討論服務治理(長命 session)     → POST /api/discuss/{slug}
  外加:新增故事 ingestion           → POST /api/stories/extract、POST /api/stories

LLM 只出現在 4 個點:critique 的 analyst / criticizer 兩格 + discuss 對話。
閘門、重試判斷、座標、渲染、列表全是純 Python(viz.py / render.py / index.py),模型碰不到。
"""
