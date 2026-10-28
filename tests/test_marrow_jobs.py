"""marrow.repo 的 job / attempt / 單筆讀取。repo 不 commit,測試直接在 conn 上跑。"""
from marrow import repo


def _job(conn, text="一二三", now=1.0):
    s = repo.ensure_story(conn, f"s{now}", None, 0)
    v, _ = repo.add_source_version(conn, s, text, 0)
    return repo.create_job(conn, "critique", s, v, {"fresh": True}, now), s, v


def _att(conn, jid, step, n, outcome, **kw):
    args = dict(runner="cli", model="sonnet", cli_version="1", raw_output=None, parsed=None,
                gate_verdict=None, tokens=None, duration_ms=None, artifact_id=None, now=0.0)
    args.update(kw)
    return repo.add_attempt(conn, jid, step, n, outcome=outcome, **args)


def test_job_lifecycle(conn):
    jid, s, v = _job(conn)
    j = repo.get_job(conn, jid)
    assert j["state"] == "queued" and j["params"] == {"fresh": True} and j["detail"] is None
    assert (j["story_id"], j["source_version_id"]) == (s, v)
    c = repo.claim_next_job(conn, 2.0)
    assert c["id"] == jid and c["state"] == "running" and c["updated_at"] == 2.0
    assert repo.claim_next_job(conn, 3.0) is None
    assert repo.get_job(conn, 999) is None


def test_claim_fifo(conn):
    a, _, _ = _job(conn, now=1.0)
    b, _, _ = _job(conn, now=2.0)
    assert repo.claim_next_job(conn, 3.0)["id"] == a
    assert repo.claim_next_job(conn, 3.0)["id"] == b


def test_set_job_state_keeps_step_and_encodes_detail(conn):
    jid, _, _ = _job(conn)
    repo.set_job_state(conn, jid, "paused", 5.0, step="analyst", error_class="usage-limit",
                       detail={"message": "m", "resets_at": 9})
    j = repo.get_job(conn, jid)
    assert (j["state"], j["step"], j["error_class"]) == ("paused", "analyst", "usage-limit")
    assert j["detail"] == {"message": "m", "resets_at": 9}
    repo.set_job_state(conn, jid, "done", 6.0)                # step 不傳 → 保留;error/detail 清掉
    j = repo.get_job(conn, jid)
    assert j["step"] == "analyst" and j["error_class"] is None and j["detail"] is None


def test_requeue_only_resumable(conn):
    for st in ("done", "running", "queued"):
        jid, _, _ = _job(conn)
        repo.set_job_state(conn, jid, st, 2.0)
        assert repo.requeue_job(conn, jid, 3.0) is False
        assert repo.get_job(conn, jid)["state"] == st
    for st in ("paused", "failed", "cancelled"):
        jid, _, _ = _job(conn)
        repo.set_job_state(conn, jid, st, 2.0, error_class="x", detail={"message": "m"})
        assert repo.requeue_job(conn, jid, 3.0) is True
        j = repo.get_job(conn, jid)
        assert j["state"] == "queued" and j["error_class"] is None and j["detail"] is None


def test_recover_running_marks_crash(conn):
    a, _, _ = _job(conn, now=1.0)
    b, _, _ = _job(conn, now=2.0)
    c, _, _ = _job(conn, now=3.0)
    repo.set_job_state(conn, a, "running", 4.0)
    repo.set_job_state(conn, b, "running", 4.0)
    assert repo.recover_running_jobs(conn, 5.0) == [a, b]
    for jid in (a, b):
        j = repo.get_job(conn, jid)
        assert j["state"] == "failed" and j["error_class"] == "crash"
    assert repo.get_job(conn, c)["state"] == "queued"
    assert repo.recover_running_jobs(conn, 6.0) == []


def test_attempt_roundtrip_and_ok_attempt(conn):
    jid, s, v = _job(conn)
    aid, _ = repo.add_artifact(conn, s, v, "analysis", 1, {"x": 1}, {}, 0)
    _att(conn, jid, "analyst", 0, "gate", gate_verdict={"ok": False}, tokens={"in": 1})
    _att(conn, jid, "analyst", 1, "ok", parsed={"x": 1}, artifact_id=aid, duration_ms=7)
    ok = repo.ok_attempt(conn, jid, "analyst")
    assert ok["n"] == 1 and ok["artifact_id"] == aid and ok["parsed"] == {"x": 1}
    assert ok["gate_verdict"] is None and ok["tokens"] is None
    got = repo.attempts(conn, jid)
    assert [a["n"] for a in got] == [0, 1]
    assert got[0]["gate_verdict"] == {"ok": False} and got[0]["tokens"] == {"in": 1}
    assert repo.ok_attempt(conn, jid, "criticizer") is None
    assert repo.artifact(conn, aid)["body"] == {"x": 1}
    assert repo.artifact(conn, 999) is None


def test_attempt_history_chars(conn):
    jid, _, _ = _job(conn, text="一二三")
    other, _, _ = _job(conn, text="一二三四五", now=2.0)
    _att(conn, jid, "analyst", 0, "gate", duration_ms=1)
    _att(conn, jid, "analyst", 1, "ok", duration_ms=5, tokens={"out": 9})
    _att(conn, other, "criticizer", 0, "ok", duration_ms=2)
    assert repo.attempt_history(conn, "analyst") == [
        {"chars": 3, "duration_ms": 5, "tokens": {"out": 9}}]
    assert repo.attempt_history(conn, "criticizer")[0]["chars"] == 5


def test_story_and_source_version_by_id(conn):
    _, s, v = _job(conn)
    assert repo.story(conn, s)["id"] == s and repo.story(conn, 999) is None
    sv = repo.source_version(conn, v)
    assert sv["text"] == "一二三" and sv["story_id"] == s
    assert repo.source_version(conn, 999) is None
