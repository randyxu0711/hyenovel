"""orchestrator 的行為契約 —— 我們的政策,不是 SDK 的行為。

_phase_with_retry / _run_py 都注入假的 → 全程不碰 ClaudeSDKClient、不燒訂閱。
沿用既有 canary 的模式:同步 test 函式 + asyncio.run。
"""
import asyncio
import json
import subprocess

import pytest

from server import config, orchestrator


def _drain(slug):
    async def go():
        return [ev async for ev in orchestrator.run_critique(slug)]
    return asyncio.run(go())


@pytest.fixture
def story(tmp_path, monkeypatch):
    d = tmp_path / "stories" / "s01"
    d.mkdir(parents=True)
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    monkeypatch.setattr(config, "STORIES", tmp_path / "stories")
    return "s01"


def _fake_phase(ok=True, cost=0.5, reason=None):
    """假的 _phase_with_retry:不派工,直接回結果。"""
    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        yield "event", {"event": "phase", "data": {"name": name, "status": "start"}}
        res = {"ok": ok, "cost": cost}
        if not ok:
            res["reason"] = reason
            res["resets_at"] = 1234567890
        yield "result", res
    return phase


def _fake_run_py(returncode=0, stdout="", stderr=""):
    def run_py(args, timeout=None):
        return subprocess.CompletedProcess(args=args, returncode=returncode,
                                           stdout=stdout, stderr=stderr)
    return run_py


# ── _gate_feedback:那個曾讓 criticizer「空過」的坑 ────────────────────

def test_gate_feedback_blocks_when_file_absent(story, monkeypatch):
    """criticizer 沒真的寫檔 → 必須擋。

    共用閘門(viz.py --check)視 feedback.json 為可選,所以它會「空過」——
    orchestrator 會誤判成功、渲染出無回饋的結果還回報 done。
    _gate_feedback 就是為了補這個洞:先確認檔案真的存在。
    """
    called = {"gate": False}

    def should_not_run(slug):
        called["gate"] = True
        return True, ""

    monkeypatch.setattr(orchestrator, "_gate", should_not_run)

    ok, detail = orchestrator._gate_feedback(story)
    assert ok is False, "feedback.json 不存在竟然放行"
    assert "feedback.json" in detail
    assert called["gate"] is False, "檔案都沒有了,不該還去跑共用閘門"


