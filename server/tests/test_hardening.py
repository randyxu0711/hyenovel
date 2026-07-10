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


def test_run_turn_returns_turnresult_type():
    # 只驗回傳建構子存在且欄位齊(不連真 client;真跑由 smoke 覆蓋)
    r = sdk_runner.TurnResult("hi", 0.3, False)
    assert (r.text, r.cost, r.is_error) == ("hi", 0.3, False)
    assert r.api_error_status is None and r.rate_limit is None


def test_backoff_config_present():
    assert isinstance(config.TRANSIENT_MAX_RETRIES, int) and config.TRANSIENT_MAX_RETRIES >= 1
    assert isinstance(config.BACKOFF_BASE, (int, float)) and config.BACKOFF_BASE >= 0


def _run_drive(run_one, gate):
    """跑 _drive_phase,收集事件;回 (calls_ref, result_payload)。"""
    import asyncio
    from server import orchestrator
    calls = {"n": 0}
    async def counted(prompt):
        calls["n"] += 1
        return await run_one(prompt, calls["n"])
    out = {}
    async def drive():
        async for kind, p in orchestrator._drive_phase(
                "analyst", counted, gate, "s", "first", lambda d: f"fix:{d}"):
            if kind == "result":
                out["result"] = p
    asyncio.run(drive())
    return calls, out["result"]


def test_drive_phase_hard_limit_fail_fast():
    from claude_agent_sdk import RateLimitInfo
    async def run_one(prompt, n):
        return sdk_runner.TurnResult("", 0.1, True, 429,
                                     rate_limit=RateLimitInfo(status="rejected", resets_at=999))
    def gate(slug):
        raise AssertionError("硬上限不該走到閘門")
    calls, result = _run_drive(run_one, gate)
    assert calls["n"] == 1, "硬上限只跑一次,不重試"
    assert result["ok"] is False and result["reason"] == "usage-limit" and result["resets_at"] == 999


def test_drive_phase_transient_backoff_then_fail():
    old = config.BACKOFF_BASE
    config.BACKOFF_BASE = 0.0                      # 免真的睡
    try:
        async def run_one(prompt, n):
            return sdk_runner.TurnResult("", 0.0, True, 529)
        def gate(slug):
            raise AssertionError("容量失敗不該走閘門")
        calls, result = _run_drive(run_one, gate)
        assert calls["n"] == config.TRANSIENT_MAX_RETRIES + 1, "退避 N 次後放棄"
        assert result["ok"] is False and result["reason"] == "usage-limit"
    finally:
        config.BACKOFF_BASE = old


def test_drive_phase_content_retry_then_pass():
    async def run_one(prompt, n):
        return sdk_runner.TurnResult("ok", 0.0, False, None)
    seq = {1: (False, "bad json"), 2: (True, "")}
    state = {"g": 0}
    def gate(slug):
        state["g"] += 1
        return seq[state["g"]]
    calls, result = _run_drive(run_one, gate)
    assert calls["n"] == 2, "第一次閘門失敗 → 修正 prompt 重派 → 第二次過"
    assert result["ok"] is True


def _tmp_story(slug: str):
    """在臨時 STORIES 下建一個帶 source.md 的故事目錄;回 (restore_fn, dir)。"""
    import tempfile, pathlib
    from server import critique  # noqa: F401 —— 確保 config 已載入
    old = config.STORIES
    tmp = pathlib.Path(tempfile.mkdtemp())
    config.STORIES = tmp
    d = tmp / slug
    d.mkdir()
    (d / "source.md").write_text("使用者的心血", encoding="utf-8")
    (d / "analysis.json").write_text("{}", encoding="utf-8")

    def restore():
        import shutil
        config.STORIES = old
        shutil.rmtree(tmp, ignore_errors=True)
    return restore, d


def test_cancel_preserves_nonfresh_story():
    """非 fresh 的 Run 取消,絕不刪既有故事(source.md 是無版控退路的心血)。"""
    from server import critique
    restore, d = _tmp_story("s01")
    try:
        run = critique.Run("s01", "既有故事")          # 預設非 fresh
        critique._discard_story(run)
        assert d.exists(), "非 fresh 取消不該刪故事目錄"
        assert (d / "source.md").exists(), "source.md 絕不能被取消刪掉"
    finally:
        restore()


def test_drive_phase_gate_exhausted_carries_reason():
    """內容閘門重試耗盡的 result 也要帶 reason 鍵(與硬上限路徑對稱),
    免得上層把兩種 result 一律處理時誤路由。"""
    async def run_one(prompt, n):
        return sdk_runner.TurnResult("ok", 0.0, False, None)
    def gate(slug):
        return (False, "永遠壞")                       # 每次都失敗 → 耗盡重試
    calls, result = _run_drive(run_one, gate)
    assert result["ok"] is False
    assert "reason" in result, "耗盡路徑的 result 缺 reason 鍵(與硬上限不對稱)"


def test_cancel_discards_fresh_story():
    """fresh(新孕育)Run 中途取消,該清掉剛 ingest 的孤兒(維持誕生流程的預期收尾)。"""
    from server import critique
    restore, d = _tmp_story("s01")
    try:
        run = critique.Run("s01", "孕育中", fresh=True)
        critique._discard_story(run)
        assert not d.exists(), "fresh 取消該清掉孤兒故事目錄"
    finally:
        restore()


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
