"""den.pipeline 行為契約:修補包重試、錯誤分流、續跑、成功才換 current。

假 RunFn 按呼叫順序吐預先排好的 RunResult(或拋例外);絕不 spawn 真 claude。
"""
import asyncio
import json
import logging

import pytest

from den import pipeline
from den.runner import RunResult
from den.tests.conftest import FIXTURES
from marrow import repo, schema
from marrow.repo import canonical_json
from marrow.workpacks import WORKPACKS

MINI = FIXTURES / "mini"


def _analysis(synopsis="第一版"):
    body = schema.to_v1("analysis", json.loads((MINI / "analysis.json").read_text(encoding="utf-8")))
    body["synopsis"] = synopsis
    return body


def _bad_analysis():
    body = _analysis("壞的")
    body["nodes"][0]["evidence"][0]["quote"] = "原文裡沒有這句"
    return body


def _feedback(read="第一版回饋"):
    return schema.to_v1("feedback", {
        "slug": "mini",
        "read": read,
        "strengths": [{"title": "燈的用法", "body": "把等待外包給物件。",
                       "refs": ["k1"], "quotes": ["像在等誰"]}],
        "key_points": [{"title": "收尾太快", "body": "關燈之後沒有餘波。",
                        "refs": ["e1"], "quotes": ["他把燈關了。"],
                        "question": "他站在黑暗裡多久?"}],
        "minor": [],
        "one_line": "節制,但收得太急。",
    })


def ok(body):
    return RunResult("ok", body, json.dumps(body, ensure_ascii=False), "claude-sonnet",
                     {"output": 10}, 5, None)


def fail(outcome, message="出事了"):
    return RunResult(outcome, None, "{}", None, None, 5, message)


class FakeRun:
    """按順序吐 script 裡的東西;BaseException 就拋。記下每次呼叫。"""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    async def __call__(self, system_prompt, user_prompt, schema_):
        self.calls.append((system_prompt, user_prompt, schema_))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _job(conn):
    st = repo.story_by_slug(conn, "mini")
    sv = repo.latest_source_version(conn, st["id"])
    with conn:
        jid = repo.create_job(conn, "critique", st["id"], sv["id"], {}, 1.0)
    return repo.get_job(conn, jid)


def _drive(conn, job, run):
    events, sleeps = [], []

    async def sleep(s):
        sleeps.append(s)

    out = asyncio.run(pipeline.run_critique(conn, job, run, events.append,
                                            runner_name="claude-cli", cli_version="9.9.9",
                                            now=lambda: 2.0, sleep=sleep))
    return out, events, sleeps


def _current(conn, job, kind):
    return repo.current_artifact(conn, job["story_id"], kind)


def _outcomes(conn, job, step=None):
    return [a["outcome"] for a in repo.attempts(conn, job["id"])
            if step is None or a["step"] == step]


def test_happy_path_commits_and_swaps_current(conn):
    job = _job(conn)
    out, events, _ = _drive(conn, job, FakeRun(ok(_analysis()), ok(_feedback())))
    assert out == pipeline.StepOutcome("done", None, None)
    a, f = _current(conn, job, "analysis"), _current(conn, job, "feedback")
    assert a["body"] == _analysis() and f["body"] == _feedback()
    for art, n in ((a, 0), (f, 0)):
        assert art["provenance"] == {"tier": "A", "runner": "claude-cli", "model": "claude-sonnet",
                                     "cli_version": "9.9.9", "job": job["id"], "attempt": n}
    atts = repo.attempts(conn, job["id"])
    assert [(x["step"], x["n"], x["outcome"]) for x in atts] == [
        ("analyst", 0, "ok"), ("criticizer", 0, "ok")]
    assert atts[0]["artifact_id"] == a["id"] and atts[1]["artifact_id"] == f["id"]
    assert events[-1] == {"event": "done", "data": {"ok": True}}
    assert {"event": "phase", "data": {"name": "analyst", "status": "ok", "attempt": 0}} in events


