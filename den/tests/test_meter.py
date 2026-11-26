import asyncio
import dataclasses

import pytest

from den import companion, meter, runner
from den.meter import Meter
from den.runner import RunResult
from marrow import repo, workpacks
from marrow.workpacks import RunConfig

RUN = RunConfig()
TOK = {"input": 2, "output": 28, "cache_read": 649, "cache_creation": 1512, "thinking": 0, "cost_usd": 0.01}


def _ok(tokens=TOK, outcome="ok"):
    return RunResult(outcome, None, "", "m", tokens and dict(tokens), 5, None)


def _rows(conn):
    return repo.calls_since(conn, 0)


def go(coro):
    return asyncio.run(coro)


def test_row_exists_before_inner_returns(conn):
    seen = []

    async def inner(system, user, schema, *, config, sink):
        seen.extend(_rows(conn))
        return _ok()
    go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst", keys={"story_id": 1})))
    assert len(seen) == 1 and seen[0]["outcome"] is None and seen[0]["story_id"] == 1


def test_ok_records_tokens_and_call_id(conn):
    async def inner(system, user, schema, *, config, sink):
        return _ok()
    r = go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst", sizes={"task": 3})))
    row = _rows(conn)[0]
    assert r.call_id == row["id"] and row["outcome"] == "ok" and row["tokens_partial"] == 0
    assert row["tokens"] == {k: v for k, v in TOK.items() if k != "cost_usd"} and row["cost_usd"] == 0.01
    assert row["model"] == "m" and row["sizes"] == {"task": 3} and row["duration_ms"] is not None


def test_timeout_falls_back_to_sink(conn):
    async def inner(system, user, schema, *, config, sink):
        sink.tokens = {"input": 1}
        return _ok(None, "timeout")
    go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    row = _rows(conn)[0]
    assert row["outcome"] == "timeout" and row["tokens"] == {"input": 1} and row["tokens_partial"] == 1


def test_timeout_without_any_usage_is_unknown(conn):
    async def inner(system, user, schema, *, config, sink):
        return _ok(None, "timeout")
    go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    row = _rows(conn)[0]
    assert row["tokens"] is None and row["tokens_partial"] == 0


def test_cancelled_error_records_partial(conn):
    async def inner(system, user, schema, *, config, sink):
        sink.tokens = {"input": 2, "output": 4}
        sink.rate_limit = {"status": "allowed"}
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("reviewer")))
    row = _rows(conn)[0]
    assert row["outcome"] == "cancelled" and row["tokens_partial"] == 1 and row["rate_limit"] == {"status": "allowed"}


def test_other_exception_is_crash(conn):
    async def inner(system, user, schema, *, config, sink):
        raise OSError("boom")
    with pytest.raises(OSError):
        go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert _rows(conn)[0]["outcome"] == "crash"


def test_meter_is_required(conn):
    async def inner(system, user, schema, *, config, sink):
        return _ok()
    with pytest.raises(TypeError):
        go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN))

    async def drain():
        async for _ in meter.wrap_chat(_chat_ok, conn)("s", "u", config=RUN):
            pass
    with pytest.raises(TypeError):
        go(drain())
    assert _rows(conn) == []


async def _chat_ok(system, user, *, config, sink):
    sink.tokens = {"input": 2, "output": 4}
    yield "delta", "嗨"
    yield "delta", "你好"
    sink.tokens = {"input": 2, "output": 28}
    yield "result", _ok()


def test_chat_ok_finishes_before_result_reaches_caller(conn):
    seen = []

    async def drive():
        async for kind, val in meter.wrap_chat(_chat_ok, conn)("s", "u", config=RUN,
                                                               meter=Meter("chat", keys={"story_id": 1})):
            if kind == "result":
                seen.append((val.call_id, _rows(conn)[0]["outcome"]))
    go(drive())
    row = _rows(conn)[0]
    assert seen == [(row["id"], "ok")] and row["tokens_partial"] == 0


def test_chat_aclose_records_cancelled(conn):
    async def drive():
        gen = meter.wrap_chat(_chat_ok, conn)("s", "u", config=RUN, meter=Meter("chat"))
        assert (await gen.__anext__())[0] == "delta"
        await gen.aclose()
    go(drive())
    row = _rows(conn)[0]
    assert row["outcome"] == "cancelled" and row["tokens"] == {"input": 2, "output": 4} and row["tokens_partial"] == 1


def test_chat_exception_is_crash(conn):
    async def bad(system, user, *, config, sink):
        yield "delta", "x"
        raise OSError("boom")

    async def drive():
        async for _ in meter.wrap_chat(bad, conn)("s", "u", config=RUN, meter=Meter("chat")):
            pass
    with pytest.raises(OSError):
        go(drive())
    assert _rows(conn)[0]["outcome"] == "crash"


def test_chat_without_result_is_crash(conn):
    async def silent(system, user, *, config, sink):
        yield "delta", "x"

    async def drive():
        return [e async for e in meter.wrap_chat(silent, conn)("s", "u", config=RUN, meter=Meter("chat"))]
    go(drive())
    assert _rows(conn)[0]["outcome"] == "crash"


def test_chat_cancel_after_result_keeps_ok(conn):
    async def drive():
        gen = meter.wrap_chat(_chat_ok, conn)("s", "u", config=RUN, meter=Meter("chat"))
        async for kind, _ in gen:
            if kind == "result":
                break
        await gen.aclose()
    go(drive())
    assert _rows(conn)[0]["outcome"] == "ok"


