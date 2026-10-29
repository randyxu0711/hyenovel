"""den.jobs 行為契約:先持久化、循序、取消可續、崩潰收尾、事件補播。

假 run_factory 用 asyncio.Event 卡住;絕不 spawn 真 claude。
同步測試裡用 asyncio.run 驅動(沒裝 pytest-asyncio)。
"""
import asyncio
import logging

import pytest

from den import jobs
from den.pipeline import StepOutcome
from den.tests.test_pipeline import _analysis, _feedback, fail, ok
from marrow import repo
from marrow.workpacks import WORKPACKS


class GatedRun:
    """run_factory:每次 run 先等 gate,再依 schema 吐 ok(analysis) 或 ok(feedback)。"""

    def __init__(self, *, gated=True, exc=None):
        self.gate = asyncio.Event()
        if not gated:
            self.gate.set()
        self.started = asyncio.Event()
        self.calls = 0
        self.exc = exc

    def __call__(self, on_proc):
        if self.exc:
            raise self.exc

        async def run(system_prompt, user_prompt, schema):
            self.calls += 1
            self.started.set()
            await self.gate.wait()
            return ok(_analysis() if schema is WORKPACKS["analyst"].schema else _feedback())
        return run


def _mgr(conn, factory):
    return jobs.JobManager(conn, factory, runner_name="claude-cli", cli_version="9.9.9")


async def _until(pred, what):
    for _ in range(2000):
        if pred():
            return
        await asyncio.sleep(0)
    raise AssertionError(f"等不到:{what}")


def _state(conn, jid):
    return repo.get_job(conn, jid)["state"]


async def _stop(task):
    """模擬 app 關機:worker 必須在有限時間內以 CancelledError 結束。"""
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=5)
    assert done, "worker 被取消後沒有退出"
    assert task.cancelled()


def test_submit_persists_before_return(conn):
    m = _mgr(conn, GatedRun())
    out = m.submit("mini")
    assert not conn.in_transaction
    assert _state(conn, out["job_id"]) == "queued"
    assert out["estimate"] is None                     # mini 沒有 attempt 歷史


def test_submit_unknown_slug_raises(conn, caplog):
    m = _mgr(conn, GatedRun())
    with caplog.at_level(logging.INFO, logger="hyenovel"), pytest.raises(LookupError):
        m.submit("nope")
    assert "event=submit-rejected" in caplog.text
    assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_worker_runs_one_at_a_time(conn):
    async def main():
        run = GatedRun()
        m = _mgr(conn, run)
        with conn:   # 第二篇(同文,假分析的引文才對得上):同篇同版會被去重,不會排出第二個 job
            text = repo.latest_source_version(conn, repo.story_by_slug(conn, "mini")["id"])["text"]
            sid = repo.ensure_story(conn, "other", None, 0)
            repo.add_source_version(conn, sid, text, 0)
        a, b = m.submit("mini")["job_id"], m.submit("other")["job_id"]
        w = asyncio.create_task(m.worker())
        await asyncio.wait_for(run.started.wait(), 5)
        assert (_state(conn, a), _state(conn, b)) == ("running", "queued")
        assert repo.get_job(conn, a)["step"] == "analyst"
        run.gate.set()
        await _until(lambda: _state(conn, b) == "done", "第二個 job 跑完")
        assert _state(conn, a) == "done"
        await _stop(w)
    asyncio.run(main())


def test_worker_idles_until_submit(conn):
    async def main():
        run = GatedRun(gated=False)
        m = _mgr(conn, run)
        w = asyncio.create_task(m.worker())
        for _ in range(50):
            await asyncio.sleep(0)
        assert run.calls == 0
        jid = m.submit("mini")["job_id"]
        await _until(lambda: _state(conn, jid) == "done", "submit 後被喚醒跑完")
        await _stop(w)
    asyncio.run(main())


def test_cancel_running_marks_cancelled_and_resumable(conn):
    async def main():
        run = GatedRun()
        m = _mgr(conn, run)
        jid = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await asyncio.wait_for(run.started.wait(), 5)
        assert m.cancel(jid) is True
        await _until(lambda: _state(conn, jid) == "cancelled", "取消落地")
        assert [a["outcome"] for a in repo.attempts(conn, jid)] == ["cancelled"]
        assert m.resume(jid) is True
        assert _state(conn, jid) == "queued"
        run.gate.set()
        await _until(lambda: _state(conn, jid) == "done", "續跑跑完")
        q = m.bus.subscribe(jid)                     # 續跑後補播的只有這一輪,沒有上輪的取消
        evs = [q.get_nowait() for _ in range(q.qsize())]
        assert evs[-1]["event"] == "done"
        assert not any(e["event"] == "error" for e in evs)
        await _stop(w)
    asyncio.run(main())


