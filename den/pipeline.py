"""critique 流水線:步驟 + 閘門引擎(重試政策移植自 server/orchestrator.py)。

- 引擎只裁決(回 StepOutcome),不寫 job 狀態——那是 worker 的事。
- 每筆 attempt 都記(#17:被擋的是純損耗,要看得見);artifact 與它的 ok attempt 同一個 transaction。
- current 只在**全部步驟成功**時一次換;中途任何停止都不動。
- 續跑:該步已有 ok attempt 就載入其 artifact 跳過,不重花錢;attempt n 接著既有的編。
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from den import config
from den.runner import RunResult
from marrow import repo, workpacks
from marrow.schema import SCHEMA_VERSION

log = logging.getLogger("hyenovel")

# 宣告式步驟清單;criticizer 的 analysis 輸入 = 本 job analyst 步的產物
CRITIQUE: tuple[str, ...] = ("analyst", "criticizer")

# (system_prompt, user_prompt, schema) -> RunResult;由 worker 注入(綁好 preset、timeout、on_proc)
RunFn = Callable[[str, str, dict], Awaitable[RunResult]]

_USAGE_MSG = "撞到訂閱用量上限，稍後再續（與你在 Claude Code 的對話共用同一份額度）"
_GATE_MSG = "閘門重試後仍未過"


@dataclass
class StepOutcome:
    state: str
    error_class: str | None
    detail: dict | None


def _phase(name: str, status: str, attempt: int, detail: str | None = None) -> dict:
    data = {"name": name, "status": status, "attempt": attempt}
    if detail is not None:
        data["detail"] = detail
    return {"event": "phase", "data": data}


async def _run_step(conn, job: dict, step: str, slug: str, source: str, analysis: dict | None,
                    run: RunFn, emit, *, runner_name: str, cli_version: str | None,
                    now, sleep) -> dict | StepOutcome:
    """一步的 attempt 迴圈。成功回 artifact,停止回 StepOutcome。"""
    pack = workpacks.WORKPACKS[step]
    jid = job["id"]
    n = sum(1 for a in repo.attempts(conn, jid) if a["step"] == step)
    prompt = workpacks.first_input(step, slug, source, analysis)
    gate_retries = transient = 0

    def record(outcome: str, r: RunResult | None, gate_verdict=None, artifact_id=None):
        repo.add_attempt(
            conn, jid, step, n, runner=runner_name, model=r and r.model, cli_version=cli_version,
            outcome=outcome, raw_output=r and r.raw, parsed=r and r.parsed,
            gate_verdict=gate_verdict, tokens=r and r.tokens, duration_ms=r and r.duration_ms,
            artifact_id=artifact_id, now=now())

    def stop(outcome: StepOutcome) -> StepOutcome:
        emit(_phase(step, "fail", n))
        return outcome

    while True:
        emit(_phase(step, "start", n))
        try:
            r = await run(pack.system_prompt, prompt, pack.schema)
        except asyncio.CancelledError:
            with conn:
                record("cancelled", None)
            log.info("event=step-cancelled job=%s step=%s n=%s", jid, step, n)
            raise
        log.info("event=attempt job=%s step=%s n=%s outcome=%s", jid, step, n, r.outcome)

        if r.outcome == "ok":
            errs = workpacks.gate(step, r.parsed, source, analysis)
            if not errs:
                prov = {"tier": "A", "runner": runner_name, "model": r.model,
                        "cli_version": cli_version, "job": jid, "attempt": n}
                with conn:
                    aid, _ = repo.add_artifact(conn, job["story_id"], job["source_version_id"],
                                               pack.kind, SCHEMA_VERSION, r.parsed, prov, now())
                    record("ok", r, artifact_id=aid)
                emit(_phase(step, "ok", n))
                return repo.artifact(conn, aid)
            with conn:
                record("gate", r, gate_verdict={"errors": errs})
            # 不把錯誤明細入 log:可能夾帶引文
            log.info("event=gate-retry job=%s step=%s n=%s errors=%s", jid, step, n, len(errs))
            emit(_phase(step, "retry", n, "\n".join(errs)[:800]))
            gate_retries += 1
            if gate_retries > config.MAX_GATE_RETRIES:
                return stop(StepOutcome("paused", "gate", {"message": _GATE_MSG}))
            prompt = workpacks.repair_input(step, slug, source, analysis, r.parsed, errs)
        else:
            with conn:
                record(r.outcome, r)
            if r.outcome == "transient" and transient < config.TRANSIENT_MAX_RETRIES:
                transient += 1                            # 不吃閘門額度、不換 prompt
                emit(_phase(step, "retry", n, r.message))
                await sleep(config.BACKOFF_BASE * 2 ** transient)
            elif r.outcome in ("transient", "usage-limit"):   # transient 耗盡視同 usage-limit
                return stop(StepOutcome("paused", "usage-limit",
                                        {"message": _USAGE_MSG, "resets_at": None}))
            else:                                         # auth / crash / timeout
                return stop(StepOutcome("failed", r.outcome, {"message": r.message}))
        n += 1


async def run_critique(conn, job: dict, run: RunFn, emit: Callable[[dict], None], *,
                       runner_name: str, cli_version: str | None,
                       now: Callable[[], float] = time.time, sleep=asyncio.sleep) -> StepOutcome:
    jid = job["id"]
    source = repo.source_version(conn, job["source_version_id"])["text"]
    slug = repo.story(conn, job["story_id"])["slug"]
    done: dict[str, dict] = {}
    for step in CRITIQUE:
        analysis = done["analyst"]["body"] if "analyst" in done else None
        prior = repo.ok_attempt(conn, jid, step)
        if prior is not None:
            log.info("event=step-skip job=%s step=%s", jid, step)
            emit(_phase(step, "ok", prior["n"], "resume-skip"))
            done[step] = repo.artifact(conn, prior["artifact_id"])
            continue
        res = await _run_step(conn, job, step, slug, source, analysis, run, emit,
                              runner_name=runner_name, cli_version=cli_version,
                              now=now, sleep=sleep)
        if isinstance(res, StepOutcome):
            log.info("event=job-stop job=%s step=%s state=%s class=%s",
                     jid, step, res.state, res.error_class)
            emit({"event": "error", "data": {
                "where": step, **res.detail, "recoverable": True,
                "reason": res.error_class}})
            return res
        done[step] = res
    with conn:
        for step, art in done.items():
            repo.set_current(conn, job["story_id"], workpacks.WORKPACKS[step].kind, art["id"])
    log.info("event=job-done job=%s", jid)
    emit({"event": "done", "data": {"ok": True}})
    return StepOutcome("done", None, None)
