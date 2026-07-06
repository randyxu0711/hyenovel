"""零成本回歸 canary(不燒訂閱):守住加固後不會無聲退回舊行為。
跑法(repo 根):  ./server/.venv/bin/python -m server.tests.test_hardening
"""
import atomicio
from server import sdk_runner, config


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
