"""Critique 執行治理:把一次分析跑成「獨立背景任務」,與 HTTP 連線解耦。

問題:舊版把 orchestrator 直接掛在 SSE 連線上——前端一重整,連線斷了,
但背景那支 claude 還在跑(燒訂閱),前端既看不到也停不掉。

解法:每個 slug 一個 Run = 一條 asyncio.Task 跑 orchestrator,事件寫進
緩衝並廣播給所有訂閱者。連線只是「訂閱者」,斷了不影響 Run;重整後可:
  - GET  /api/critique/running   查還在跑的
  - POST /api/critique/{slug}    重新接上(補播已發事件 → 繼續直播)
  - DELETE /api/critique/{slug}  取消(cancel Task → orchestrator 的
                                  ClaudeSDKClient __aexit__ 收掉 claude 行程)
"""
import asyncio
import time

from . import orchestrator

# phase name → 生長階(給 /running 顯示、前端成形動畫對齊)
_STEP = {"analyst": 1, "criticizer": 2, "render": 3}
_DONE_TTL = 600   # 已結束的 Run 留多久(秒)讓晚到的重整還接得到 done


class Run:
    def __init__(self, slug: str, title: str):
        self.slug = slug
        self.title = title
        self.events: list[dict] = []                 # 已發事件(補播用)
        self.subscribers: set[asyncio.Queue] = set()
        self.status = "running"                       # running|done|error|cancelled
        self.step = 0
        self.cost = 0.0
        self.task: asyncio.Task | None = None
        self.client = None                            # 當前 ClaudeSDKClient(取消時直接 disconnect)
        self.finished = asyncio.Event()
        self.started = time.time()


_runs: dict[str, Run] = {}


def list_running() -> list[dict]:
    return [{"slug": r.slug, "title": r.title, "status": r.status, "step": r.step}
            for r in _runs.values() if r.status == "running"]


def _record(run: Run, ev: dict):
    """記一個事件:更新狀態/相位,並廣播給所有訂閱者(同步,無 await → 對事件迴圈原子)。"""
    run.events.append(ev)
    kind = ev.get("event")
    data = ev.get("data", {})
    if kind == "phase":
        step = _STEP.get(data.get("name"), 0)
        if data.get("status") == "ok":
            step += 1
        run.step = max(run.step, step)
    elif kind == "done":
        run.status = "done"
        run.cost = data.get("cost_usd", run.cost)
        run.step = 4
    elif kind == "error" and run.status == "running":
        run.status = "error"
    for q in list(run.subscribers):
        q.put_nowait(ev)


async def _drive(run: Run):
    """背景跑 orchestrator,把事件灌進緩衝/廣播。獨立於任何 HTTP 連線。"""
    def _hold(c):
        run.client = c
    try:
        async for ev in orchestrator.run_critique(run.slug, on_client=_hold):
            _record(run, ev)
    except asyncio.CancelledError:
        if run.status == "running":
            run.status = "cancelled"
        _record(run, {"event": "error",
                      "data": {"where": "cancel", "message": "已取消", "recoverable": False}})
        raise
    except Exception as e:  # noqa: BLE001 —— 任何意外都收斂成 error 事件,不讓 Task 默默死掉
        # 取消會先 disconnect client,使 receive 拋連線錯誤而非 CancelledError;
        # 已標記 cancelled 就別覆蓋成 error。
        if run.status == "running":
            run.status = "error"
            _record(run, {"event": "error",
                          "data": {"where": "run", "message": str(e), "recoverable": False}})
        else:
            _record(run, {"event": "error",
                          "data": {"where": "cancel", "message": "已取消", "recoverable": False}})
    finally:
        run.client = None
        run.finished.set()
        for q in list(run.subscribers):
            q.put_nowait(None)   # 串流結束哨兵


def start(slug: str, title: str) -> Run:
    """開一個 Run;若該 slug 已在跑就回既有的(避免重整/重送造成雙重派工燒錢)。"""
    cur = _runs.get(slug)
    if cur and cur.status == "running":
        return cur
    run = Run(slug, title or (cur.title if cur else slug))
    _runs[slug] = run
    run.task = asyncio.create_task(_drive(run))
    return run


async def attach(slug: str, title: str):
    """開始-或-接上:先補播已發事件,再直播後續到串流結束。"""
    run = start(slug, title)
    q: asyncio.Queue = asyncio.Queue()
    run.subscribers.add(q)             # 先註冊,再快照 backlog —— 兩行間無 await,
    backlog = list(run.events)         # 故已發的進 backlog、之後的進 q,不漏不重
    done_already = run.finished.is_set()
    try:
        for ev in backlog:
            yield ev
        if done_already:
            return
        while True:
            ev = await q.get()
            if ev is None:
                break
            yield ev
    finally:
        run.subscribers.discard(q)


async def cancel(slug: str) -> bool:
    run = _runs.get(slug)
    if not run or run.status != "running" or not run.task:
        return False
    run.status = "cancelled"        # 先標記,_drive 的 except 才不會誤判成 error
    client = run.client
    if client is not None:
        try:
            await client.disconnect()   # 直接收掉 claude 子行程(task.cancel 在 __aexit__ 期間會漏掉)
        except Exception:               # noqa: BLE001
            pass
    run.task.cancel()
    try:
        await run.task
    except BaseException:  # noqa: BLE001 —— 取消必然拋 CancelledError/連線錯誤,吞掉
        pass
    return True


async def sweep_runs():
    """背景:清掉結束已久的 Run,避免 _runs 無限長。"""
    while True:
        await asyncio.sleep(120)
        now = time.time()
        for slug in [s for s, r in _runs.items()
                     if r.status != "running" and now - r.started > _DONE_TTL]:
            _runs.pop(slug, None)