def test_cancel_queued_marks_cancelled(conn):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    assert m.cancel(jid) is True
    assert _state(conn, jid) == "cancelled"
    assert m.bus._events[jid][-1]["data"]["reason"] == "cancelled"


def test_resume_clears_stale_error_before_claim(conn):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    assert m.cancel(jid) is True                     # queued → cancelled,發收尾 error
    assert m.resume(jid) is True                     # 沒有 worker:停在 queued 未被 claim
    q = m.bus.subscribe(jid)
    assert q.empty()
    assert _state(conn, jid) == "queued"


def test_cancel_done_returns_false(conn, caplog):
    async def main():
        m = _mgr(conn, GatedRun(gated=False))
        jid = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, jid) == "done", "跑完")
        await _stop(w)
        return m, jid
    m, jid = asyncio.run(main())
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert m.cancel(jid) is False
        assert m.cancel(9999) is False
        assert m.resume(jid) is False
    assert _state(conn, jid) == "done"
    assert caplog.text.count("event=cancel-rejected") == 2
    assert "event=resume-rejected" in caplog.text


def test_outcome_state_written(conn, monkeypatch):
    async def stop(*a, **k):
        return StepOutcome("paused", "usage-limit", {"message": "額度", "resets_at": None})
    monkeypatch.setattr(jobs.pipeline, "run_critique", stop)

    async def main():
        m = _mgr(conn, GatedRun(gated=False))
        jid = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, jid) == "paused", "paused 落地")
        await _stop(w)
        return jid
    jid = asyncio.run(main())
    job = repo.get_job(conn, jid)
    assert (job["error_class"], job["detail"]["message"]) == ("usage-limit", "額度")


def test_worker_crash_marks_failed(conn, caplog):
    async def main():
        m = _mgr(conn, GatedRun(exc=OSError("接線壞了")))
        jid = m.submit("mini")["job_id"]
        q = m.bus.subscribe(jid)
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, jid) == "failed", "崩潰收尾")
        again = m.submit("mini")["job_id"]           # 崩潰不能把 worker 迴圈帶走
        await _until(lambda: _state(conn, again) == "failed", "worker 還活著")
        await _stop(w)
        return jid, q
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        jid, q = asyncio.run(main())
    assert repo.get_job(conn, jid)["error_class"] == "crash"
    assert "event=job-crash" in caplog.text
    ev = q.get_nowait()
    assert ev["event"] == "error"
    assert (ev["data"]["reason"], ev["data"]["recoverable"]) == ("crash", True)


def test_shutdown_cancel_exits_and_leaves_job_for_recovery(conn):
    async def main():
        run = GatedRun()
        m = _mgr(conn, run)
        jid = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await asyncio.wait_for(run.started.wait(), 5)
        await _stop(w)
        return m, jid
    m, jid = asyncio.run(main())
    # 關機不是使用者取消:不寫 cancelled,留給下次 startup 判 crash
    assert _state(conn, jid) == "running"
    m.startup()
    assert repo.get_job(conn, jid)["error_class"] == "crash"


def test_startup_recovers_running_as_crash(conn, caplog):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    with conn:
        repo.claim_next_job(conn, 2.0)
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        m.startup()
    job = repo.get_job(conn, jid)
    assert (job["state"], job["error_class"]) == ("failed", "crash")
    assert f"event=job-recovered job={jid}" in caplog.text


def test_bus_replays_then_streams():
    async def main():
        bus = jobs.EventBus()
        bus.publish(1, {"event": "a"})
        bus.publish(1, {"event": "b"})
        q = bus.subscribe(1)
        bus.publish(1, {"event": "c"})
        bus.publish(2, {"event": "other"})
        got = [q.get_nowait() for _ in range(q.qsize())]
        assert got == [{"event": "a"}, {"event": "b"}, {"event": "c"}]
        bus.unsubscribe(1, q)
        bus.publish(1, {"event": "d"})
        assert q.empty()
    asyncio.run(main())


def test_bus_drops_finished_jobs_after_ttl():
    t = [0.0]
    bus = jobs.EventBus(now=lambda: t[0])
    bus.publish(1, {"event": "done"})
    bus.close(1)
    t[0] = jobs._DONE_TTL - 1
    bus.publish(2, {"event": "x"})
    assert bus.subscribe(1).qsize() == 1
    t[0] = jobs._DONE_TTL + 1
    bus.publish(2, {"event": "y"})
    assert bus.subscribe(1).qsize() == 0


