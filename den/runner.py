"""Claude CLI 工人:隔離配方、env 白名單、stdin 送 prompt、行程群組取消。

不用 --bare(吃不到訂閱且沉默)。log 只記 event=key=value,不記 prompt / 輸出。
"""
import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Mapping

from den import config
from marrow.jsonout import extract_json

log = logging.getLogger("hyenovel")

_AUTH_MSG = "Claude CLI 未登入：在終端機執行 claude 並 /login"


@dataclass(frozen=True)
class ClaudePreset:
    exe: str
    model: str = "sonnet"
    runner_name = "claude-cli"


@dataclass
class RunResult:
    outcome: str  # ok|transient|usage-limit|auth|crash|timeout|cancelled
    parsed: dict | None
    raw: str
    model: str | None
    tokens: dict | None
    duration_ms: int
    message: str | None
    num_turns: int | None = None
    text: str | None = None  # 模型的原始文字輸出(CLI 的 result);parsed 抽不出時拿它當修補的 previous


def build_argv(preset: ClaudePreset, system_prompt_file: Path, schema: dict) -> list[str]:
    # 不帶 --json-schema:CLI 會在內部自己驗格式、自己重試(smoke:一次 num_turns=4、13 萬
    # output tokens),那段我們的閘門與 log 都看不到。schema 已附在 system prompt,JSON 由我們
    # 解析(marrow.jsonout)、閘門驗,格式錯誤也成為一筆看得見的 attempt。schema 參數保留不用。
    return [preset.exe, "-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
            "--no-session-persistence", "--output-format", "json",
            "--model", preset.model,
            "--system-prompt-file", str(system_prompt_file)]


def build_chat_argv(preset: ClaudePreset, system_prompt_file: Path) -> list[str]:
    # 同 build_argv 的隔離配方,只換成 stream-json 逐字串流
    return [preset.exe, "-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
            "--no-session-persistence", "--output-format", "stream-json",
            "--include-partial-messages", "--verbose",
            "--model", preset.model,
            "--system-prompt-file", str(system_prompt_file)]


def worker_env(env: Mapping[str, str]) -> dict[str, str]:
    out = {k: env[k] for k in config.ENV_WHITELIST if k in env}
    out["MAX_THINKING_TOKENS"] = "0"
    return out


def classify(rc: int, stdout: str) -> tuple[str, dict | None, str | None]:
    try:
        obj = json.loads(stdout)
    except ValueError:
        obj = None
    if not isinstance(obj, dict):
        return "crash", None, f"CLI 輸出不是 JSON 物件 (rc={rc})"
    status = obj.get("api_error_status")
    text = obj.get("result") if isinstance(obj.get("result"), str) else ""
    if status == 429:
        return "usage-limit", obj, "用量已達上限"
    if status in (500, 529):
        return "transient", obj, f"API 暫時錯誤 ({status})"
    # 文字判斷只在 is_error 時用:成功時 result 是模型輸出的 JSON 文字,可能逐字含使用者原文
    if status == 401 or (obj.get("is_error") and ("/login" in text or "Not logged in" in text)):
        return "auth", obj, _AUTH_MSG
    if obj.get("is_error"):
        return "crash", obj, f"CLI 回報錯誤 subtype={obj.get('subtype')}"
    if not isinstance(obj.get("result"), str):
        return "crash", obj, "CLI 輸出沒有 result 文字"
    return "ok", obj, None


def explain(outcome: str, obj: dict | None, err: str, msg: str | None) -> str | None:
    """crash/auth 的訊息補上病因尾巴:非 JSON → stderr 末 300 字;is_error → result 文字。

    只進 attempt / job detail,絕不進 log(可能夾帶使用者原文)。
    """
    if outcome not in ("crash", "auth"):
        return msg
    if obj is None:
        tail = err.strip()[-300:]
    elif obj.get("is_error") and isinstance(obj.get("result"), str):
        tail = obj["result"].strip()[-300:]
    else:
        tail = ""
    return f"{msg}：{tail}" if tail else msg


def make_result(outcome: str, obj: dict | None, raw: str, message: str | None,
                duration_ms: int) -> RunResult:
    model = tokens = parsed = turns = text = None
    if obj is not None:
        turns = obj.get("num_turns")
        usage = obj.get("usage")
        if isinstance(usage, dict):
            tokens = {"input": usage.get("input_tokens"),
                      "output": usage.get("output_tokens"),
                      "cache_read": usage.get("cache_read_input_tokens"),
                      "cache_creation": usage.get("cache_creation_input_tokens"),
                      "thinking": (usage.get("output_tokens_details") or {}).get("thinking_tokens"),
                      # 每個行程只跑一次,total_cost_usd 就是單次成本(非 SDK 的 client 累計值)
                      "cost_usd": obj.get("total_cost_usd")}
        mu = obj.get("modelUsage")
        if isinstance(mu, dict) and mu:
            model = next(iter(mu))
        if outcome == "ok":
            text = obj["result"]
            parsed = extract_json(text)              # 可能 None:由流水線當閘門失敗處理
    return RunResult(outcome, parsed, raw, model, tokens, duration_ms, message, turns, text)


