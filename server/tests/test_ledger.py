"""帳本(usage/token ledger)零成本 canary。
跑法(repo 根):  ./server/.venv/bin/python -m server.tests.test_ledger
"""
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from server import config, sdk_runner

logging.getLogger("hyenovel").addHandler(logging.NullHandler())


# ── 測試工具 ────────────────────────────────────────────────────────
def _fake_turn(cost=0.3, input=0, output=0, cc=0, cr=0):
    u = {"input_tokens": input, "output_tokens": output,
         "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}
    return sdk_runner.TurnResult(text="", cost=cost, is_error=False, usage=u,
                                 model_usage={"sonnet": {}}, num_turns=1, duration_ms=1200)


class _tmp_stories:
    """把 config.STORIES 指到臨時空目錄,離開還原;ledger 於呼叫時讀 config.STORIES,故生效。"""
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._orig = config.STORIES
        config.STORIES = Path(self._t.name)
        return config.STORIES

    def __exit__(self, *a):
        config.STORIES = self._orig
        self._t.cleanup()


# ── Task 1 ──────────────────────────────────────────────────────────
def test_run_turn_captures_usage():
    from claude_agent_sdk import ResultMessage

    class FakeClient:
        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield ResultMessage(
                subtype="success", duration_ms=1500, duration_api_ms=1400,
                is_error=False, num_turns=2, session_id="s", total_cost_usd=0.3,
                usage={"input_tokens": 100, "output_tokens": 50,
                       "cache_creation_input_tokens": 200, "cache_read_input_tokens": 900},
                model_usage={"claude-sonnet-x": {"cost_usd": 0.3}})

    r = asyncio.run(sdk_runner.run_turn(FakeClient(), "go"))
    assert r.cost == 0.3, "cost 該接到"
    assert r.usage and r.usage["cache_read_input_tokens"] == 900, "usage 四欄該接到"
    assert r.model_usage and "claude-sonnet-x" in r.model_usage, "model_usage 該接到"
    assert r.num_turns == 2 and r.duration_ms == 1500, "num_turns/duration_ms 該接到"


# ── Task 2 ──────────────────────────────────────────────────────────
def test_append_writes_and_load_reads():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3, input=100, cr=900, output=50))
        ledger.append("s99", "criticizer", 0, _fake_turn(cost=0.4, input=60))
        rows = ledger.load("s99")
        assert len(rows) == 2, "該有兩行"
        assert rows[0]["phase"] == "analyst" and rows[0]["cache_read"] == 900
        assert rows[0]["cost_usd"] == 0.3 and rows[0]["input"] == 100
        assert rows[1]["phase"] == "criticizer" and rows[1]["input"] == 60


def test_append_skips_missing_dir():
    from server import ledger
    with _tmp_stories():
        ledger.append("s_nonexistent", "analyst", 0, _fake_turn())   # 不該炸
        assert ledger.load("s_nonexistent") == []


def test_load_skips_bad_line():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "usage.jsonl").write_text(
            '{"phase":"analyst"}\nNOT JSON\n{"phase":"discuss"}\n', encoding="utf-8")
        rows = ledger.load("s99")
        assert len(rows) == 2 and rows[1]["phase"] == "discuss"


# ── Task 3 ──────────────────────────────────────────────────────────
def test_aggregate_sums_and_ratio():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3, input=100, cc=200, cr=900, output=50))
        ledger.append("s99", "criticizer", 0, _fake_turn(cost=0.4, input=60, cr=300, output=40))
        agg = ledger.aggregate("s99")
        assert agg["empty"] is False
        assert agg["total"]["cost_usd"] == 0.7
        assert agg["total"]["cache_read"] == 1200
        assert agg["phases"]["analyst"]["input"] == 100
        # ratio = cache_read / (input + cache_creation + cache_read) = 1200 / (160+200+1200)
        assert agg["cache_read_ratio"] == round(1200 / 1560, 4)