def test_submit_estimate_failure_leaves_no_job(conn, monkeypatch):
    def boom(*a):
        raise ZeroDivisionError
    monkeypatch.setattr(jobs, "estimate", boom)
    m = _mgr(conn, GatedRun())
    with pytest.raises(ZeroDivisionError):
        m.submit("mini")
    assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_submit_dedupes_inflight_same_version(conn, caplog):
    """同篇同版還在 queued/running → 回同一個 job,不建第二個(第二份花費)。"""
    async def main():
        run = GatedRun()
        m = _mgr(conn, run)
        first = m.submit("mini")
        assert first["existing"] is False
        with caplog.at_level(logging.INFO, logger="hyenovel"):
            again = m.submit("mini")                       # queued
        assert again == {**first, "existing": True}
        assert f"event=job-deduped job={first['job_id']}" in caplog.text
        w = asyncio.create_task(m.worker())
        await asyncio.wait_for(run.started.wait(), 5)
        assert m.submit("mini")["job_id"] == first["job_id"]   # running
        assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
        run.gate.set()
        await _until(lambda: _state(conn, first["job_id"]) == "done", "跑完")
        rerun = m.submit("mini")                           # done 之後明確重跑 = 新 job
        assert rerun["existing"] is False and rerun["job_id"] != first["job_id"]
        await _until(lambda: _state(conn, rerun["job_id"]) == "done", "重跑完")
        await _stop(w)
    asyncio.run(main())


# ── 8c:同一版自動續跑、續跑防重 ──

class ScriptRun:
    """run_factory:analyst 一律 ok;criticizer 依 crit 腳本(先吐完再一律 ok)。記每步呼叫數。"""

    def __init__(self, *crit):
        self.crit = list(crit)
        self.calls = {"analyst": 0, "criticizer": 0}

    def __call__(self, on_proc):
        async def run(system_prompt, user_prompt, schema):
            if schema is WORKPACKS["analyst"].schema:
                self.calls["analyst"] += 1
                return ok(_analysis())
            self.calls["criticizer"] += 1
            return self.crit.pop(0) if self.crit else ok(_feedback())
        return run


def _job_count(conn):
    return conn.execute("SELECT COUNT(*) FROM job").fetchone()[0]


def test_submit_auto_resumes_paused_same_version(conn, caplog):
    async def main():
        run = ScriptRun(fail("usage-limit"))
        m = _mgr(conn, run)
        first = m.submit("mini")
        assert first["resumed"] is False
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, first["job_id"]) == "paused", "撞額度暫停")
        assert run.calls == {"analyst": 1, "criticizer": 1}
        with caplog.at_level(logging.INFO, logger="hyenovel"):
            again = m.submit("mini")
        assert again == {"job_id": first["job_id"], "estimate": again["estimate"],
                         "existing": True, "resumed": True, "previous_state": "paused",
                         "previous_error_class": "usage-limit"}
        assert f"event=job-auto-resumed job={first['job_id']}" in caplog.text
        assert _job_count(conn) == 1
        await _until(lambda: _state(conn, first["job_id"]) == "done", "續跑跑完")
        assert run.calls == {"analyst": 1, "criticizer": 2}      # analyst 有 ok attempt,不重跑
        q = m.bus.subscribe(first["job_id"])                     # bus 已 reset:沒有上一輪的 error
        evs = [q.get_nowait() for _ in range(q.qsize())]
        assert not any(e["event"] == "error" for e in evs)
        await _stop(w)
    asyncio.run(main())


def test_submit_auto_resumes_cancelled(conn):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    assert m.cancel(jid) is True
    again = m.submit("mini")
    assert (again["job_id"], again["resumed"], again["existing"]) == (jid, True, True)
    assert again["previous_error_class"] is None                # 取消的沒有 error_class
    assert _state(conn, jid) == "queued" and _job_count(conn) == 1
    assert m._wake.is_set()


def test_submit_after_done_is_new_job_not_resumed(conn):
    async def main():
        m = _mgr(conn, GatedRun(gated=False))
        first = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, first) == "done", "跑完")
        again = m.submit("mini")
        assert again["job_id"] != first and (again["existing"], again["resumed"]) == (False, False)
        await _until(lambda: _state(conn, again["job_id"]) == "done", "重跑完")
        await _stop(w)
    asyncio.run(main())


