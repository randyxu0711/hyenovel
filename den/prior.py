import asyncio
import logging
import time

from den import suggest
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
        from den import digest
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


def _date(at: float | None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(at)) if at is not None else ""


def _fresh(conn, story_id: int, discussion_id: int | None) -> dict:
    latest = repo.latest_source_version(conn, story_id)
    got = gather(conn, story_id, discussion_id, latest["text"] if latest else "")
    return {"digests": [d["id"] for d in got["digests"]], "threads": [t["id"] for t in got["threads"] if not t["stale"]]}


async def snapshot(conn, queue, story_id: int | None, discussion_id: int | None, every: list[dict],
                   use: bool, wait_s: float) -> dict | None:
    if story_id is None:
        return None
    last = next((u for u in reversed(every) if u["role"] == "assistant"), None)
    if last is not None:
        snap = (last["recipe"] or {}).get("prior")
        return _fresh(conn, story_id, discussion_id) if snap is not None and not snap["digests"] else snap
    bring = use and enabled(conn)
    if not bring and not suggest.enabled(conn):
        return None
    if queue is not None:
        if not queue.running(story_id):
            queue.ensure(story_id)
        elif bring:
            await queue.wait(story_id, wait_s)
    return _fresh(conn, story_id, discussion_id) if bring else None


def resolve(conn, snap: dict | None, latest_source: str, discussion_id: int | None = None) -> dict | None:
    if not snap:
        return None
    talked = repo.talked_in(conn, discussion_id) if discussion_id is not None else set()
    digests = [{"id": g["id"], "at": g["at"], "text": g["text"]}
               for g in (repo.digest_by_id(conn, i) for i in snap["digests"]) if g is not None]
    threads = [{"id": t["id"], "text": t["text"], "quote": t["quote"], "source_quote": t["source_quote"],
                "at": t["at"], "session": t["session"], "ended": t["ended_at"] is not None, "talked": t["id"] in talked}
               for t in (repo.thread_by_id(conn, i) for i in snap["threads"])
               if t is not None and not is_stale(t, latest_source)]
    return {"digests": digests, "threads": threads}


def layer_text(shown: dict) -> str:
    out = "".join(f"### {_date(d['at'])}\n{d['text'].rstrip()}\n\n" for d in shown["digests"])
    live = [t for t in shown["threads"] if not t["ended"]]
    if live:
        out += "待續話題:\n" + "".join(f"- {t['text']}「{t['quote']}」\n" for t in live)
    return out + "\n"


def mark_talked(conn, shown: dict | None, discussion_id: int, said: str) -> None:
    for t in (shown or {}).get("threads", ()):
        if t["ended"]:
            continue
        if gate.locate(t["quote"], said) is not None or (
                t["source_quote"] and gate.locate(t["source_quote"], said) is not None):
            repo.mark_talked(conn, t["id"], discussion_id)


def end_thread(conn, thread_id: int, ended_at: float | None) -> None:
    repo.set_thread_ended(conn, thread_id, ended_at)
    t = repo.thread_by_id(conn, thread_id)
    if t["replaced_at"] is None:
        return
    for live in repo.threads_of(conn, t["root_id"]):
        if gate.locate(live["quote"], t["quote"]) is not None or gate.locate(t["quote"], live["quote"]) is not None:
            repo.set_thread_ended(conn, live["id"], ended_at)
