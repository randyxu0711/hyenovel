"""用量帳本的計量包裝:呼叫前寫一列、結束補結局。只存數字、id、列舉值,不存文字。"""
import asyncio
import logging
import os
import time
from contextlib import aclosing
from dataclasses import dataclass, field

from den import candidates, companion
from den.runner import RunResult, UsageSink
from marrow import repo, workpacks

log = logging.getLogger("hyenovel")

PROMPT_FILES: dict[str, tuple[str, ...]] = {
    "analyst": ("analyst.md",),
    "reviewer": ("reviewer.md",),
    "chat": ("companion/base.md", "companion/reading.md", "companion/closing.md", "companion/examples.md",
             "companion/prior.md", "companion/compare.md", "companion/samples.md"),
    "compact": ("companion/compact.md",),
    "digest": ("companion/digest.md", "companion/digest_memories.md"),
    "candidates": ("candidates.md", "example_story.md"),
    "candidate_revise": ("candidate_revise.md", "example_story.md"),
}
PROMPT_FILES["redo"] = PROMPT_FILES["chat"]


@dataclass(frozen=True)
class Meter:
    kind: str
    sizes: dict | None = None
    keys: dict = field(default_factory=dict)


def _text(rel: str) -> str:
    if rel == "example_story.md":
        return candidates.STORY
    if "/" not in rel:
        return workpacks._prompt(rel.removesuffix(".md"))
    return companion._read(rel)


def prompt_fp(kind: str) -> str:
    return repo.sha256_text("\0".join(_text(rel) for rel in PROMPT_FILES[kind]))[:12]


def _start(conn, meter: Meter, clock, runner: str | None, config) -> tuple[int | None, float]:
    t0 = clock()
    try:
        with conn:
            cid = repo.start_call(conn, meter.kind, t0, prompt_fp(meter.kind),
                                  tag=os.environ.get("HYENOVEL_TAG") or None, sizes=meter.sizes, runner=runner,
                                  effort=getattr(config, "effort", None), **meter.keys)
    except Exception:
        log.exception("event=ledger-start-failed kind=%s", meter.kind)
        return None, t0
    return cid, t0


def _finish(conn, cid: int | None, t0: float, clock, sink: UsageSink, r: RunResult | None = None,
            outcome: str | None = None) -> None:
    if cid is None:
        return
    try:
        _write_finish(conn, cid, t0, clock, sink, r, outcome)
    except Exception:
        log.exception("event=ledger-finish-failed call=%s", cid)


def _write_finish(conn, cid: int, t0: float, clock, sink: UsageSink, r: RunResult | None,
                  outcome: str | None) -> None:
    tokens = cost = model = None
    if r is not None:
        outcome, model = r.outcome, r.model
        if r.tokens is not None:
            cost = r.tokens.get("cost_usd")
            tokens = {k: v for k, v in r.tokens.items() if k != "cost_usd"}
    partial = tokens is None and sink.tokens is not None
    end = clock()
    with conn:
        repo.finish_call(conn, cid, outcome=outcome, ended_at=end, duration_ms=int((end - t0) * 1000),
                         tokens=sink.tokens if partial else tokens, tokens_partial=partial, cost_usd=cost,
                         model=model, rate_limit=sink.rate_limit)


def wrap_run(run, conn, clock=time.time, runner: str | None = None):
    async def metered(system, user, schema, *, meter: Meter, **kw) -> RunResult:
        cid, t0 = _start(conn, meter, clock, runner, kw.get("config"))
        sink = UsageSink()
        try:
            r = await run(system, user, schema, sink=sink, **kw)
        except (asyncio.CancelledError, GeneratorExit):
            _finish(conn, cid, t0, clock, sink, outcome="cancelled")
            raise
        except Exception:
            _finish(conn, cid, t0, clock, sink, outcome="crash")
            raise
        _finish(conn, cid, t0, clock, sink, r)
        r.call_id = cid
        return r
    metered.inner = run
    return metered


def wrap_chat(chat, conn, clock=time.time, runner: str | None = None):
    async def metered(system, user, *, meter: Meter, **kw):
        cid, t0 = _start(conn, meter, clock, runner, kw.get("config"))
        sink = UsageSink()
        done = False
        try:
            async with aclosing(chat(system, user, sink=sink, **kw)) as stream:
                async for kind, val in stream:
                    if kind == "result" and not done:
                        _finish(conn, cid, t0, clock, sink, val)
                        done = True
                        val.call_id = cid
                    yield kind, val
        except (asyncio.CancelledError, GeneratorExit):
            if not done:
                _finish(conn, cid, t0, clock, sink, outcome="cancelled")
            raise
        except Exception:
            if not done:
                _finish(conn, cid, t0, clock, sink, outcome="crash")
            raise
        if not done:
            _finish(conn, cid, t0, clock, sink, outcome="crash")
    metered.inner = chat
    return metered


def wrap_factory(factory, conn, runner: str | None = None):
    return lambda on_proc: wrap_run(factory(on_proc), conn, runner=runner)