def test_submit_prefers_active_over_resumable(conn):
    m = _mgr(conn, GatedRun())
    old = m.submit("mini")["job_id"]
    m.cancel(old)
    st = repo.story_by_slug(conn, "mini")
    with conn:
        live = repo.create_job(conn, "critique", st["id"],
                               repo.latest_source_version(conn, st["id"])["id"], {}, 2.0)
    out = m.submit("mini")
    assert (out["job_id"], out["existing"], out["resumed"]) == (live, True, False)
    assert _state(conn, old) == "cancelled"


def test_resume_rejected_when_other_active_job(conn, caplog):
    m = _mgr(conn, GatedRun())
    old = m.submit("mini")["job_id"]
    m.cancel(old)
    st = repo.story_by_slug(conn, "mini")
    with conn:
        live = repo.create_job(conn, "critique", st["id"],
                               repo.latest_source_version(conn, st["id"])["id"], {}, 2.0)
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert m.resume(old) is False
    assert f"event=resume-rejected job={old} reason=active-job other={live}" in caplog.text
    assert _state(conn, old) == "cancelled"


def test_submit_auto_resume_reports_failed_gate_class(conn):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    with conn:
        repo.set_job_state(conn, jid, "failed", 2.0, error_class="gate")
    again = m.submit("mini")
    assert (again["job_id"], again["previous_error_class"]) == (jid, "gate")
    assert repo.get_job(conn, jid)["error_class"] is None          # requeue 清掉了,回傳的是之前的


def _paused(m, conn):
    jid = m.submit("mini")["job_id"]
    with conn:
        repo.set_job_state(conn, jid, "paused", 2.0, error_class="usage-limit")
    return jid


def test_resume_rejected_on_stale_version(conn, caplog):
    m = _mgr(conn, GatedRun())
    old = _paused(m, conn)
    with conn:   # 改稿:v1 的 job 跑完會把 current 換回舊分析
        repo.add_source_version(conn, repo.story_by_slug(conn, "mini")["id"], "改過的稿。", 3.0)
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert m.resume(old) is False
    assert f"event=resume-rejected job={old} reason=stale-version" in caplog.text
    assert _state(conn, old) == "paused"


def test_resume_rejected_when_version_already_done(conn, caplog):
    m = _mgr(conn, GatedRun())
    old = _paused(m, conn)
    st = repo.story_by_slug(conn, "mini")
    with conn:
        sib = repo.create_job(conn, "critique", st["id"],
                              repo.latest_source_version(conn, st["id"])["id"], {}, 3.0)
        repo.set_job_state(conn, sib, "done", 4.0)
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        assert m.resume(old) is False
        out = m.submit("mini")                                      # done 過 = 明確重跑:新 job
    assert f"event=resume-rejected job={old} reason=already-done" in caplog.text
    assert out["job_id"] not in (old, sib) and out["resumed"] is False
    assert _state(conn, old) == "paused"


def test_rerun_after_done_can_pause_and_resume(conn):
    """done J1 → 明確重跑 J2 停在半路 → J2 能續(直接 resume 與重送自動續跑都行)。"""
    async def main():
        run = ScriptRun()
        m = _mgr(conn, run)
        j1 = m.submit("mini")["job_id"]
        w = asyncio.create_task(m.worker())
        await _until(lambda: _state(conn, j1) == "done", "J1 跑完")
        run.crit.append(fail("usage-limit"))
        j2 = m.submit("mini")["job_id"]
        assert j2 != j1
        await _until(lambda: _state(conn, j2) == "paused", "J2 撞額度")
        again = m.submit("mini")                                   # 自動續跑 J2
        assert (again["job_id"], again["resumed"]) == (j2, True)
        await _until(lambda: _state(conn, j2) == "done", "J2 續跑完")
        assert run.calls == {"analyst": 2, "criticizer": 3}        # J2 的 analyst 沒重跑
        run.crit.append(fail("usage-limit"))
        j3 = m.submit("mini")["job_id"]
        await _until(lambda: _state(conn, j3) == "paused", "J3 撞額度")
        assert m.resume(j3) is True                                # 直接 resume 也行
        await _until(lambda: _state(conn, j3) == "done", "J3 續跑完")
        await _stop(w)
    asyncio.run(main())


@pytest.mark.parametrize("state, cls", [("paused", "usage-limit"), ("failed", None),
                                        ("cancelled", None)])
def test_submit_auto_resume_reports_previous_state(conn, state, cls):
    m = _mgr(conn, GatedRun())
    jid = m.submit("mini")["job_id"]
    with conn:
        repo.set_job_state(conn, jid, state, 2.0, error_class=cls)
    out = m.submit("mini")
    assert (out["job_id"], out["previous_state"], out["previous_error_class"]) == (jid, state, cls)
