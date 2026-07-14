"""orchestrator 的行為契約 —— 我們的政策,不是 SDK 的行為。

_phase_with_retry / _run_py 都注入假的 → 全程不碰 ClaudeSDKClient、不燒訂閱。
沿用既有 canary 的模式:同步 test 函式 + asyncio.run。
"""
import asyncio
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
    (tmp_path / "stories").mkdir()
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
