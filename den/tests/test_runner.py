"""den.runner 行為契約。絕不 spawn 真 claude——用 tmp_path 裡的假執行檔。"""
import asyncio
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from den import runner
from den.runner import ClaudePreset

FIX = Path(__file__).resolve().parent / "fixtures"
OK = json.loads((FIX / "claude_ok.json").read_text())
SCHEMA = {"type": "object"}


@pytest.fixture
def fake(tmp_path):
    """回 set_mode(mode) -> 假 claude 路徑;同目錄放控制檔與輸出檔。"""
    exe = tmp_path / "claude"
    shutil.copy(FIX / "fake_claude.py", exe)
    shutil.copy(FIX / "claude_ok.json", tmp_path / "claude_ok.json")
    exe.chmod(0o755)

    def set_mode(mode):
        (tmp_path / "fake_mode").write_text(mode)
        return str(exe)

    return set_mode


def test_argv_recipe_locked():
    argv = runner.build_argv(ClaudePreset("/x/claude"), Path("/t/sys.md"), {"a": "中"})
    assert argv == ["/x/claude", "-p", "--safe-mode", "--tools", "",
                    "--strict-mcp-config", "--no-session-persistence",
                    "--output-format", "json", "--model", "sonnet",
                    "--system-prompt-file", "/t/sys.md",
                    "--json-schema", '{"a": "中"}']
    assert "--bare" not in argv


def test_worker_env_whitelist():
    env = runner.worker_env({
        "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "s", "CLAUDE_CODE_MESSAGING_SOCKET": "x",
        "ANTHROPIC_API_KEY": "k", "PATH": "/bin", "HOME": "/h", "FOO": "1"})
    assert not [k for k in env if k.startswith("CLAUDE")]
    assert "ANTHROPIC_API_KEY" not in env and "FOO" not in env
    assert env["PATH"] == "/bin" and env["HOME"] == "/h"
    assert env["MAX_THINKING_TOKENS"] == "0"


def test_classify_ok_fixture():
    outcome, obj, msg = runner.classify(0, json.dumps(OK))
    assert (outcome, msg) == ("ok", None)
    assert obj["structured_output"] == {"answer": 2}
    res = runner.make_result(outcome, obj, json.dumps(OK), msg, 5)
    assert res.model == "claude-haiku-5-5"
    assert res.tokens == {"input": 2, "output": 111, "cache_read": 0,
                          "cache_creation": 1186, "thinking": 58}
    assert res.parsed == {"answer": 2}


def _err(**kw):
    return json.dumps({**OK, **kw})


def test_classify_failures():
    assert runner.classify(1, "not json")[0] == "crash"
    assert "rc=1" in runner.classify(1, "not json")[2]
    assert runner.classify(0, "[1]")[0] == "crash"
    assert runner.classify(1, _err(is_error=True, api_error_status=429))[0] == "usage-limit"
    assert runner.classify(1, _err(is_error=True, api_error_status=529))[0] == "transient"
    assert runner.classify(1, _err(is_error=True, api_error_status=500))[0] == "transient"
    o, _, m = runner.classify(1, _err(is_error=True, api_error_status=401))
    assert o == "auth" and "/login" in m
    assert runner.classify(1, _err(is_error=True, result="Please run /login"))[0] == "auth"
    # 成功的 run:原文逐字含 "/login" 不可被誤判成 auth
    assert runner.classify(0, _err(is_error=False, result='{"q":"/login"}'))[0] == "ok"
    o, _, m = runner.classify(1, _err(is_error=True, subtype="error_max_turns"))
    assert o == "crash" and "error_max_turns" in m
    bad = {k: v for k, v in OK.items() if k != "structured_output"}
    o, _, m = runner.classify(0, json.dumps(bad))
    assert o == "crash" and m == "沒有結構化輸出"


def test_make_result_without_usage():
    res = runner.make_result("crash", None, "raw", "m", 3)
    assert res.model is None and res.tokens is None and res.parsed is None
    res = runner.make_result("crash", {"is_error": True}, "raw", "m", 3)
    assert res.model is None and res.tokens is None


def test_run_job_ok_stdin_and_isolated_cwd(fake, tmp_path):
    exe = fake("ok")
    seen_procs = []
    res = asyncio.run(runner.run_job(ClaudePreset(exe), "SYS", "用戶提示", SCHEMA,
                                     timeout=20, on_proc=seen_procs.append))
    assert res.outcome == "ok" and res.parsed == {"answer": 2}
    assert seen_procs[0] is not None and seen_procs[-1] is None
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert "--system-prompt-file" in seen["argv"]
    assert seen["stdin"] == "用戶提示"
    repo = Path(__file__).resolve().parents[2]
    assert seen["cwd"] not in (str(repo), str(tmp_path))
    assert not [k for k in seen["env"] if k.startswith("CLAUDE")]


def test_run_job_garbage_is_crash(fake):
    res = asyncio.run(runner.run_job(ClaudePreset(fake("garbage")), "S", "U", SCHEMA, timeout=20))
    assert res.outcome == "crash" and res.raw.strip() == "not json"


def _child_pid(tmp_path):
    p = tmp_path / "child.pid"
    return int(p.read_text()) if p.exists() and p.read_text() else None


def _dead(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # 被殺但未收的孫行程(僵屍)也算死
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z"
    except FileNotFoundError:
        return True


def test_timeout_kills_and_reports(fake, tmp_path):
    res = asyncio.run(runner.run_job(ClaudePreset(fake("sleep")), "S", "U", SCHEMA, timeout=2))
    assert res.outcome == "timeout"
    pid = _child_pid(tmp_path)
    assert pid and _dead(pid)


def test_cancel_kills_process_group(fake, tmp_path):
    exe = fake("sleep")

    async def drive():
        task = asyncio.create_task(runner.run_job(ClaudePreset(exe), "S", "U", SCHEMA, timeout=30))
        for _ in range(100):
            if _child_pid(tmp_path):
                break
            await asyncio.sleep(0.05)
        pid = _child_pid(tmp_path)
        assert pid
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        t0 = time.time()
        while time.time() - t0 < 0.5 and not _dead(pid):
            await asyncio.sleep(0.02)
        assert _dead(pid)

    asyncio.run(drive())


def test_kill_tree_swallows_missing():
    class P:
        pid = 2 ** 22 + 12345  # 不存在
    runner.kill_tree(P())


def test_cli_version(fake, tmp_path):
    v = tmp_path / "v"
    v.write_text("#!/bin/sh\necho '2.1.312 (Claude Code)'\n")
    v.chmod(0o755)
    assert runner.cli_version(str(v)) == "2.1.312"
    assert runner.cli_version(str(tmp_path / "nope")) is None


def test_find_claude(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/claude")
    assert runner.find_claude() == "/usr/bin/claude"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert runner.find_claude() is None
