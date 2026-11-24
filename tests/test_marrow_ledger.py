import sqlite3

import pytest

from marrow import repo

TOK = {"input": 2, "output": 28, "cache_read": 649, "cache_creation": 1512, "thinking": 0}


def _finish(conn, cid, outcome="ok"):
    repo.finish_call(conn, cid, outcome=outcome, ended_at=11.0, duration_ms=1000, tokens=TOK,
                     tokens_partial=False, cost_usd=0.01, model="m", rate_limit={"five_hour": {"utilization": 0.22}})


def test_start_then_finish_roundtrip(conn):
    cid = repo.start_call(conn, "chat", 10.0, "fp1", tag="m6-on", sizes={"base": 120}, story_id=1)
    row = repo.calls_since(conn, 0)[0]
    assert row["id"] == cid and row["outcome"] is None and row["sizes"] == {"base": 120} and row["tag"] == "m6-on"
    assert row["tokens"] is None and row["rate_limit"] is None
    _finish(conn, cid)
    row = repo.get_call(conn, cid)
    assert row["tokens"]["output"] == 28 and row["tokens_partial"] == 0
    assert row["rate_limit"]["five_hour"]["utilization"] == 0.22 and row["story_id"] == 1


def test_finish_without_tokens(conn):
    cid = repo.start_call(conn, "chat", 1.0, "fp")
    repo.finish_call(conn, cid, outcome="cancelled", ended_at=2.0, duration_ms=None, tokens=None,
                     tokens_partial=False, cost_usd=None, model=None, rate_limit=None)
    assert repo.get_call(conn, cid)["tokens"] is None


def test_link_sets_only_given_keys(conn):
    cid = repo.start_call(conn, "chat", 1.0, "fp", story_id=7)
    repo.link_call(conn, cid, discussion_id=3, seq=4, variant=1)
    row = repo.get_call(conn, cid)
    assert (row["story_id"], row["discussion_id"], row["seq"], row["variant"]) == (7, 3, 4, 1)


def test_unknown_key_rejected(conn):
    with pytest.raises(ValueError):
        repo.start_call(conn, "chat", 1.0, "fp", text="x")
    cid = repo.start_call(conn, "chat", 1.0, "fp")
    with pytest.raises(ValueError):
        repo.link_call(conn, cid, text="x")


def test_mark_only_overrides_ok(conn):
    a = repo.start_call(conn, "analyst", 1.0, "fp")
    b = repo.start_call(conn, "analyst", 2.0, "fp")
    _finish(conn, a)
    _finish(conn, b, "cancelled")
    repo.mark_call(conn, a, "gate_rejected")
    repo.mark_call(conn, b, "discarded")
    assert repo.get_call(conn, a)["outcome"] == "gate_rejected"
    assert repo.get_call(conn, b)["outcome"] == "cancelled"
    with pytest.raises(ValueError):
        repo.mark_call(conn, a, "ok")


def test_calls_since_filters_and_orders(conn):
    for t in (25.0, 5.0, 15.0):
        repo.start_call(conn, "chat", t, "fp")
    assert [r["started_at"] for r in repo.calls_since(conn, 10)] == [15.0, 25.0]


def test_kind_check_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        repo.start_call(conn, "other", 1.0, "fp")
