import asyncio
import logging

from den import digest
from den.config import MAX_THREADS, PRIOR_MIN_USER_TURNS, PRIOR_SESSIONS
from marrow import gate, repo

log = logging.getLogger("hyenovel")

SETTING = "prior.enabled"


def enabled(conn) -> bool:
    return repo.get_setting(conn, SETTING) != "0"


def set_enabled(conn, on: bool) -> None:
    repo.set_setting(conn, SETTING, "1" if on else "0")


def _recent(conn, story_id: int, exclude: int | None) -> list[dict]:
    return repo.prior_discussions(conn, story_id, exclude=exclude, limit=PRIOR_SESSIONS,
                                  min_user_turns=PRIOR_MIN_USER_TURNS)


def is_stale(thread: dict, latest_source: str) -> bool:
    return thread["source_quote"] is not None and gate.locate(thread["source_quote"], latest_source) is None


def gather(conn, story_id: int, exclude: int | None, latest_source: str) -> dict:
    digests, live, stale = [], [], []
    for d in _recent(conn, story_id, exclude):
        cur = repo.current_digest(conn, d["id"])
        if cur is None:
            continue
        digests.append({"id": cur["id"], "session": d["external_id"], "at": d["ended_at"],
                        "text": cur["text"], "edited": bool(cur["edited"])})
        for t in repo.threads_of(conn, cur["root_id"]):
            if t["ended_at"] is not None:
                continue
            row = {"id": t["id"], "root_id": cur["root_id"], "text": t["text"], "quote": t["quote"],
                   "source_quote": t["source_quote"], "at": d["ended_at"], "session": d["external_id"],
                   "stale": is_stale(t, latest_source)}
            (stale if row["stale"] else live).append(row)
    return {"digests": digests, "threads": live[:MAX_THREADS] + stale}


class PriorQueue:
    def __init__(self, conn, chat):
        self.conn, self.chat = conn, chat
        self.tasks: dict[int, asyncio.Task] = {}

    def running(self, story_id: int) -> bool:
        t = self.tasks.get(story_id)
        return t is not None and not t.done()

    def ensure(self, story_id: int) -> None:
        if self.chat is None or self.running(story_id):
            return
        self.tasks[story_id] = asyncio.get_running_loop().create_task(self._run(story_id))

    async def _run(self, story_id: int) -> None:
        try:
            for d in _recent(self.conn, story_id, None):
                try:
                    await digest.make(self.conn, self.chat, d["id"], story_id)
                except Exception:
                    log.exception("event=digest-failed discussion=%s stage=queue", d["id"])
        finally:
            if self.tasks.get(story_id) is asyncio.current_task():
                del self.tasks[story_id]

    async def wait(self, story_id: int, timeout: float) -> bool:
        t = self.tasks.get(story_id)
        if t is None or t.done():
            return False
        try:
            await asyncio.wait_for(asyncio.shield(t), timeout)
        except TimeoutError:
            return False
        return True

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