def test_aggregate_retry_cost():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3))
        ledger.append("s99", "analyst", 1, _fake_turn(cost=0.25))   # attempt>0 = 重試那輪
        agg = ledger.aggregate("s99")
        assert agg["retry_cost_usd"] == 0.25


def test_aggregate_empty():
    from server import ledger
    with _tmp_stories():
        agg = ledger.aggregate("s_none")
        assert agg["empty"] is True and agg["total"]["cost_usd"] == 0.0


def test_aggregate_all_grand_total():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s01").mkdir()
        (S / "s02").mkdir()
        ledger.append("s01", "analyst", 0, _fake_turn(cost=0.3))
        ledger.append("s02", "analyst", 0, _fake_turn(cost=0.5))
        allagg = ledger.aggregate_all()
        assert allagg["empty"] is False
        assert allagg["total"]["cost_usd"] == 0.8
        assert {s["slug"] for s in allagg["stories"]} == {"s01", "s02"}


# ── Task 4 ──────────────────────────────────────────────────────────
def test_drive_phase_appends_ledger():
    from server import orchestrator, ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()

        async def run_one(prompt):
            return _fake_turn(cost=0.3, input=10)

        def gate_ok(slug):
            return True, ""

        async def drive():
            async for _ in orchestrator._drive_phase(
                    "analyst", run_one, gate_ok, "s99", "p", lambda d: "r"):
                pass

        asyncio.run(drive())
        rows = ledger.load("s99")
        assert len(rows) == 1, "analyst 一輪該記一筆"
        assert rows[0]["phase"] == "analyst" and rows[0]["cost_usd"] == 0.3


# ── Task 5 ──────────────────────────────────────────────────────────
def test_usage_endpoints_callable():
    from server import app as appmod, ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3))
        one = appmod.usage_one("s99")
        assert one["slug"] == "s99" and one["total"]["cost_usd"] == 0.3
        allr = appmod.usage_all()
        assert allr["total"]["cost_usd"] == 0.3 and allr["empty"] is False


def test_append_swallows_io_error():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "usage.jsonl").mkdir()          # open("a") → IsADirectoryError
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3))   # 不該拋


def test_load_swallows_io_error():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "usage.jsonl").mkdir()          # read_text → IsADirectoryError
        assert ledger.load("s99") == []


# ── Unit B Task 1 ──────────────────────────────────────────────────
def test_aggregate_turns_and_retry_count():
    from server import ledger
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        ledger.append("s99", "analyst", 0, _fake_turn(cost=0.3))
        ledger.append("s99", "analyst", 1, _fake_turn(cost=0.25))   # 重試那輪
        ledger.append("s99", "criticizer", 0, _fake_turn(cost=0.4))
        ledger.append("s99", "discuss", 0, _fake_turn(cost=0.2))
        ledger.append("s99", "discuss", 0, _fake_turn(cost=0.2))
        agg = ledger.aggregate("s99")
        assert agg["phases"]["analyst"]["turns"] == 2
        assert agg["phases"]["criticizer"]["turns"] == 1
        assert agg["phases"]["discuss"]["turns"] == 2
        assert agg["retry_count"] == 1


def test_aggregate_empty_has_retry_count():
    from server import ledger
    with _tmp_stories():
        agg = ledger.aggregate("s_none")
        assert agg["empty"] is True and agg["retry_count"] == 0


# ── 累計成本 → 單輪增量 ──────────────────────────────────────────────
class _CumulativeClient:
    """假 client:照 CLI 真行為,每輪回報「這個 client 開跑至今的累計花費」。
    數字取自 s07 真帳(analyst 兩次嘗試共用同一 client)。"""
    def __init__(self, totals):
        self._totals = list(totals)

    async def query(self, prompt):
        pass

    async def receive_response(self):
        from claude_agent_sdk import ResultMessage
        yield ResultMessage(
            subtype="success", duration_ms=1500, duration_api_ms=1400,
            is_error=False, num_turns=4, session_id="s",
            total_cost_usd=self._totals.pop(0),
            usage={"input_tokens": 5, "output_tokens": 12000,
                   "cache_creation_input_tokens": 29000, "cache_read_input_tokens": 28000},
            model_usage={"claude-sonnet-4-6": {}})