def test_gate_retry_uses_repair_input(conn):
    job = _job(conn)
    run = FakeRun(ok(_bad_analysis()), ok(_analysis()), ok(_feedback()))
    out, events, _ = _drive(conn, job, run)
    assert out.state == "done"
    second = run.calls[1][1]
    assert "<previous_output>" in second and "原文裡沒有這句" in second
    assert _outcomes(conn, job, "analyst") == ["gate", "ok"]
    gate_att = repo.attempts(conn, job["id"])[0]
    assert any("原文裡沒有這句" in e for e in gate_att["gate_verdict"]["errors"])
    retry = [e for e in events if e["data"].get("status") == "retry"]
    assert len(retry) == 1 and "原文裡沒有這句" in retry[0]["data"]["detail"]


def test_gate_exhausted_pauses(conn):
    job = _job(conn)
    before = _current(conn, job, "analysis")["id"]
    out, events, _ = _drive(conn, job, FakeRun(*[ok(_bad_analysis())] * 3))
    assert (out.state, out.error_class) == ("paused", "gate")
    assert out.detail["message"]
    assert _outcomes(conn, job) == ["gate"] * 3
    assert _current(conn, job, "analysis")["id"] == before
    assert events[-1]["event"] == "error" and events[-1]["data"]["reason"] == "gate"


def test_transient_backoff_not_counted(conn):
    job = _job(conn)
    bad = ok(_bad_analysis())
    run = FakeRun(fail("transient"), fail("transient"), bad, bad, ok(_analysis()), ok(_feedback()))
    out, _, sleeps = _drive(conn, job, run)
    assert out.state == "done"
    assert sleeps == [4.0, 8.0]
    assert _outcomes(conn, job, "analyst") == ["transient", "transient", "gate", "gate", "ok"]
    assert [a["n"] for a in repo.attempts(conn, job["id"]) if a["step"] == "analyst"] == [0, 1, 2, 3, 4]


def test_transient_exhausted_is_overload_not_quota(conn):
    job = _job(conn)
    out, _, sleeps = _drive(conn, job, FakeRun(*[fail("transient")] * 3))
    assert (out.state, out.error_class) == ("paused", "overload")
    assert "額度" not in out.detail["message"] and "resets_at" not in out.detail
    assert sleeps == [4.0, 8.0]
    assert _outcomes(conn, job) == ["transient"] * 3


@pytest.mark.parametrize("outcome,state,cls", [
    ("usage-limit", "paused", "usage-limit"),
    ("auth", "failed", "auth"),
    ("crash", "failed", "crash"),
    ("timeout", "failed", "timeout"),
])
def test_error_routing_usage_limit_auth_crash(conn, outcome, state, cls):
    job = _job(conn)
    out, events, _ = _drive(conn, job, FakeRun(fail(outcome)))
    assert (out.state, out.error_class) == (state, cls)
    assert out.detail["message"]
    if cls == "usage-limit":
        assert "同一份額度" in out.detail["message"]
        assert out.detail["resets_at"] is None
    assert _outcomes(conn, job) == [outcome]
    err = events[-1]
    assert err["event"] == "error"
    assert err["data"]["where"] == "analyst" and err["data"]["reason"] == cls
    assert err["data"]["recoverable"] is True   # 引擎回的每種停止都可續(paused|failed)


def _paused_second_job(conn):
    """先一次 happy path(current=A1,F1),再開新 job:analyst ok、criticizer 撞 usage-limit。"""
    j1 = _job(conn)
    _drive(conn, j1, FakeRun(ok(_analysis()), ok(_feedback())))
    a1, f1 = _current(conn, j1, "analysis")["id"], _current(conn, j1, "feedback")["id"]
    j2 = _job(conn)
    out, _, _ = _drive(conn, j2, FakeRun(ok(_analysis("第二版")), fail("usage-limit")))
    assert out.state == "paused"
    return j2, a1, f1


def test_current_swaps_only_on_success(conn):
    j2, a1, f1 = _paused_second_job(conn)
    assert _current(conn, j2, "analysis")["id"] == a1
    assert _current(conn, j2, "feedback")["id"] == f1


