import logging

from den.config import CANDIDATES_PER_DIGEST, KNOWN_MAX, MEMORY_QUOTE_MIN_CHARS
from marrow import gate, jsonout, repo

log = logging.getLogger("hyenovel")

SETTING = "suggest.enabled"
SCOPES = ("author", "work")


def enabled(conn) -> bool:
    return repo.get_setting(conn, SETTING) != "0"


def set_enabled(conn, on: bool) -> None:
    repo.set_setting(conn, SETTING, "1" if on else "0")


def _said_by_author(quote: str, turns: list[dict]) -> int | None:
    return next((u["seq"] for u in turns if u["role"] == "user" and gate.locate(quote, u["text"]) is not None), None)


def parse(raw: str, turns: list[dict]) -> list[dict]:
    obj = jsonout.extract_json(raw or "")
    items = obj.get("memories") if isinstance(obj, dict) else None
    out = []
    for m in items if isinstance(items, list) else ():
        if not isinstance(m, dict) or not isinstance(m.get("text"), str) or not m["text"].strip():
            log.info("event=candidate-dropped reason=shape")
            continue
        quote, scope = m.get("quote"), m.get("scope")
        if scope not in SCOPES:
            log.info("event=candidate-dropped reason=scope")
            continue
        if not isinstance(quote, str) or len(quote.strip()) < MEMORY_QUOTE_MIN_CHARS:
            log.info("event=candidate-dropped reason=quote-short")
            continue
        seq = _said_by_author(quote, turns)
        if seq is None:
            log.info("event=candidate-dropped reason=quote-not-author")
            continue
        out.append({"text": m["text"].strip(), "quote": quote, "seq": seq, "scope": scope})
        if len(out) == CANDIDATES_PER_DIGEST:
            break
    return out


def _overlaps(a: str, b: str) -> bool:
    return gate.locate(a, b) is not None or gate.locate(b, a) is not None


def _live_memories(conn, story_id: int) -> list[dict]:
    return repo.active_memories(conn, "author") + repo.active_memories(conn, "work", story_id)


def store(conn, discussion_id: int, story_id: int, items: list[dict], now: float) -> int:
    live = _live_memories(conn, story_id)
    quotes = [c["quote"] for c in repo.candidates_of_story(conn, story_id)] + [m["quote"] for m in live if m["quote"]]
    texts = {m["text"] for m in live}
    n = 0
    for m in items:
        if m["text"] in texts or any(_overlaps(m["quote"], q) for q in quotes):
            log.info("event=candidate-dropped reason=duplicate")
            continue
        repo.add_candidate(conn, discussion_id, m["seq"], m["quote"], m["text"], m["scope"], now)
        quotes.append(m["quote"])
        n += 1
    return n


def known(conn, story_id: int) -> list[str]:
    return ([m["text"] for m in _live_memories(conn, story_id)]
            + [c["text"] for c in repo.candidates_of_story(conn, story_id)])[:KNOWN_MAX]
