"""ClaudeSDKClient 薄包裝:統一 options + 把 SDK 訊息收斂成我們要的東西。

兩種用法:
  - critique:一個協調者 client 連續發 query(派 analyst→看閘門→派 criticizer),
    不需 token 串流;run_turn() 把一輪跑完、回成本。
  - discuss:長命 client + token 串流(在 discuss.py 直接消費 receive_response)。
"""
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock, ResultMessage,
)
from . import config


def critique_options() -> ClaudeAgentOptions:
    """協調者:cwd 指本專案 → 原封載入 analyst/criticizer subagent 與閘門。
    只給 Read/Write/Task(派子代理);acceptEdits 讓無人值守也能落 json。"""
    return ClaudeAgentOptions(
        cwd=str(config.ROOT),
        setting_sources=["project"],          # 只載專案 .claude/,跳過全域 plugin
        allowed_tools=["Read", "Write", "Task"],
        permission_mode="acceptEdits",        # 自動收 edit,後端無人按核准
        model=config.CRITIQUE_MODEL,
        max_budget_usd=config.CRITIQUE_BUDGET_USD,
        include_partial_messages=False,       # critique 只要進度,不要逐 token
    )


def discuss_options(resume: str | None = None) -> ClaudeAgentOptions:
    """討論:read-only(v1 不開寫回 analysis.json),逐 token 串流。
    resume 帶 SDK session id → 斷線後接回同一對話。"""
    return ClaudeAgentOptions(
        cwd=str(config.ROOT),
        setting_sources=["project"],
        allowed_tools=["Read"],               # v1 唯讀:聊天不誤改正本
        permission_mode="default",
        model=config.DISCUSS_MODEL,
        include_partial_messages=True,        # 逐 token delta
        resume=resume,
    )


async def run_turn(client: ClaudeSDKClient, prompt: str):
    """送一輪 prompt、把回應抽乾,回 (summary_text, cost_usd, is_error)。
    給 critique 協調者用:我們只在意它完成了、花多少,內容看閘門結果。"""
    await client.query(prompt)
    text, cost, err = "", 0.0, False
    async for m in client.receive_response():
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    text = b.text
        elif isinstance(m, ResultMessage):
            cost = m.total_cost_usd or 0.0
            err = bool(m.is_error)
    return text, cost, err


def delta_text(stream_event) -> str | None:
    """從 StreamEvent 抽純文字 delta(content_block_delta / text_delta);其餘回 None。"""
    ev = getattr(stream_event, "event", None) or {}
    if isinstance(ev, dict) and ev.get("type") == "content_block_delta":
        delta = ev.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text") or None
    return None