def test_no_text_stored(conn):
    secret = "獨特的原文字串XYZ"

    async def inner(system, user, schema, *, config, sink):
        r = _ok()
        r.raw = r.text = r.message = secret
        return r
    go(meter.wrap_run(inner, conn)(secret, secret, {}, config=RUN, meter=Meter("analyst")))
    assert all(secret not in str(v) for v in _rows(conn)[0].values())


def test_tag_from_env(conn, monkeypatch):
    monkeypatch.setenv("HYENOVEL_TAG", "m6-on")

    async def inner(system, user, schema, *, config, sink):
        return _ok()
    go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert _rows(conn)[0]["tag"] == "m6-on"


def test_wrap_factory_passes_on_proc(conn):
    got = []

    def factory(on_proc):
        got.append(on_proc)

        async def inner(system, user, schema, *, config, sink):
            return _ok()
        return inner
    marker = object()
    r = go(meter.wrap_factory(factory, conn)(marker)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert got == [marker] and r.call_id == _rows(conn)[0]["id"]


def test_prompt_files_cover_repo_prompts():
    root = workpacks._PROMPTS
    listed = {f for files in meter.PROMPT_FILES.values() for f in files}
    on_disk = {str(p.relative_to(root)) for p in root.rglob("*.md")
               if p.parts[len(root.parts)] != "characters" and p.name != "README.md"}
    assert on_disk == listed
    assert set(meter.PROMPT_FILES) == {"analyst", "reviewer", "chat", "redo", "compact", "digest",
                                       "candidates", "candidate_revise"}


def test_prompt_fp_follows_companion_loader(monkeypatch):
    before = meter.prompt_fp("chat")
    real = companion._read
    monkeypatch.setattr(companion, "_read", lambda rel: "改過了" if rel == "companion/closing.md" else real(rel))
    assert meter.prompt_fp("chat") != before and meter.prompt_fp("redo") == meter.prompt_fp("chat")
    assert meter.prompt_fp("compact") == meter.prompt_fp("compact")


def test_prompt_fp_uses_what_the_worker_was_given(monkeypatch):
    before = meter.prompt_fp("analyst")
    monkeypatch.setattr(workpacks, "_prompt", lambda name: "別的")
    assert meter.prompt_fp("analyst") != before
    story = meter.prompt_fp("candidates")
    monkeypatch.setattr(meter.candidates, "STORY", "另一篇")
    assert meter.prompt_fp("candidates") != story


def test_prompt_fp_covers_schema_in_system_prompt(monkeypatch):
    before = {k: meter.prompt_fp(k) for k in meter.SYSTEMS}
    pack = workpacks.WORKPACKS["reviewer"]
    shown = workpacks.assemble("reviewer", {**pack.schema, "title": "換過"})
    monkeypatch.setitem(workpacks.WORKPACKS, "reviewer", dataclasses.replace(pack, prompt=shown))
    monkeypatch.setattr(meter.candidates, "_prompt", lambda: workpacks.assemble("candidates", {"type": "object"}))
    after = {k: meter.prompt_fp(k) for k in meter.SYSTEMS}
    assert [k for k in before if before[k] != after[k]] == ["reviewer", "candidates"]


class BrokenConn:
    def __enter__(self):
        raise RuntimeError("database is locked")

    def __exit__(self, *a):
        return False


def test_ledger_failure_never_reaches_caller():
    async def inner(system, user, schema, *, config, sink):
        return _ok()
    r = go(meter.wrap_run(inner, BrokenConn())("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert r.outcome == "ok" and r.call_id is None

    async def drive():
        return [e async for e in meter.wrap_chat(_chat_ok, BrokenConn())("s", "u", config=RUN, meter=Meter("chat"))]
    assert [k for k, _ in go(drive())] == ["delta", "delta", "result"]


def test_finish_failure_keeps_result(conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("locked")
    monkeypatch.setattr(repo, "finish_call", boom)

    async def inner(system, user, schema, *, config, sink):
        return _ok()
    r = go(meter.wrap_run(inner, conn)("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert r.outcome == "ok" and r.call_id == _rows(conn)[0]["id"]

    async def drive():
        return [e async for e in meter.wrap_chat(_chat_ok, conn)("s", "u", config=RUN, meter=Meter("chat"))]
    assert [k for k, _ in go(drive())] == ["delta", "delta", "result"]


def test_run_records_runner_and_effort(conn):
    async def inner(system, user, schema, *, sink, **kw):
        return _ok()
    run = meter.wrap_run(inner, conn, runner="claude-cli")
    go(run("s", "u", {}, config=RunConfig(effort="high"), meter=Meter("analyst")))
    go(run("s", "u", {}, meter=Meter("analyst")))
    a, b = _rows(conn)
    assert (a["runner"], a["effort"]) == ("claude-cli", "high")
    assert (b["runner"], b["effort"]) == ("claude-cli", None)


def test_chat_records_runner_and_effort(conn):
    async def inner(system, user, *, config, sink):
        yield "result", _ok()

    async def drive():
        return [e async for e in meter.wrap_chat(inner, conn, runner="claude-cli")(
            "s", "u", config=RunConfig(effort="low"), meter=Meter("chat"))]
    go(drive())
    row = _rows(conn)[0]
    assert (row["runner"], row["effort"]) == ("claude-cli", "low")


def test_factory_passes_runner(conn):
    async def inner(system, user, schema, *, config, sink):
        return _ok()
    run = meter.wrap_factory(lambda on_proc: inner, conn, runner="claude-cli")(None)
    go(run("s", "u", {}, config=RUN, meter=Meter("analyst")))
    assert _rows(conn)[0]["runner"] == "claude-cli"
