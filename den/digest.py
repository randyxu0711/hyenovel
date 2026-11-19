import logging
import time
from contextlib import aclosing

from den import compact
from den.companion import _read
from den.config import DIGEST_MAX_CHARS, MIN_QUOTE_CHARS, THREADS_PER_DIGEST
from den.discuss import _TURNS
from marrow import gate, jsonout, prompt, repo
from marrow.prompt import Layer, Prompt
from marrow.workpacks import RunConfig

log = logging.getLogger("hyenovel")

DIGEST_RUN = RunConfig()
RETRYABLE = ("usage-limit", "transient", "cancelled")
PREVIOUS = "上一版摘要:\n<previous>\n{text}\n</previous>\n\n"


def system() -> Prompt:
    text = (_read("companion/digest.md").replace("{DIGEST_MAX_CHARS}", str(DIGEST_MAX_CHARS))
            .replace("{THREADS_PER_DIGEST}", str(THREADS_PER_DIGEST)))
    return Prompt((Layer("digest", text),))


def parse(raw: str, said: str, sources: list[str]) -> tuple[str, list[dict]] | None:
    obj = jsonout.extract_json(raw or "")
    if obj is None or not isinstance(obj.get("summary"), str) or not obj["summary"].strip():
        return None
    summary = obj["summary"].strip()
    if len(summary) > DIGEST_MAX_CHARS:
        log.warning("event=digest-truncated chars=%s max=%s", len(summary), DIGEST_MAX_CHARS)
        summary = summary[:DIGEST_MAX_CHARS]
    threads = []
    raw_threads = obj.get("threads")
    for t in raw_threads if isinstance(raw_threads, list) else ():
        if not isinstance(t, dict) or not isinstance(t.get("text"), str) or not t["text"].strip():
            log.info("event=digest-thread-dropped reason=shape")
            continue
        quote = t.get("quote")
        if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE_CHARS:
            log.info("event=digest-thread-dropped reason=quote-short")
            continue
        if gate.locate(quote, said) is None:
            log.info("event=digest-thread-dropped reason=quote-not-said")
            continue
        src = t.get("source_quote")
        if src is not None and not (isinstance(src, str) and src.strip()
                                    and any(gate.locate(src, s) is not None for s in sources)):
            log.info("event=digest-source-dropped")
            src = None
        threads.append({"text": t["text"].strip(), "quote": quote, "source_quote": src, "ended_at": None})
        if len(threads) == THREADS_PER_DIGEST:
            break
    return summary, threads


def _carry_ended(old: list[dict], new: list[dict]) -> None:
    for t in new:
        hit = next((o for o in old if o["ended_at"] is not None and (
            gate.locate(t["quote"], o["quote"]) is not None or gate.locate(o["quote"], t["quote"]) is not None)), None)
        if hit:
            t["ended_at"] = hit["ended_at"]


async def make(conn, chat, discussion_id: int, story_id: int | None, now=time.time) -> int | None:
    turns = [u for u in repo.utterances(conn, discussion_id) if u["role"] in _TURNS]
    if not turns:
        return None
    last_seq = turns[-1]["seq"]
    cur = repo.current_digest(conn, discussion_id)
    if cur is not None and cur["through_seq"] >= last_seq:
        return cur["id"]
    if repo.digest_failed_seq(conn, discussion_id) == last_seq:
        return None
    versions = repo.source_versions(conn, story_id) if story_id is not None else []
    fresh = [u for u in turns if cur is None or u["seq"] > cur["through_seq"]]
    user = (PREVIOUS.format(text=cur["text"]) if cur else "") + compact.transcript(fresh, versions)
    said = "\n".join(u["text"] for u in turns)
    sources = [v["text"] for v in versions]
    old_threads = repo.threads_of(conn, cur["root_id"]) if cur else []
    result = None
    try:
        async with aclosing(chat(system().text, user, config=DIGEST_RUN)) as stream:
            async for kind, val in stream:
                if kind == "result":
                    result = val
    except Exception:
        log.exception("event=digest-failed discussion=%s stage=chat", discussion_id)
    parsed = parse(result.text, said, sources) if result is not None and result.outcome == "ok" else None
    if parsed is None:
        log.warning("event=digest-failed discussion=%s outcome=%s", discussion_id,
                    getattr(result, "outcome", "no-result"))
        if result is not None and result.outcome not in RETRYABLE:
            with conn:
                repo.record_digest_failure(conn, discussion_id, last_seq, now())
        return None
    summary, threads = parsed
    _carry_ended(old_threads, threads)
    usage = {**(result.tokens or {}), "duration_ms": result.duration_ms, "model": result.model}
    at = now()
    with conn:
        did = repo.add_digest(conn, discussion_id, summary, last_seq, at, root_id=cur["root_id"] if cur else None,
                              usage=usage, recipe=prompt.recipe(system(), DIGEST_RUN.as_dict()))
        repo.replace_threads(conn, repo.digest_by_id(conn, did)["root_id"], threads, at)
    log.info("event=digest-made discussion=%s threads=%s", discussion_id, len(threads))
    return did
