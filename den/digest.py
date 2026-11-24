import json
import logging
import time
from contextlib import aclosing

from den import compact, discuss, meter, suggest
from den.companion import _read
from den.config import CANDIDATES_PER_DIGEST, DIGEST_MAX_CHARS, MIN_QUOTE_CHARS, THREADS_PER_DIGEST
from den.discuss import since_clear
from marrow import gate, jsonout, prompt, repo
from marrow.prompt import Layer, Prompt
from marrow.workpacks import RunConfig

log = logging.getLogger("hyenovel")

DIGEST_RUN = RunConfig()
RETRYABLE = ("usage-limit", "transient", "cancelled", "timeout", "auth")
PREVIOUS = "上一版摘要:\n<previous>\n{text}\n</previous>\n\n"
KNOWN = "已經記住或提過的事:\n<known>\n{items}\n</known>\n\n"
PREVIOUS_THREADS = "上一版待續話題:\n<threads>\n{items}\n</threads>\n\n"


def system(memories: bool = True) -> Prompt:
    text = (_read("companion/digest.md").replace("{DIGEST_MAX_CHARS}", str(DIGEST_MAX_CHARS))
            .replace("{THREADS_PER_DIGEST}", str(THREADS_PER_DIGEST)))
    layers = [Layer("digest", text)]
    if memories:
        layers.append(Layer("memories", _read("companion/digest_memories.md")
                            .replace("{CANDIDATES_PER_DIGEST}", str(CANDIDATES_PER_DIGEST))))
    return Prompt(tuple(layers))


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


def _known(conn, story_id: int | None, on: bool) -> str:
    items = suggest.known(conn, story_id) if on else []
    return KNOWN.format(items="\n".join(f"- {t}" for t in items)) if items else ""


def _previous(base: dict | None, open_threads: list[dict]) -> str:
    if base is None:
        return ""
    out = PREVIOUS.format(text=base["text"])
    if open_threads:
        items = "\n".join(json.dumps({k: t[k] for k in ("text", "quote", "source_quote")}, ensure_ascii=False)
                          for t in open_threads)
        out += PREVIOUS_THREADS.format(items=items)
    return out


async def make(conn, chat, discussion_id: int, story_id: int | None, now=time.time) -> int | None:
    every = repo.utterances(conn, discussion_id)
    cur = repo.current_digest(conn, discussion_id)
    turns = since_clear(every)
    if not turns:
        return cur["id"] if cur else None
    last_seq = turns[-1]["seq"]
    if cur is not None and cur["through_seq"] >= last_seq:
        return cur["id"]
    if repo.digest_failed_seq(conn, discussion_id) == last_seq:
        return None
    cleared = max((u["seq"] for u in every if u["role"] == "clear"), default=-1)
    base = cur if cur is not None and cur["through_seq"] > cleared else None
    open_threads = [t for t in repo.threads_of(conn, base["root_id"]) if t["ended_at"] is None] if base else []
    versions = repo.source_versions(conn, story_id) if story_id is not None else []
    fresh = [u for u in turns if base is None or u["seq"] > base["through_seq"]]
    suggesting = story_id is not None and suggest.enabled(conn)
    sys_prompt = system(suggesting)
    user = _known(conn, story_id, suggesting) + _previous(base, open_threads) + compact.transcript(fresh, versions)
    said = "\n".join(u["text"] for u in turns)
    sources = [v["text"] for v in versions]
    result = None
    try:
        usage_meter = meter.Meter("digest", sizes=prompt.sizes(sys_prompt),
                                  keys={k: v for k, v in (("story_id", story_id), ("discussion_id", discussion_id))
                                        if v is not None})
        async with aclosing(chat(sys_prompt.text, user, config=DIGEST_RUN, meter=usage_meter)) as stream:
            async for kind, val in stream:
                if kind == "result":
                    result = val
    except Exception:
        log.exception("event=digest-failed discussion=%s stage=chat", discussion_id)
    after = repo.current_digest(conn, discussion_id)
    if (after and after["id"]) != (cur and cur["id"]) or not repo.utterances(conn, discussion_id):
        log.info("event=digest-dropped discussion=%s reason=changed-while-running", discussion_id)
        discuss.discard(conn, getattr(result, "call_id", None))
        return None
    parsed = parse(result.text, said, sources) if result is not None and result.outcome == "ok" else None
    if parsed is None:
        if result is not None and result.outcome == "ok" and result.call_id is not None:
            with conn:
                repo.mark_call(conn, result.call_id, "gate_rejected")
        log.warning("event=digest-failed discussion=%s outcome=%s", discussion_id,
                    getattr(result, "outcome", "no-result"))
        if result is not None and result.outcome not in RETRYABLE:
            with conn:
                repo.record_digest_failure(conn, discussion_id, last_seq, now())
        return None
    summary, threads = parsed
    _carry_ended(repo.threads_of(conn, cur["root_id"]) if cur else [], threads)
    usage = {**(result.tokens or {}), "duration_ms": result.duration_ms, "model": result.model}
    at = now()
    with conn:
        did = repo.add_digest(conn, discussion_id, summary, last_seq, at, root_id=cur["root_id"] if cur else None,
                              usage=usage, recipe=prompt.recipe(sys_prompt, DIGEST_RUN.as_dict()))
        repo.replace_threads(conn, repo.digest_by_id(conn, did)["root_id"], threads, at)
        if result.call_id is not None:
            repo.link_call(conn, result.call_id, digest_id=did)
        kept = (suggest.store(conn, discussion_id, story_id, suggest.parse(result.text, turns), at)
                if suggesting and suggest.enabled(conn) else 0)
    log.info("event=digest-made discussion=%s threads=%s memories=%s", discussion_id, len(threads), kept)
    return did
