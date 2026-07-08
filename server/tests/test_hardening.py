"""零成本回歸 canary(不燒訂閱):守住加固後不會無聲退回舊行為。
跑法(repo 根):  ./server/.venv/bin/python -m server.tests.test_hardening
"""
from server import sdk_runner, config


def test_log_setup_idempotent():
    from server import log
    log.setup()
    n = len(log.log.handlers)
    log.setup()                       # 再呼一次不該重複加 handler
    assert log.log.handlers, "setup 後該有 handler"
    assert len(log.log.handlers) == n, "setup 必須冪等"
    assert log.log.name == "hyenovel"


def test_load_agent_prompt_strips_frontmatter():
    for name in ("analyst", "criticizer"):
        body = sdk_runner.load_agent_prompt(name)
        assert body, f"{name} body 不該為空"
        assert not body.startswith("---"), f"{name} frontmatter 沒剝掉"
        assert "description:" not in body.split("\n", 1)[0]


def test_async_dispatch_detection():
    assert sdk_runner.contains_async_dispatch("... Async agent launched successfully\nagentId: x")
    assert not sdk_runner.contains_async_dispatch("正常摘要,無背景派工")


def test_classify_failure():
    assert sdk_runner.classify_failure("... Stream closed at sendRequest") == "usage-limit"
    assert sdk_runner.classify_failure("Error in hook callback hook_0") == "usage-limit"
    assert sdk_runner.classify_failure("Async agent launched successfully") == "async-dispatch"
    assert sdk_runner.classify_failure("max_budget exceeded") == "budget"
    assert sdk_runner.classify_failure("some other failure") == "unknown"


def test_agent_options_shape():
    opt = sdk_runner.agent_options("analyst")
    assert opt.system_prompt, "system_prompt 該是 analyst body"
    assert opt.allowed_tools == ["Read", "Write"]
    assert "Task" in opt.disallowed_tools, "必須禁 Task(斷 async 巢狀)"
    assert "Bash" in opt.disallowed_tools, "必須禁 Bash(斷亂試)"
    assert opt.max_turns == config.AGENT_MAX_TURNS


def test_rate_limit_of():
    from claude_agent_sdk import RateLimitEvent, RateLimitInfo
    ev = RateLimitEvent(
        rate_limit_info=RateLimitInfo(status="rejected", resets_at=999, rate_limit_type="five_hour"),
        uuid="u", session_id="s")
    info = sdk_runner.rate_limit_of(ev)
    assert info is not None and info.status == "rejected" and info.resets_at == 999
    assert sdk_runner.rate_limit_of("不是事件的東西") is None
    assert sdk_runner.rate_limit_of(None) is None


def test_capacity_failure_classifier():
    from claude_agent_sdk import RateLimitInfo
    T = sdk_runner.TurnResult
    assert sdk_runner._capacity_failure(T("", 0.0, True, 429)) == "hard"
    assert sdk_runner._capacity_failure(T("", 0.0, True, 529)) == "transient"
    assert sdk_runner._capacity_failure(T("", 0.0, True, 500)) == "transient"
    assert sdk_runner._capacity_failure(T("", 0.0, False, None)) is None
    assert sdk_runner._capacity_failure(T("", 0.0, True, None)) is None   # error 但無容量碼 → 走內容路
    # 沒 api 碼但 RateLimitEvent 說 rejected → 也算硬上限
    r = T("", 0.0, True, None, rate_limit=RateLimitInfo(status="rejected", resets_at=1))
    assert sdk_runner._capacity_failure(r) == "hard"


def test_backoff_config_present():
    assert isinstance(config.TRANSIENT_MAX_RETRIES, int) and config.TRANSIENT_MAX_RETRIES >= 1
    assert isinstance(config.BACKOFF_BASE, (int, float)) and config.BACKOFF_BASE >= 0


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