def test_cost_is_this_turn_not_session_cumulative():
    c = _CumulativeClient([0.371415, 0.745130])
    first = asyncio.run(sdk_runner.run_turn(c, "go"))
    second = asyncio.run(sdk_runner.run_turn(c, "retry"))
    assert abs(first.cost - 0.371415) < 1e-9, f"第一輪 = 累計本身,得 {first.cost}"
    assert abs(second.cost - 0.373715) < 1e-9, \
        f"第二輪該是增量 0.373715(0.745130-0.371415),不是累計 0.745130;得 {second.cost}"


def test_cost_restarts_per_client():
    a = _CumulativeClient([0.90])
    b = _CumulativeClient([0.20])
    asyncio.run(sdk_runner.run_turn(a, "go"))
    r = asyncio.run(sdk_runner.run_turn(b, "go"))
    assert abs(r.cost - 0.20) < 1e-9, f"另一個 client 自己從 0 起算,不受 a 影響;得 {r.cost}"


def test_ledger_total_matches_true_spend():
    """s07 實況:analyst 一個 client 跑兩次(累計 0.371415 → 0.745130)、
    criticizer 另一個 client 跑一次(0.270338)。真實總花費 = 0.745130 + 0.270338。"""
    from server import ledger
    with _tmp_stories() as stories:
        (stories / "s07").mkdir()
        analyst = _CumulativeClient([0.371415, 0.745130])
        for attempt in (0, 1):
            ledger.append("s07", "analyst", attempt,
                          asyncio.run(sdk_runner.run_turn(analyst, "p")))
        criticizer = _CumulativeClient([0.270338])
        ledger.append("s07", "criticizer", 0,
                      asyncio.run(sdk_runner.run_turn(criticizer, "p")))

        agg = ledger.aggregate("s07")
        assert abs(agg["total"]["cost_usd"] - 1.015468) < 1e-6, \
            f"總帳該是 1.015468,不是重複計的 1.386883;得 {agg['total']['cost_usd']}"
        assert abs(agg["phases"]["analyst"]["cost_usd"] - 0.745130) < 1e-6, \
            f"analyst 該格 = 0.745130;得 {agg['phases']['analyst']['cost_usd']}"


def test_discuss_records_this_turn_not_running_total():
    """discuss 是常駐 client、多輪 query → 累計值最毒(聊 N 輪等於三角級數式暴脹)。
    連兩輪累計 0.20 → 0.45,帳本該記 0.20 與 0.25。"""
    from server import discuss, ledger

    async def drive(sid, msg):
        return [ev async for ev in discuss.run_discuss("s01", sid, msg)]

    with _tmp_stories() as stories:
        (stories / "s01").mkdir()
        (stories / "s01" / "analysis.json").write_text("{}", encoding="utf-8")
        client = _CumulativeClient([0.20, 0.45])
        sid = "sess_test"
        discuss._sessions[sid] = discuss.Session("s01", client)
        try:
            asyncio.run(drive(sid, "第一輪"))
            events = asyncio.run(drive(sid, "第二輪"))
        finally:
            discuss._sessions.pop(sid, None)

        rows = ledger.load("s01")
        assert len(rows) == 2, f"兩輪該記兩列;得 {len(rows)}"
        assert abs(rows[0]["cost_usd"] - 0.20) < 1e-9, f"第一輪 0.20;得 {rows[0]['cost_usd']}"
        assert abs(rows[1]["cost_usd"] - 0.25) < 1e-9, \
            f"第二輪該記增量 0.25,不是累計 0.45;得 {rows[1]['cost_usd']}"
        done = [e for e in events if e["event"] == "done"][0]
        assert abs(done["data"]["cost_usd"] - 0.25) < 1e-6, \
            f"done 事件回報的也該是這輪的錢;得 {done['data']['cost_usd']}"


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    _main()
