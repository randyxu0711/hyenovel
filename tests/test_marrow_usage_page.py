import pytest

from marrow import repo, usage


def T(n, thinking=0):
    return {"input": n, "output": 0, "cache_read": 0, "cache_creation": 0, "thinking": thinking}


def call(conn, kind="chat", outcome="ok", tokens=None, partial=False, started=10.0, ms=100, fp="fp1",
         model="m", rate=None, runner="claude-cli", effort="medium", **keys):
    cid = repo.start_call(conn, kind, started, fp, runner=runner, effort=effort, **keys)
    if outcome is not None:
        repo.finish_call(conn, cid, outcome=outcome, ended_at=started + 1, duration_ms=ms,
                         tokens=T(100) if tokens is None else tokens or None, tokens_partial=partial,
                         cost_usd=None, model=model, rate_limit=rate)
    return repo.get_call(conn, cid)


def page(conn, rows, all_rows=None, now=1000.0):
    return usage.page(conn, rows, rows if all_rows is None else all_rows, now)


def work(conn, slug, versions=1, now=1.0, analyzed=()):
    sid = repo.ensure_story(conn, slug, None, now)
    vids = [repo.add_source_version(conn, sid, f"{slug} 第{i}版", now)[0] for i in range(1, versions + 1)]
    for n in analyzed:
        repo.add_artifact(conn, sid, vids[n - 1], "analysis", 1, {"n": n}, {}, now)
    return sid, vids


def job(conn, sid, vid, now=1.0):
    return repo.create_job(conn, "analyze", sid, vid, {}, now)


def test_page_empty(conn):
    p = page(conn, [])
    assert p["as_of"] == 1000.0 and p["total"] == {"tokens": 0, "partial": False}
    assert p["categories"] == [] and p["works"] == [] and p["unbound"] is None and p["quota"] is None
    assert p["unused_share"] is None and p["completeness"] == {"partial": 0, "unknown": 0}
    assert p["compare"] == {"config": [], "character": []}


def test_page_categories_share_and_avg(conn):
    rows = [call(conn, "analyst", tokens=T(100)), call(conn, "analyst", tokens=T(300)),
            call(conn, "chat", tokens=T(600))]
    p = page(conn, rows)
    assert p["total"]["tokens"] == 1000
    assert [(c["id"], c["n"], c["tokens"], c["share"], c["avg"]) for c in p["categories"]] == [
        ("analysis", 2, 400, 0.4, 200), ("chat", 1, 600, 0.6, 600)]


def test_token_sum_is_four_kinds_without_thinking(conn):
    row = call(conn, tokens={"input": 1, "output": 2, "cache_read": 3, "cache_creation": 4, "thinking": 2})
    assert page(conn, [row])["total"]["tokens"] == 10


def test_partial_counts_in_total_not_avg(conn):
    rows = [call(conn, outcome="cancelled", tokens=T(50), partial=True), call(conn, tokens=T(100))]
    p = page(conn, rows)
    assert p["total"] == {"tokens": 150, "partial": True}
    [c] = p["categories"]
    assert (c["tokens"], c["partial"], c["avg"]) == (150, True, 100)
    assert p["completeness"] == {"partial": 1, "unknown": 0}


def test_all_partial_avg_none(conn):
    rows = [call(conn, outcome="cancelled", tokens=T(50), partial=True)]
    [c] = page(conn, rows)["categories"]
    assert c["avg"] is None and c["partial"] is True


def test_unknown_only_is_empty_period(conn):
    call(conn, outcome=None)
    repo.close_open_calls(conn, 50.0)
    rows = repo.calls_since(conn, 0)
    p = page(conn, rows)
    assert p["total"]["tokens"] == 0 and p["categories"] == [] and p["completeness"] == {"partial": 0, "unknown": 1}
    assert p["running"] == 0


def test_running_calls_are_counted_apart(conn):
    rows = [call(conn, outcome=None), call(conn, kind="analyst", tokens=T(10))]
    p = page(conn, rows)
    assert p["running"] == 1 and p["total"]["tokens"] == 10 and p["completeness"] == {"partial": 0, "unknown": 0}
    assert [c["n"] for c in p["categories"]] == [1] and p["unused_share"] == 0


def test_unknown_kind_goes_to_other(conn):
    row = {**call(conn, tokens=T(10)), "kind": "future_kind"}
    assert [c["id"] for c in page(conn, [row])["categories"]] == ["other"]


def test_quota_ignores_period_and_status_only_rows(conn):
    old = call(conn, started=5.0, rate={"five_hour": {"utilization": 0.81, "resetsAt": 99.0, "status": "ok"},
                                        "status": "allowed"})
    newer = call(conn, started=50.0, rate={"status": "allowed"})
    now = call(conn, started=500.0)
    p = page(conn, [now], [old, newer, now])
    assert p["quota"] == {"at": 6.0, "five_hour": {"utilization": 0.81, "resets_at": 99.0}, "seven_day": None}


