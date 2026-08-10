"""零成本回歸 canary(不燒訂閱):守住加固後不會無聲退回舊行為。
跑法(repo 根):  server/.venv/bin/python -m pytest
"""
import asyncio

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
    assert opt.hooks is sdk_runner._CRITIQUE_GUARD_HOOKS, \
        "analyst 要掛帶得到寫入根的那份閘門,否則寫不出 analysis.json"


# ── 路徑白名單硬閘門 ──────────────────────────────────────────────
# 這支閘門是唯一擋住「代理被 source.md 注入騎劫後亂讀亂寫」的東西,
# 而它在 2026-08-10 之前零測試:把 _within 的 any 改成 all、或把 fail-closed
# 改成 fail-open,整套測試照樣全綠。以下釘住它的每一條分支。

def _guard_of(opt):
    """取出實際掛在這份 options 上的 PreToolUse 閘門。
    刻意不直接抓 sdk_runner 裡的函式 —— 要測的是「這個 client 拿到的是哪一份閘門」,
    接錯線跟邏輯寫錯一樣會出事,而前者只有從 options 這頭看得見。"""
    return opt.hooks["PreToolUse"][0].hooks[0]


def _ask(guard, tool, path=None, key="file_path"):
    ti = {} if path is None else {key: path}
    return asyncio.run(guard({"tool_name": tool, "tool_input": ti}, "tu", None))


def _denied(res):
    return res.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_guard_write_roots_allow_stories_only():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _ask(g, "Write", str(config.STORIES / "s99" / "analysis.json")) == {}, \
        "analyst 寫自己的產物必須放行——擋掉這條 critique 全鏈當場死"
    assert _denied(_ask(g, "Write", "/tmp/x.py")), "stories/ 外不得寫"
    assert _denied(_ask(g, "Write", str(config.ROOT / "server" / "config.py"))), "不得寫 repo 自己的 code"
    assert _denied(_ask(g, "Write", str(config.STORIES / ".." / "server" / "config.py"))), \
        "`..` 逃逸必須被 resolve() 攤平後擋下"


def test_guard_read_roots_allow_stories_and_schemas():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _ask(g, "Read", str(config.ROOT / "schemas" / "analysis.schema.json")) == {}
    assert _ask(g, "Read", str(config.STORIES / "s99" / "source.md")) == {}
    assert _denied(_ask(g, "Read", "/etc/passwd")), "讀也要鎖——不然注入就能撈機密"
    assert _denied(_ask(g, "Write", str(config.ROOT / "schemas" / "analysis.schema.json"))), \
        "schemas/ 唯讀:讀得到不代表寫得進"


def test_guard_ignores_non_file_tools():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _ask(g, "WebSearch") == {}, "非檔案工具不歸這支閘門管,直接放行"


def test_guard_is_fail_closed():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _denied(_ask(g, "Write", "")), "空路徑不是「沒指定所以算了」,是擋"
    assert _denied(_ask(g, "Write", "\x00")), "路徑解析爆炸要 fail-closed,不能因例外而放行"


def test_guard_resolves_relative_against_root():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _ask(g, "Write", "stories/s99/analysis.json") == {}, "相對路徑以 repo 根為基準"
    assert _denied(_ask(g, "Write", "server/config.py"))


def test_guard_checks_alternate_path_keys():
    g = _guard_of(sdk_runner.agent_options("analyst"))
    assert _denied(_ask(g, "NotebookEdit", "/tmp/x.ipynb", key="notebook_path")), \
        "notebook_path 也要看,不能因為換個欄位名就繞過去"


_READONLY = (("discuss", sdk_runner.discuss_options),
             ("settle", sdk_runner.settle_options))


def test_readonly_clients_cannot_write_anywhere():
    """discuss/settle/align 宣稱唯讀,那就不該有任何寫入根。

    在此之前它們與 analyst 共用 `_WRITE_ROOTS=[STORIES]` —— 寫 /tmp 被擋,
    寫 stories/ 卻會放行,而唯讀這件事只剩 `allowed_tools=["Read"]` 一層在守。
    #18 的 log(唯讀 client 吐出 Write、一路走到這支 hook)正是在懷疑那一層。
    """
    for name, mk in _READONLY:
        g = _guard_of(mk())
        assert _denied(_ask(g, "Write", str(config.STORIES / "s99" / "analysis.json"))), \
            f"{name} 不得寫 analysis.json:那是觀察層正本,只有 analyst 寫"
        assert _denied(_ask(g, "Write", str(config.STORIES / "s99" / "conclusions.jsonl"))), \
            f"{name} 不得直接寫結論正本:四道閘門長在 conclusions.py,繞過去等於沒有閘門"
        assert _denied(_ask(g, "Edit", str(config.STORIES / "s99" / "source.md"))), \
            f"{name} 不得改使用者的創作"


def test_readonly_clients_can_still_read():
    """收緊寫入不能誤傷讀:討論要讀原文、跨篇地圖、命中篇的 analysis。"""
    for name, mk in _READONLY:
        g = _guard_of(mk())
        assert _ask(g, "Read", str(config.STORIES / "s99" / "source.md")) == {}, f"{name} 要讀原文"
        assert _ask(g, "Read", str(config.STORIES / "label-map.json")) == {}, f"{name} 要讀跨篇地圖"
        assert _denied(_ask(g, "Read", "/etc/passwd")), f"{name} 讀仍然鎖在白名單內"


def test_readonly_deny_reason_never_promises_write_access():
    """被擋的那一方接下來會說什麼——#18 買過單的那條。

    共用理由寫著「僅允許讀寫 stories/」,對唯讀 client 是假話:它剛被擋的正是
    stories/ 內的檔。給模型一句自相矛盾的理由,它只會換條路再試或編個下台階。
    """
    g = _guard_of(sdk_runner.discuss_options())
    res = _ask(g, "Write", str(config.STORIES / "s99" / "analysis.json"))
    reason = res["hookSpecificOutput"]["permissionDecisionReason"]
    assert "僅允許讀寫" not in reason, "不能告訴唯讀 client 它可以寫 stories/"
    assert "唯讀" in reason, "要講明它是唯讀的,好讓它照『有據』那條說出『我做不到』"


def test_readonly_options_shape():
    """對稱 test_agent_options_shape。

    在此之前只有 analyst 那支有 shape 測試,於是「討論唯讀」這句話在測試層
    一個字都沒被守著——把 discuss_options 的 allowed_tools 加回 "Write",
    或把 hooks 換回帶寫入根的那份,整套測試照樣全綠。
    """
    for name, mk in _READONLY:
        opt = mk()
        assert opt.allowed_tools == ["Read"], f"{name} 只該拿到 Read"
        assert opt.hooks is sdk_runner._READONLY_GUARD_HOOKS, \
            f"{name} 掛錯閘門就等於拿到 analyst 的寫入根"


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


