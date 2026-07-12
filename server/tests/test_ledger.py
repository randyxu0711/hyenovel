"""帳本(usage/token ledger)零成本 canary。
跑法(repo 根):  ./server/.venv/bin/python -m server.tests.test_ledger
"""
import asyncio
import json
import tempfile
from pathlib import Path

from server import config, sdk_runner


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