def test_quota_none_when_no_window(conn):
    rows = [call(conn, rate={"status": "allowed"})]
    assert page(conn, rows)["quota"] is None


def test_works_sorted_and_unbound(conn):
    a, _ = work(conn, "a")
    b, _ = work(conn, "b")
    c, _ = work(conn, "c")
    rows = [call(conn, "chat", tokens=T(10), story_id=a), call(conn, "chat", tokens=T(30), story_id=b),
            call(conn, "analyst", tokens=T(20), story_id=c), call(conn, "chat", tokens=T(5)),
            call(conn, "candidates", tokens=T(7)), call(conn, "analyst", tokens=T(9), story_id=999)]
    p = page(conn, rows)
    assert [(w["slug"], w["tokens"]) for w in p["works"]] == [("b", 30), ("c", 20), ("a", 10)]
    assert p["works"][1]["by_category"] == {"analysis": 20}
    assert p["unbound"] == {"tokens": 5, "partial": False, "by_category": {"chat": 5}}
    assert p["total"]["tokens"] == 81
    assert {c["id"]: c["tokens"] for c in p["categories"]} == {"analysis": 29, "chat": 45, "character": 7}


def test_unbound_none_without_unbound_conversations(conn):
    assert page(conn, [call(conn, "candidates")])["unbound"] is None


def test_archived_flag(conn):
    sid, _ = work(conn, "a")
    repo.archive_story(conn, sid, 2.0)
    [w] = page(conn, [call(conn, story_id=sid)])["works"]
    assert w["archived"] is True


def test_versions_tokens_and_analyzed(conn):
    sid, (v1, v2, v3) = work(conn, "a", versions=3, analyzed=(1, 2))
    j2, j3 = job(conn, sid, v2), job(conn, sid, v3)
    rows = [call(conn, "analyst", tokens=T(40), story_id=sid, job_id=j2),
            call(conn, "reviewer", tokens=T(60), story_id=sid, job_id=j2),
            call(conn, "analyst", outcome="crash", tokens=T(5), partial=True, story_id=sid, job_id=j3),
            call(conn, "chat", tokens=T(1), story_id=sid)]
    [w] = page(conn, rows)["works"]
    assert [(v["n"], v["tokens"], v["partial"], v["analyzed"]) for v in w["versions"]] == [
        (1, 0, False, True), (2, 100, False, True), (3, 5, True, False)]
    assert w["by_category"] == {"analysis": 105, "chat": 1} and w["partial"] is True


def test_version_unknown_job_ignored(conn):
    sid, _ = work(conn, "a")
    rows = [call(conn, "analyst", tokens=T(40), story_id=sid, job_id=12345)]
    [w] = page(conn, rows)["works"]
    assert w["tokens"] == 40 and [v["tokens"] for v in w["versions"]] == [0]


def test_reused_story_id(conn):
    old, (v,) = work(conn, "old", now=1.0)
    j = job(conn, old, v, now=1.0)
    stale = [call(conn, "analyst", tokens=T(70), started=2.0, story_id=old, job_id=j)]
    repo.delete_story(conn, old)
    new, (nv,) = work(conn, "new", now=5.0)
    assert new == old
    nj = job(conn, new, nv, now=5.0)
    assert nj == j
    fresh = [call(conn, "analyst", tokens=T(30), started=6.0, story_id=new, job_id=nj)]
    p = page(conn, stale + fresh)
    [w] = p["works"]
    assert (w["slug"], w["tokens"]) == ("new", 30) and [x["tokens"] for x in w["versions"]] == [30]
    assert p["total"]["tokens"] == 100 and p["unbound"] is None


def test_stale_job_on_live_story_not_counted_to_version(conn):
    sid, (v,) = work(conn, "a", now=1.0)
    j = job(conn, sid, v, now=50.0)
    [w] = page(conn, [call(conn, "analyst", tokens=T(30), started=10.0, story_id=sid, job_id=j)])["works"]
    assert w["tokens"] == 30 and w["versions"][0]["tokens"] == 0


def test_unused_share(conn):
    d = repo.ensure_discussion(conn, None, "s1", "web", None, 0.0)
    repo.add_utterance(conn, d, 0, "assistant", "答", 1.0, "den", [], None)
    rows = [call(conn, "chat", tokens=T(75), discussion_id=d, seq=0, variant=1),
            call(conn, "redo", tokens=T(25), discussion_id=d, seq=0, variant=2)]
    assert page(conn, rows)["unused_share"] == 0.25