def kill_tree(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def run_job(preset: ClaudePreset, system_prompt: str, user_prompt: str, schema: dict,
                  *, timeout: float,
                  on_proc: Callable[[asyncio.subprocess.Process | None], None] | None = None
                  ) -> RunResult:
    """schema 不傳給 CLI(見 build_argv);保留在簽名上是因 RunFn 介面不變,非 CLI runner 與測試假體會用。

    ok 只代表工人正常結束且有 result 文字;parsed 可能是 None(抽不出 JSON 物件),由流水線處理。
    """
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "system.md"
        sp.write_text(system_prompt, encoding="utf-8")
        proc = await asyncio.create_subprocess_exec(
            *build_argv(preset, sp, schema),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=tmp, env=worker_env(os.environ),
            start_new_session=True)
        if on_proc:
            on_proc(proc)
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(user_prompt.encode()), timeout)
        except asyncio.TimeoutError:
            kill_tree(proc)
            await proc.wait()
            log.info("event=run_timeout timeout=%s", timeout)
            return RunResult("timeout", None, "", None, None, ms(), f"逾時 {timeout}s")
        except asyncio.CancelledError:
            kill_tree(proc)
            await proc.wait()
            log.info("event=run_cancelled")
            raise
        finally:
            if on_proc:
                on_proc(None)
        raw = out.decode("utf-8", "replace")
        outcome, obj, msg = classify(proc.returncode, raw)
        msg = explain(outcome, obj, err.decode("utf-8", "replace"), msg)
        log.info("event=run_done outcome=%s rc=%s ms=%s", outcome, proc.returncode, ms())
        return make_result(outcome, obj, raw, msg, ms())


async def stream_chat(preset: ClaudePreset, system_prompt: str, user_prompt: str,
                      *, timeout: float) -> AsyncIterator[tuple[str, str | RunResult]]:
    """逐個 yield ("delta", 文字),最後恰好一次 ("result", RunResult)。

    只認 text_delta(見 #13)。消費端中途 aclose / 取消 / 逾時,finally 一律殺整個行程群組。
    """
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "system.md"
        sp.write_text(system_prompt, encoding="utf-8")
        proc = await asyncio.create_subprocess_exec(
            *build_chat_argv(preset, sp),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=tmp, env=worker_env(os.environ),
            start_new_session=True, limit=1 << 24)
        err_task = asyncio.ensure_future(proc.stderr.read())
        result_line = ""
        timed_out = False
        try:
            proc.stdin.write(user_prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            deadline = t0 + timeout
            while True:
                try:
                    raw_line = await asyncio.wait_for(
                        proc.stdout.readline(), max(deadline - time.monotonic(), 0))
                except asyncio.TimeoutError:
                    timed_out = True
                    break
                if not raw_line:
                    break
                try:
                    ev = json.loads(raw_line)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("type") == "result":
                    result_line = raw_line.decode("utf-8", "replace")
                elif ev.get("type") == "stream_event":
                    inner = ev.get("event") or {}
                    delta = inner.get("delta") or {}
                    if (inner.get("type") == "content_block_delta"
                            and delta.get("type") == "text_delta"
                            and isinstance(delta.get("text"), str)):
                        yield "delta", delta["text"]
            if timed_out:
                kill_tree(proc)
            await proc.wait()
            err = (await err_task).decode("utf-8", "replace")
        finally:
            kill_tree(proc)
            await proc.wait()
            err_task.cancel()
        if timed_out:
            log.info("event=chat_done outcome=timeout rc=%s ms=%s", proc.returncode, ms())
            yield "result", RunResult("timeout", None, "", None, None, ms(), f"逾時 {timeout}s")
            return
        outcome, obj, msg = classify(proc.returncode, result_line)
        msg = explain(outcome, obj, err, msg)
        log.info("event=chat_done outcome=%s rc=%s ms=%s", outcome, proc.returncode, ms())
        res = make_result(outcome, obj, result_line, msg, ms())
        res.parsed = None                            # 聊天輸出是自由文字,不抽 JSON
        yield "result", res


def cli_version(exe: str) -> str | None:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        return r.stdout.split()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def find_claude() -> str | None:
    return shutil.which("claude")


def pick_runner(client_name: str | None, available: tuple[str, ...]) -> str | None:
    """clientInfo 對得到且可用就用它;否則照 RUNNER_ORDER 取第一個可用;都沒有 → None。"""
    name = (client_name or "").lower()
    for key, runner in config.CLIENT_RUNNERS.items():
        if key in name and runner in available:
            return runner
    return next((r for r in config.RUNNER_ORDER if r in available), None)
