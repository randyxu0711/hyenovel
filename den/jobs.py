"""job worker + 事件匯流排。

- **先持久化再回應**(§3.4):submit 在回傳前 create_job 並 commit。
- 一次只跑一個 job:這條 worker 迴圈本身就是 semaphore=1;沒 job 時等 Event,不輪詢。
- job 狀態只有 worker(與 queued 的 cancel)寫;引擎只裁決(StepOutcome)。
- 取消分兩種:使用者取消當前 job → 寫 cancelled(可續);app 關機取消 worker → 不寫,
  留 running 給下次 startup 判 crash。
- sqlite3 連線只在事件迴圈執行緒上用,不丟 to_thread。
"""
import asyncio
import logging
import time
from typing import Callable

from den import pipeline
from den.estimate import estimate
from marrow import repo

log = logging.getLogger("hyenovel")

_DONE_TTL = 600   # 結束的 job 事件留多久(秒)讓晚到的訂閱還接得到收尾

RunFactory = Callable[[Callable | None], pipeline.RunFn]


class EventBus:
    """每 job 一串事件:subscribe 先補播已發的,再直播後續。"""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self._now = now
        self._events: dict[int, list[dict]] = {}
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._closed: dict[int, float] = {}

    def _prune(self) -> None:
        cut = self._now() - _DONE_TTL
        for jid in [j for j, t in self._closed.items() if t < cut]:
            self._closed.pop(jid)
            self._events.pop(jid, None)

    def reset(self, job_id: int) -> None:
        """續跑排入時清掉上一輪事件(否則新訂閱者先看到上一輪的 error,SSE 就地收尾)。"""
        self._events[job_id] = []
        self._closed.pop(job_id, None)

    def publish(self, job_id: int, ev: dict) -> None:
        self._prune()
        self._events.setdefault(job_id, []).append(ev)
        for q in self._subs.get(job_id, ()):
            q.put_nowait(ev)

    def close(self, job_id: int) -> None:
        self._closed[job_id] = self._now()

    def subscribe(self, job_id: int) -> asyncio.Queue:
        self._prune()
        q: asyncio.Queue = asyncio.Queue()
        for ev in self._events.get(job_id, ()):   # 補播與註冊之間無 await,不會漏
            q.put_nowait(ev)
        self._subs.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: int, q: asyncio.Queue) -> None:
        subs = self._subs.get(job_id)
        if subs is not None:
            subs.discard(q)
            if not subs:
                del self._subs[job_id]


def _error(where: str | None, reason: str, message: str) -> dict:
    return {"event": "error", "data": {"where": where, "message": message,
                                       "recoverable": True, "reason": reason}}


class JobManager:
    def __init__(self, conn, run_factory: RunFactory, *, runner_name: str,
                 cli_version: str | None, now: Callable[[], float] = time.time):
        self.conn = conn
        self.bus = EventBus()
        self._run_factory = run_factory
        self._runner_name = runner_name
        self._cli_version = cli_version
        self._now = now
        self._wake = asyncio.Event()
        self._current: tuple[int, asyncio.Task] | None = None
        self._step: str | None = None

    def startup(self) -> None:
        with self.conn:
            ids = repo.recover_running_jobs(self.conn, self._now())
        for jid in ids:
            log.info("event=job-recovered job=%s", jid)

    def submit(self, slug: str, client: dict | None = None, runner: str | None = None) -> dict:
        st = repo.story_by_slug(self.conn, slug)
        if st is None:
            log.info("event=submit-rejected reason=unknown-slug")
            raise LookupError(slug)
        sv = repo.latest_source_version(self.conn, st["id"])
        # 預估在 create_job 之前算:算壞了不能留下一個 client 不知道的 job
        est = estimate({s: repo.attempt_history(self.conn, s) for s in pipeline.CRITIQUE},
                       len(sv["text"]))
        with self.conn:
            jid = repo.create_job(self.conn, "critique", st["id"], sv["id"],
                                  {"client": client, "runner": runner}, self._now())
        log.info("event=job-submitted job=%s client=%r runner=%s", jid, client, runner)
        self._wake.set()
        return {"job_id": jid, "estimate": est}

    def cancel(self, job_id: int) -> bool:
        if self._current is not None and self._current[0] == job_id:
            # cancel() 回 False = task 已跑完、worker 還沒收尾:結果照寫,不算取消
            if self._current[1].cancel():
                log.info("event=job-cancel job=%s state=running", job_id)
                return True
        else:
            job = repo.get_job(self.conn, job_id)
            if job is not None and job["state"] == "queued":
                with self.conn:
                    repo.set_job_state(self.conn, job_id, "cancelled", self._now())
                self.bus.publish(job_id, _error(None, "cancelled", "已取消"))
                self.bus.close(job_id)
                log.info("event=job-cancel job=%s state=queued", job_id)
                return True
        log.info("event=cancel-rejected job=%s", job_id)
        return False

    def resume(self, job_id: int) -> bool:
        with self.conn:
            ok = repo.requeue_job(self.conn, job_id, self._now())
        if not ok:
            log.info("event=resume-rejected job=%s", job_id)
            return False
        self.bus.reset(job_id)   # 排隊期間的新訂閱者不能被補播上一輪的收尾 error
        log.info("event=job-resume job=%s", job_id)
        self._wake.set()
        return True

    def _emit(self, job_id: int, ev: dict) -> None:
        if ev.get("event") == "phase" and ev["data"].get("status") == "start":
            self._step = ev["data"]["name"]
            with self.conn:
                repo.set_job_state(self.conn, job_id, "running", self._now(), step=self._step)
        self.bus.publish(job_id, ev)

    def _finish(self, job_id: int, state: str, error_class=None, detail=None) -> None:
        with self.conn:
            repo.set_job_state(self.conn, job_id, state, self._now(),
                               error_class=error_class, detail=detail)
        log.info("event=job-end job=%s state=%s class=%s", job_id, state, error_class)

    async def _run(self, job: dict) -> None:
        jid = job["id"]
        self._step = None

        async def go() -> pipeline.StepOutcome:   # run_factory 的例外也要落在下面的 crash 收尾
            return await pipeline.run_critique(
                self.conn, job, self._run_factory(None), lambda ev: self._emit(jid, ev),
                runner_name=self._runner_name, cli_version=self._cli_version, now=self._now)
        task = asyncio.create_task(go())
        self._current = (jid, task)
        try:
            out = await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():   # 關機:worker 自己被取消
                raise
            self._finish(jid, "cancelled")
            self.bus.publish(jid, _error(self._step, "cancelled", "已取消"))
        except Exception:
            log.exception("event=job-crash job=%s", jid)
            self._finish(jid, "failed", "crash", {"message": "worker 例外"})
            self.bus.publish(jid, _error(self._step, "crash", "worker 例外"))
        else:
            self._finish(jid, out.state, out.error_class, out.detail)
        finally:
            self._current = None
        self.bus.close(jid)

    async def worker(self) -> None:
        while True:
            with self.conn:
                job = repo.claim_next_job(self.conn, self._now())
            if job is None:
                self._wake.clear()     # claim 與 clear 之間無 await,submit 不會被漏
                await self._wake.wait()
                continue
            log.info("event=job-start job=%s", job["id"])
            await self._run(job)
