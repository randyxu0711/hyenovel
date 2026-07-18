"""零成本回歸 canary(不燒訂閱):守住加固後不會無聲退回舊行為。
跑法(repo 根):  server/.venv/bin/python -m pytest
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


def test_extract_text_rejects_oversize():
    """上傳超過上限的檔案該被擋(避免 read 巨檔 / docx zip bomb 撐爆記憶體)。"""
    from server import ingest
    big = b"x" * (config.MAX_UPLOAD_BYTES + 1)
    try:
        ingest.extract_text("a.txt", big)
        assert False, "過大檔案應拒"
    except ValueError:
        pass
    assert ingest.extract_text("a.txt", b"hello").strip() == "hello"   # 界內照常


def test_create_story_rejects_oversize():
    """直接 POST /api/stories 的 create 路徑也要有上限(否則繞過 extract 的讀取上限,
    把巨量 text 寫進 source.md)。且拒絕時不可留半成品目錄。"""
    from server import ingest
    import tempfile, pathlib, shutil
    old = config.STORIES
    tmp = pathlib.Path(tempfile.mkdtemp())
    config.STORIES = tmp
    try:
        big = "x" * (config.MAX_UPLOAD_BYTES + 1)
        try:
            ingest.create_story("t", big)
            assert False, "過長故事應拒"
        except ValueError:
            pass
        assert not any(tmp.iterdir()), "拒絕時不該建立任何故事目錄"
    finally:
        config.STORIES = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_create_story_retries_on_slug_collision():
    """並發/重送下 next_slug 可能回到已被搶走的 slug;mkdir 當原子佔位,撞了要進位重試,
    不該讓 FileExistsError 冒成 500。"""
    from server import ingest
    import tempfile, pathlib, shutil
    old_stories, old_next = config.STORIES, ingest.next_slug
    tmp = pathlib.Path(tempfile.mkdtemp())
    config.STORIES = tmp
    (tmp / "s01").mkdir()                       # s01 已被另一請求搶先建好
    seq = iter(["s01", "s02"])                  # next_slug 先回撞號 s01、再回 s02
    ingest.next_slug = lambda: next(seq)
    try:
        slug = ingest.create_story("t", "內文")
        assert slug == "s02", "撞號後應進位到 s02"
        assert (tmp / "s02" / "source.md").exists()
    finally:
        config.STORIES, ingest.next_slug = old_stories, old_next
        shutil.rmtree(tmp, ignore_errors=True)


def test_run_py_enforces_timeout():
    """確定性層子行程(render/viz/index/gate)要有逾時,卡死的子行程不能讓 Run 永遠 running。"""
    import subprocess
    from server import orchestrator
    try:
        orchestrator._run_py(["-c", "import time; time.sleep(5)"], timeout=0.3)
        assert False, "超時應拋 TimeoutExpired"
    except subprocess.TimeoutExpired:
        pass


def test_extract_text_bad_pdf_friendly_error():
    """壞/加密的 pdf·docx 要轉成友善 ValueError(app 層 →4xx),不讓 pypdf/docx 例外冒成 500。"""
    from server import ingest
    try:
        ingest.extract_text("broken.pdf", b"%PDF-1.4 this is not a real pdf at all")
        assert False, "壞 pdf 應拒"
    except ValueError:
        pass


def test_phase_error_shapes():
    """analyst/criticizer 共用的錯誤事件產生器:usage-limit 帶 resets_at+recoverable,
    泛用閘門失敗帶對應 gate 名詞、不可恢復。"""
    from server import orchestrator
    ul = orchestrator._phase_error("analyst", "analysis",
                                   {"ok": False, "reason": "usage-limit", "resets_at": 42}, cost=0.3)
    assert ul["event"] == "error"
    d = ul["data"]
    assert d["where"] == "analyst" and d["reason"] == "usage-limit"
    assert d["resets_at"] == 42 and d["recoverable"] is True
    assert d["cost_usd"] == 0.3, "錯誤事件也要帶已花成本(F3)"
    gen = orchestrator._phase_error("criticizer", "feedback", {"ok": False}, cost=0.8)
    assert gen["data"]["where"] == "criticizer"
    assert gen["data"]["message"] == "feedback 閘門重試後仍未過"
    assert gen["data"]["recoverable"] is False
    assert gen["data"]["cost_usd"] == 0.8, "criticizer 失敗要含累計成本(含 analyst)"


def test_record_captures_cost_on_error():
    """失敗收場的 Run 也該記下已花的錢(原本只有 done 事件會設 run.cost)。"""
    from server import critique
    run = critique.Run("s01", "t")
    critique._record(run, {"event": "error",
                           "data": {"where": "analyst", "message": "x", "cost_usd": 0.42}})
    assert run.cost == 0.42, "error 事件帶的成本該被記到 run.cost"


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