def test_gate_feedback_delegates_when_file_exists(story, monkeypatch):
    (config.STORIES / story / "feedback.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(orchestrator, "_gate", lambda slug: (True, "ok"))

    ok, detail = orchestrator._gate_feedback(story)
    assert ok is True and detail == "ok"


def test_gate_returns_false_on_nonzero_exit(monkeypatch):
    """viz.py --check 非零離開 → 閘門沒過,明細帶回去給 agent 修。"""
    monkeypatch.setattr(orchestrator, "_run_py",
                        _fake_run_py(returncode=1, stdout="⚠ 引用閘門:2 條 quote 找不到"))
    ok, detail = orchestrator._gate("s01")
    assert ok is False
    assert "引用閘門" in detail


# ── 守門:縱深防禦 ────────────────────────────────────────────────────

def test_invalid_slug_is_rejected():
    """slug 會拼路徑、也會當 argv 餵子行程 → 非法就擋,不得走到派工。"""
    events = _drain("../etc/passwd")
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["where"] == "input"
    assert events[0]["data"]["recoverable"] is False


def test_missing_source_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORIES", tmp_path / "stories")
    (tmp_path / "stories").mkdir(exist_ok=True)  # 下方 autouse _stories fixture 可能已建過
    events = _drain("s01")
    assert events[0]["event"] == "error"
    assert events[0]["data"]["where"] == "input"
    assert "source.md" in events[0]["data"]["message"]


# ── happy path ───────────────────────────────────────────────────────

def test_happy_path_emits_done_with_cost_and_artifacts(story, monkeypatch):
    monkeypatch.setattr(orchestrator, "_phase_with_retry", _fake_phase(ok=True, cost=0.4))
    monkeypatch.setattr(orchestrator, "_run_py", _fake_run_py(returncode=0))

    events = _drain(story)
    done = events[-1]
    assert done["event"] == "done"
    assert done["data"]["ok"] is True
    assert done["data"]["cost_usd"] == pytest.approx(0.8)      # analyst 0.4 + criticizer 0.4
    assert "viz.json" in done["data"]["artifacts"]


def test_criticizer_uses_the_stricter_gate(story, monkeypatch):
    """analyst 用 _gate、criticizer 必須用 _gate_feedback(不可兩格共用寬鬆閘門)。"""
    gates = []

    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        gates.append((name, gate_fn))
        yield "result", {"ok": True, "cost": 0.1}

    monkeypatch.setattr(orchestrator, "_phase_with_retry", phase)
    monkeypatch.setattr(orchestrator, "_run_py", _fake_run_py(returncode=0))
    _drain(story)

    by_name = dict(gates)
    assert by_name["criticizer"] is orchestrator._gate_feedback


# ── 早出 viz:讓孕育動畫畫得出真骨 ───────────────────────────────────

def test_preview_viz_runs_between_analyst_and_criticizer(story, monkeypatch):
    """analyst 交件後就先產一版 viz.json —— 孕育動畫靠它畫真骨:階段詞「長出骨架」
    說的那一刻,骨架真的已經在磁碟上。必須落在 criticizer **之前**,否則等於白等一整格
    (criticizer 是分鐘級的),那條敘事就沒了。"""
    calls = []

    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        calls.append(f"phase:{name}")
        yield "result", {"ok": True, "cost": 0.1}

    def run_py(args, timeout=None):
        calls.append(args[0].rsplit("/", 1)[-1])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(orchestrator, "_phase_with_retry", phase)
    monkeypatch.setattr(orchestrator, "_run_py", run_py)
    _drain(story)

    assert "viz.py" in calls, f"analyst 之後沒產早出 viz:{calls}"
    assert calls.index("viz.py") < calls.index("phase:criticizer"), \
        f"早出 viz 必須在 criticizer 之前,實際順序:{calls}"


def test_preview_viz_failure_does_not_abort_the_run(story, monkeypatch):
    """早出 viz 只餵動畫 → best-effort。它壞了不得砍掉一格已經花掉 ~$0.4 的 analyst;
    真正的 viz 在確定性層還會再跑一次,那次失敗才該讓整支紅。"""
    n = {"i": 0}

    def run_py(args, timeout=None):
        n["i"] += 1
        rc = 1 if n["i"] == 1 else 0        # 第一次 = 早出 viz,讓它失敗;其餘照常
        return subprocess.CompletedProcess(args=args, returncode=rc, stdout="炸了", stderr="")

    monkeypatch.setattr(orchestrator, "_phase_with_retry", _fake_phase(ok=True, cost=0.4))
    monkeypatch.setattr(orchestrator, "_run_py", run_py)

    events = _drain(story)
    assert events[-1]["event"] == "done", "早出 viz 失敗竟然中斷整支"
    preview = [e for e in events if e["event"] == "phase" and e["data"]["name"] == "preview"]
    assert preview[-1]["data"]["status"] == "skip", "失敗的早出 viz 不該回報 ok"


def test_preview_viz_exception_does_not_abort_the_run(story, monkeypatch):
    """早出 viz 拋例外(逾時/子行程炸)同樣只降級——外層的 except 會把它冒成 sdk error,
    那就等於預覽壞掉害整支紅。"""
    n = {"i": 0}

    def run_py(args, timeout=None):
        n["i"] += 1
        if n["i"] == 1:
            raise subprocess.TimeoutExpired(cmd=args, timeout=1)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(orchestrator, "_phase_with_retry", _fake_phase(ok=True, cost=0.4))
    monkeypatch.setattr(orchestrator, "_run_py", run_py)

    events = _drain(story)
    assert events[-1]["event"] == "done", "早出 viz 拋例外竟然中斷整支"


def test_no_preview_viz_when_analyst_fails(story, monkeypatch):
    """analyst 沒交件就沒有 analysis.json,早出 viz 無事可做(跑了只會噴錯)。"""
    calls = []

    def run_py(args, timeout=None):
        calls.append(args[0])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(orchestrator, "_phase_with_retry",
                        _fake_phase(ok=False, cost=0.3, reason="usage-limit"))
    monkeypatch.setattr(orchestrator, "_run_py", run_py)
    _drain(story)

    assert calls == [], f"analyst 失敗卻還跑了子行程:{calls}"


# ── 確定性層段的失敗分流 ─────────────────────────────────────────────

def test_deterministic_layer_nonzero_returncode_is_error(story, monkeypatch):
    """render/viz/index 任一 returncode != 0 → error(不得默默當成功)。"""
    monkeypatch.setattr(orchestrator, "_phase_with_retry", _fake_phase(ok=True))
    monkeypatch.setattr(orchestrator, "_run_py",
                        _fake_run_py(returncode=1, stderr="引用閘門擋下"))

    err = _drain(story)[-1]
    assert err["event"] == "error"
    assert err["data"]["where"] == "render"
    assert "引用閘門擋下" in err["data"]["message"]


def test_deterministic_layer_timeout_is_error(story, monkeypatch):
    """子行程卡死 → error,不得讓 Run 永遠 running。"""
    def boom(args, timeout=None):
        raise subprocess.TimeoutExpired(cmd=args, timeout=config.SUBPROCESS_TIMEOUT)

    monkeypatch.setattr(orchestrator, "_phase_with_retry", _fake_phase(ok=True))
    monkeypatch.setattr(orchestrator, "_run_py", boom)

    err = _drain(story)[-1]
    assert err["event"] == "error"
    assert err["data"]["reason"] == "timeout"
    assert err["data"]["where"] == "render"


# ── 失敗路徑:成本不得消失、階段不得標錯 ─────────────────────────────

def test_failed_phase_still_reports_cost(story, monkeypatch):
    """撞用量上限 → 可恢復 + 帶 resets_at + 照實回報已花的錢(F3)。"""
    monkeypatch.setattr(orchestrator, "_phase_with_retry",
                        _fake_phase(ok=False, cost=0.3, reason="usage-limit"))

    err = _drain(story)[-1]
    assert err["event"] == "error"
    assert err["data"]["where"] == "analyst"
    assert err["data"]["cost_usd"] == pytest.approx(0.3)
    assert err["data"]["recoverable"] is True
    assert err["data"]["reason"] == "usage-limit"
    assert err["data"]["resets_at"] == 1234567890


def test_gate_exhaustion_is_not_recoverable(story, monkeypatch):
    """閘門重試耗盡 → 不可恢復(跟撞用量上限不同,重跑也沒用)。"""
    monkeypatch.setattr(orchestrator, "_phase_with_retry",
                        _fake_phase(ok=False, cost=0.2, reason="gate"))

    err = _drain(story)[-1]
    assert err["data"]["recoverable"] is False
    assert "閘門" in err["data"]["message"]


def test_cost_accumulates_across_phases_on_late_failure(story, monkeypatch):
    """analyst 成功、criticizer 失敗 → 回報的是兩格的總花費,不是只有失敗那格。"""
    calls = {"n": 0}

    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield "result", {"ok": True, "cost": 0.4}
        else:
            yield "result", {"ok": False, "cost": 0.3, "reason": "gate"}

    monkeypatch.setattr(orchestrator, "_phase_with_retry", phase)

    err = _drain(story)[-1]
    assert err["data"]["where"] == "criticizer"
    assert err["data"]["cost_usd"] == pytest.approx(0.7), "analyst 花掉的錢不見了"


def test_timeout_labels_the_right_phase(story, monkeypatch):
    """第二格逾時要說 criticizer —— 原本一律說「分析階段」,報錯會誤導。"""
    calls = {"n": 0}

    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield "result", {"ok": True, "cost": 0.4}
            return
        raise asyncio.TimeoutError()

    monkeypatch.setattr(orchestrator, "_phase_with_retry", phase)

    err = _drain(story)[-1]
    assert err["event"] == "error"
    assert err["data"]["where"] == "timeout"
    assert "criticizer" in err["data"]["message"], "逾時標錯階段"
    assert err["data"]["cost_usd"] == pytest.approx(0.4), "逾時也要回報已花的錢"


def test_unexpected_exception_is_classified(story, monkeypatch):
    """SDK 意外爆炸 → 收斂成 error 事件並分類死因,不讓 Task 默默死掉。"""
    async def phase(name, first_prompt, retry_prompt, slug, gate_fn=None, on_client=None):
        raise RuntimeError("Stream closed at sendRequest")
        yield

    monkeypatch.setattr(orchestrator, "_phase_with_retry", phase)

    err = _drain(story)[-1]
    assert err["event"] == "error"
    assert err["data"]["where"] == "sdk"
    assert err["data"]["reason"] == "usage-limit"      # classify_failure 認得這個訊息


# ── 續跑:跳過已完成格(閘門確認)─────────────────────────────────────

@pytest.fixture(autouse=True)
def _stories(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORIES", tmp_path / "stories")
    # exist_ok:同檔另有測試也會自建同一個 tmp_path/"stories"(各自 monkeypatch 同一路徑),
    # autouse 先跑一步不該跟它們搶著建目錄而炸 FileExistsError。
    (tmp_path / "stories").mkdir(exist_ok=True)
    yield


def _story_with_analysis(slug="s01"):
    d = config.STORIES / slug
    d.mkdir(parents=True)
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    (d / "analysis.json").write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    return d


def test_resume_skips_analyst_when_analysis_good(monkeypatch):
    """analysis.json 完整 → 續跑不重跑 analyst(不再燒那 $0.4)。"""
    d = _story_with_analysis()

    calls = {"analyst": 0, "criticizer": 0}

    async def fake_phase(name, *a, **k):
        calls[name] += 1
        yield ("event", {"event": "phase", "data": {"name": name, "status": "ok", "attempt": 0}})
        yield ("result", {"ok": True, "cost": 0.3, "reason": None})

    monkeypatch.setattr(orchestrator, "_phase_with_retry", fake_phase)
    # 完整閘門確認:analysis 通過、render 子行程都當成功
    monkeypatch.setattr(orchestrator, "_gate", lambda slug: (True, ""))
    monkeypatch.setattr(orchestrator, "_gate_feedback", lambda slug: (True, ""))
    monkeypatch.setattr(orchestrator, "_run_py",
                        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})())

    async def go():
        events = [ev async for ev in orchestrator.run_critique("s01")]
        assert calls["analyst"] == 0, "analysis 完整卻重跑了 analyst"
        assert calls["criticizer"] == 1
        assert any(e.get("event") == "phase" and e["data"].get("name") == "analyst"
                   and e["data"].get("status") == "ok" for e in events), "跳過仍要 emit analyst ok"

    asyncio.run(go())


def test_resume_reruns_analyst_when_gate_confirm_fails(monkeypatch):
    """analysis.json 看似在,但完整閘門確認不過 → 退回重跑 analyst。"""
    _story_with_analysis()
    calls = {"analyst": 0, "criticizer": 0}

    async def fake_phase(name, *a, **k):
        calls[name] += 1
        yield ("event", {"event": "phase", "data": {"name": name, "status": "ok", "attempt": 0}})
        yield ("result", {"ok": True, "cost": 0.3, "reason": None})

    monkeypatch.setattr(orchestrator, "_phase_with_retry", fake_phase)
    monkeypatch.setattr(orchestrator, "_gate", lambda slug: (False, "引用對不上"))   # 確認失敗
    monkeypatch.setattr(orchestrator, "_gate_feedback", lambda slug: (True, ""))
    monkeypatch.setattr(orchestrator, "_run_py",
                        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})())

    async def go():
        [ev async for ev in orchestrator.run_critique("s01")]
        assert calls["analyst"] == 1, "閘門確認不過就該重跑 analyst"

    asyncio.run(go())
