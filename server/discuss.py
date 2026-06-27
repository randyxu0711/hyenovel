"""討論服務治理:長命 ClaudeSDKClient 的 session registry + 逐 token 串流。

每個討論 session = 一個活著的 ClaudeSDKClient(底層一支 claude 行程),跨 HTTP 請求存活。
個人單機:每個 session 一把 lock 序列化輪次;閒置逾時由背景 sweeper 回收。

事件信封:
  token   {text}             逐 token delta
  message {role, text, session_id}   整輪收尾(存檔 / 非串流 fallback)
  done    {ok, cost_usd, session_id}
  error   {where, message, recoverable}
"""
import asyncio
import time
import uuid

from claude_agent_sdk import (
    ClaudeSDKClient, AssistantMessage, TextBlock, StreamEvent, ResultMessage,
)

from . import config, sdk_runner


class Session:
    def __init__(self, slug: str, client: ClaudeSDKClient):
        self.slug = slug
        self.client = client
        self.sdk_session_id: str | None = None   # SDK 端對話 id(供未來 resume)
        self.last_active = time.time()
        self.lock = asyncio.Lock()


_sessions: dict[str, Session] = {}


def list_sessions(slug: str) -> list[dict]:
    return [{"session_id": sid, "last_active": s.last_active}
            for sid, s in _sessions.items() if s.slug == slug]


async def close_session(session_id: str) -> bool:
    s = _sessions.pop(session_id, None)
    if not s:
        return False
    try:
        await s.client.disconnect()
    except Exception:
        pass
    return True


async def sweep_idle():
    """背景:回收閒置逾時的 session,避免洩漏 claude 行程。"""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        stale = [sid for sid, s in _sessions.items()
                 if now - s.last_active > config.DISCUSS_IDLE_TIMEOUT and not s.lock.locked()]
        for sid in stale:
            await close_session(sid)


async def run_discuss(slug: str, session_id: str | None, message: str):
    if not (config.STORIES / slug / "analysis.json").exists():
        yield {"event": "error", "data": {"where": "input",
               "message": f"{slug} 還沒分析,先跑 critique", "recoverable": False}}
        return

    sess = _sessions.get(session_id) if session_id else None
    new = sess is None

    try:
        if new:
            client = ClaudeSDKClient(options=sdk_runner.discuss_options())
            await client.connect()
            sid = uuid.uuid4().hex[:12]
            sess = Session(slug, client)
            _sessions[sid] = sess
            # 新 session 開場:引 story-discuss skill(讀 analysis/feedback/source,提切入點)
            prompt = f"/story-discuss {slug}"
            if message.strip():
                prompt += f"\n\n{message}"
        else:
            sid = session_id
            prompt = message
    except Exception as e:
        yield {"event": "error", "data": {"where": "connect", "message": str(e), "recoverable": True}}
        return

    async with sess.lock:
        sess.last_active = time.time()
        final, cost = "", 0.0
        try:
            await sess.client.query(prompt)
            async for m in sess.client.receive_response():
                if isinstance(m, StreamEvent):
                    txt = sdk_runner.delta_text(m)
                    if txt:
                        yield {"event": "token", "data": {"text": txt}}
                elif isinstance(m, AssistantMessage):
                    for b in m.content:
                        if isinstance(b, TextBlock):
                            final = b.text
                elif isinstance(m, ResultMessage):
                    cost = m.total_cost_usd or 0.0
                    if m.session_id:
                        sess.sdk_session_id = m.session_id
        except Exception as e:
            yield {"event": "error", "data": {"where": "discuss", "message": str(e), "recoverable": True}}
            return
        sess.last_active = time.time()
        yield {"event": "message", "data": {"role": "assistant", "text": final, "session_id": sid}}
        yield {"event": "done", "data": {"ok": True, "cost_usd": round(cost, 4), "session_id": sid}}