def test_resume_skips_committed_steps(conn):
    j2, a1, _ = _paused_second_job(conn)
    with conn:
        repo.set_job_state(conn, j2["id"], "paused", 3.0)   # worker 的工作,這裡代勞
        assert repo.requeue_job(conn, j2["id"], 3.0)
    run = FakeRun(ok(_feedback("第二版回饋")))
    out, events, _ = _drive(conn, repo.get_job(conn, j2["id"]), run)
    assert out.state == "done"
    assert len(run.calls) == 1 and run.calls[0][0] == WORKPACKS["criticizer"].system_prompt
    assert canonical_json(_analysis("第二版")) in run.calls[0][1]
    assert [a["n"] for a in repo.attempts(conn, j2["id"]) if a["step"] == "criticizer"] == [0, 1]
    assert _current(conn, j2, "analysis")["body"] == _analysis("第二版")
    assert _current(conn, j2, "analysis")["id"] != a1
    assert _current(conn, j2, "feedback")["body"] == _feedback("第二版回饋")
    assert {"event": "phase", "data": {"name": "analyst", "status": "ok", "attempt": 0,
                                       "detail": "resume-skip"}} in events


def test_criticizer_gets_this_jobs_analysis(conn):
    job = _job(conn)
    old = _current(conn, job, "analysis")["body"]
    mine = _analysis("本 job 的分析")
    run = FakeRun(ok(mine), ok(_feedback()))
    _drive(conn, job, run)
    prompt = run.calls[1][1]
    assert f"<analysis>\n{canonical_json(mine)}\n</analysis>" in prompt
    assert canonical_json(old) not in prompt


def test_cancel_records_attempt_and_reraises(conn):
    job = _job(conn)
    before = _current(conn, job, "analysis")["id"]
    with pytest.raises(asyncio.CancelledError):
        _drive(conn, job, FakeRun(ok(_analysis()), asyncio.CancelledError()))
    atts = repo.attempts(conn, job["id"])
    assert [(a["step"], a["outcome"]) for a in atts] == [("analyst", "ok"), ("criticizer", "cancelled")]
    assert _current(conn, job, "analysis")["id"] == before
    assert _current(conn, job, "feedback") is None



# ── 8a 工人異常 ──

def _with(r, *, turns, output):
    r.num_turns = turns
    r.tokens = None if output is None else {"output": output}
    return r


def test_worker_anomaly_warns_any_outcome(conn, caplog):
    """CLI 多跑輪 / 吐爆量(smoke:4 輪、132,533 tokens)→ WARNING,不論 outcome。"""
    job = _job(conn)
    run = FakeRun(_with(fail("crash"), turns=2, output=132533))
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        _drive(conn, job, run)
    hits = [r for r in caplog.records if "event=worker-anomaly" in r.getMessage()]
    assert len(hits) == 1 and hits[0].levelno == logging.WARNING
    assert (f"event=worker-anomaly job={job['id']} step=analyst turns=2 output_tokens=132533 "
            "duration_ms=5") == hits[0].getMessage()


def test_worker_anomaly_turns_on_ok(conn, caplog):
    job = _job(conn)
    run = FakeRun(_with(ok(_analysis()), turns=4, output=132533),
                  _with(ok(_feedback()), turns=2, output=4000))
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        out, _, _ = _drive(conn, job, run)
    assert out.state == "done"
    hits = [r.getMessage() for r in caplog.records if "event=worker-anomaly" in r.getMessage()]
    assert hits == [f"event=worker-anomaly job={job['id']} step=analyst turns=4 "
                    "output_tokens=132533 duration_ms=5"]


@pytest.mark.parametrize("turns,output", [(2, 4000), (3, 20000), (None, None), (None, 4000)],
                         ids=["normal", "at-threshold", "missing", "no-turns"])
def test_worker_anomaly_quiet_when_normal_or_missing(conn, caplog, turns, output):
    job = _job(conn)
    run = FakeRun(_with(ok(_analysis()), turns=turns, output=output),
                  _with(ok(_feedback()), turns=turns, output=output))
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        out, _, _ = _drive(conn, job, run)
    assert out.state == "done"
    assert "event=worker-anomaly" not in caplog.text


def test_worker_anomaly_tokens_without_output_key(conn, caplog):
    job = _job(conn)
    r = fail("crash")
    r.num_turns, r.tokens = 5, {"input": 3}
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        _drive(conn, job, FakeRun(r))
    assert "turns=5 output_tokens=None" in caplog.text