def _cfg(p, kind="chat"):
    return [r for r in p["compare"]["config"] if r["kind"] == kind]


def test_compare_config_current_and_delta(conn):
    rows = [call(conn, tokens=T(100, 10), fp="old", started=1.0, ms=100),
            call(conn, tokens=T(120, 20), fp="new", started=2.0, ms=50)]
    new, old = _cfg(page(conn, rows))
    assert (new["prompt_fp"], new["current"], old["current"]) == ("new", True, False)
    assert new["delta"] == {"avg": pytest.approx(0.2), "thinking": pytest.approx(1.0), "ms": pytest.approx(-0.5)}
    assert old["delta"] is None
    assert (new["first_at"], new["last_at"], new["n"], new["avg"], new["thinking"], new["ms_median"]) == (
        2.0, 2.0, 1, 120, 20, 50)
    assert (new["runner"], new["model"], new["effort"], new["recorded"]) == ("claude-cli", "m", "medium", True)


def test_compare_delta_none_when_prev_zero_or_missing(conn):
    rows = [call(conn, tokens=T(100, 0), fp="old", started=1.0, ms=None),
            call(conn, tokens=T(120, 5), fp="new", started=2.0, ms=50)]
    new, _ = _cfg(page(conn, rows))
    assert new["delta"] == {"avg": pytest.approx(0.2), "thinking": None, "ms": None}


def test_compare_single_group_has_no_delta(conn):
    [only] = _cfg(page(conn, [call(conn)]))
    assert only["current"] is True and only["delta"] is None


def test_compare_model_change_is_new_row(conn):
    rows = [call(conn, model="a", started=1.0), call(conn, model="b", started=2.0)]
    assert [r["model"] for r in _cfg(page(conn, rows))] == ["b", "a"]


def test_compare_ignores_incomplete_rows(conn):
    rows = [call(conn, started=float(i)) for i in range(3)]
    rows.append(call(conn, outcome="cancelled", model=None, tokens=T(5), partial=True, started=9.0))
    rows.append(call(conn, outcome="crash", model=None, tokens=False, started=9.5))
    [g] = _cfg(page(conn, rows))
    assert g["n"] == 3 and g["current"] is True


def test_compare_current_is_last_used(conn):
    rows = [call(conn, effort="a", started=1.0, tokens=T(100)), call(conn, effort="b", started=2.0, tokens=T(50)),
            call(conn, effort="a", started=3.0, tokens=T(100))]
    a, b = sorted(_cfg(page(conn, rows)), key=lambda r: r["effort"])
    assert a["current"] is True and b["current"] is False and a["delta"]["avg"] == pytest.approx(1.0)


def test_compare_unrecorded_split_by_fp(conn):
    rows = [call(conn, runner=None, effort=None, fp="x", started=5.0),
            call(conn, runner=None, effort=None, fp="y", started=6.0, tokens=T(1)),
            call(conn, fp="z", started=1.0)]
    got = _cfg(page(conn, rows))
    assert [(r["prompt_fp"], r["recorded"], r["current"]) for r in got] == [
        ("y", False, False), ("x", False, False), ("z", True, True)]
    assert got[2]["delta"] is None and got[0]["runner"] is None and got[0]["model"] is None


def test_compare_kinds_ordered_and_separate(conn):
    rows = [call(conn, "chat"), call(conn, "analyst"), call(conn, "digest")]
    assert [r["kind"] for r in page(conn, rows)["compare"]["config"]] == ["analyst", "chat", "digest"]


def test_compare_character_groups(conn):
    rows = [call(conn, "chat", tokens=T(100), character_id="hyena", character_v=3, started=1.0),
            call(conn, "redo", tokens=T(150), character_id="hyena", character_v=4, started=2.0),
            call(conn, "chat", tokens=T(10), character_id="deer", character_v=1, started=3.0),
            call(conn, "chat", tokens=T(10), started=0.5),
            call(conn, "candidates", tokens=T(10), character_id="hyena", character_v=None, started=4.0)]
    got = page(conn, rows)["compare"]["character"]
    assert [(r["character_id"], r["character_v"], r["current"], r["recorded"]) for r in got] == [
        ("deer", 1, True, True), ("hyena", 4, True, True), ("hyena", 3, False, True), (None, None, False, False)]
    assert got[1]["delta"]["avg"] == pytest.approx(0.5) and got[0]["delta"] is None and got[3]["delta"] is None


def test_compare_uses_all_rows(conn):
    old = call(conn, fp="old", started=1.0, tokens=T(100))
    new = call(conn, fp="new", started=900.0, tokens=T(110))
    p = page(conn, [new], [old, new])
    assert [r["prompt_fp"] for r in _cfg(p)] == ["new", "old"] and p["total"]["tokens"] == 110
