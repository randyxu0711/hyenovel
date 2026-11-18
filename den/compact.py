import logging
from contextlib import aclosing

from den.companion import _read
from den.config import COMPACT_MAX_CHARS
from den.discuss import _ROLE, SUBMITTED, annotate
from marrow.prompt import Layer, Prompt
from marrow.workpacks import RunConfig

log = logging.getLogger("hyenovel")

COMPACT_RUN = RunConfig()


class CompactFailed(Exception):
    pass


def system() -> Prompt:
    text = _read("companion/compact.md").replace("{COMPACT_MAX_CHARS}", str(COMPACT_MAX_CHARS))
    return Prompt((Layer("compact", text),))


def transcript(rows: list[dict], versions: list[dict] = ()) -> str:
    rows = annotate(rows, list(versions))
    lines = []
    for i, r in enumerate(rows):
        if i and (r["role"] == "user" or rows[i - 1]["role"] == "assistant") \
                and rows[i - 1]["v"] and r["v"] and rows[i - 1]["v"] < r["v"]:
            lines.append(SUBMITTED.format(new=r["v"], old=rows[i - 1]["v"]))
        lines.append(f"{_ROLE[r['role']]}:{r['text']}")
    return "\n".join(lines)


async def summarize(chat, transcript: str) -> tuple[str, dict]:
    result = None
    async with aclosing(chat(system().text, transcript, config=COMPACT_RUN)) as stream:
        async for kind, val in stream:
            if kind == "result":
                result = val
    if result is None or result.outcome != "ok" or not (result.text or "").strip():
        raise CompactFailed(getattr(result, "outcome", "no-result"))
    text = result.text.strip()
    if len(text) > COMPACT_MAX_CHARS:
        log.warning("event=compact-truncated chars=%s max=%s", len(text), COMPACT_MAX_CHARS)
        text = text[:COMPACT_MAX_CHARS]
    return text, {**(result.tokens or {}), "duration_ms": result.duration_ms, "model": result.model}
