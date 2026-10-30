"""den.mcp 行為契約:五個 tool、clientInfo 帶給 den、錯誤一律 ToolError、提示只附一次、stdout 乾淨。

den 端是 test_client 的 FakeDen(in-process TestClient,Run() 立即放行);絕不 spawn 真 den / 真 claude,
data dir 一律 tmp_path。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp_types import Implementation

from den import mcp as den_mcp
from den.config import MAX_SOURCE_BYTES
from den.tests.test_app import Run
from den.tests.test_client import FakeDen
from marrow import db, repo

_REPO = Path(__file__).resolve().parent.parent.parent
TEXT = "她把信摺好。窗外的雨停了。\n\n她沒有寄出去。\n"


@pytest.fixture
def den(data):
    d = FakeDen(data)
    yield d
    d.stop()


def _call(client, name, args, **kw):
    async def go():
        async with Client(den_mcp.build_server(client),
                          client_info=Implementation(name="claude-code", version="2.1.312"),
                          **kw) as c:
            return await c.call_tool(name, args)
    return anyio.run(go)


def _text(r):
    return r.content[0].text


def _conn(den):
    return db.connect(den.url)


def _story_count(den):
    c = _conn(den)
    try:
        return c.execute("SELECT COUNT(*) FROM story").fetchone()[0]
    finally:
        c.close()


def _job_params(den, jid):
    c = _conn(den)
    try:
        return repo.get_job(c, jid)["params"]
    finally:
        c.close()


def _make_job(den, state, error_class=None):
    """直接用 repo 造一個 mini 的 job 並設狀態。先起 den:startup 會把 running 收成 crash、
    worker 啟動時會撿 queued;起好之後才建的列,沒有 submit/resume 叫醒 worker 就沒人碰。"""
    if den.tc is None:
        den.start()
    c = _conn(den)
    try:
        with c:
            st = repo.story_by_slug(c, "mini")
            sv = repo.latest_source_version(c, st["id"])
            jid = repo.create_job(c, "critique", st["id"], sv["id"], {}, time.time())
            repo.set_job_state(c, jid, state, time.time(), error_class=error_class)
        return jid
    finally:
        c.close()


def _write(tmp_path, name="a.md", text=TEXT, enc="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(enc))
    return p


# ── tools ──

def test_tools_listed(den):
    async def go():
        async with Client(den_mcp.build_server(den.client())) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert anyio.run(go) == {"submit_work", "talk_to_companion", "find_works", "read_work", "cancel_work"}
    assert den.spawns == 0   # 列 tool 不碰 den


def test_den_unavailable_is_tool_error(den):
    def spawn():
        (den.dir / "den.log").write_text("boot\nRuntimeError: 找不到 claude CLI\n", encoding="utf-8")
    r = _call(den.client(spawn=spawn, spawn_wait=0.3), "find_works", {})
    assert r.is_error and "RuntimeError: 找不到 claude CLI" in _text(r)


def test_notices_appended_once(den):
    c = den.client()
    c.notices.append("提示一條")
    first = _text(_call(c, "find_works", {}))
    second = _text(_call(c, "find_works", {}))
    assert first.rstrip().endswith("提示一條")
    assert "提示一條" not in second


def test_notices_appended_to_errors(den):
    c = den.client()
    c.notices.append("提示一條")
    r = _call(c, "read_work", {"work": "nope", "part": "source"})
    assert r.is_error and _text(r).rstrip().endswith("提示一條")


def test_client_name_truncated(den, tmp_path):
    async def go():
        async with Client(den_mcp.build_server(den.client()),
                          client_info=Implementation(name="x" * 200, version="1")) as c:
            return await c.call_tool("submit_work", {"path": str(_write(tmp_path))})
    r = anyio.run(go)
    assert not r.is_error
    assert json.loads(_last_job(den)["params"])["client"]["name"] == "x" * 64


# ── 入口 ──

def test_main_keeps_stdout_clean(tmp_path):
    """真 client 會開著 stdin:一問一答地送,收到回覆才送下一則(一次寫完再關 stdin,
    server 可能先看到 EOF 就退出,tools/list 沒回 → 偶發失敗)。"""
    env = {**os.environ, "HYENOVEL_DATA_DIR": str(tmp_path)}
    p = subprocess.Popen([sys.executable, "-m", "den.mcp"], cwd=_REPO, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True)
    lines: queue.Queue = queue.Queue()
    reader = threading.Thread(target=lambda: [lines.put(ln) for ln in p.stdout], daemon=True)
    reader.start()
    seen: list[str] = []

    def send(msg):
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()

    def reply(mid):
        end = time.monotonic() + 60
        while time.monotonic() < end:
            try:
                ln = lines.get(timeout=max(0.0, end - time.monotonic()))
            except queue.Empty:
                break
            if ln.strip():
                seen.append(ln)
                msg = json.loads(ln)          # 每一行都得是 JSON
                if msg.get("id") == mid:
                    return msg
        raise AssertionError(f"等不到 id={mid} 的回覆;收到 {seen!r}")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "0"}}})
        reply(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = reply(2)
        p.stdin.close()
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    reader.join(timeout=10)                   # 讀完管線,尾巴的行才進得了 queue
    for ln in lines.queue:                    # 收尾後殘留的也得是 JSON
        if ln.strip():
            json.loads(ln)
    assert len(listed["result"]["tools"]) == 5
    assert not (tmp_path / "den.json").exists()   # 沒拉起 den


# ── talk_to_companion ──

@pytest.fixture
def cden(data):
    from den.tests.test_app_discuss import FakeChat
    d = FakeDen(data, chat=FakeChat())
    yield d
    d.stop()


def _session(client, calls, between=None):
    """同一個 MCP 連線(= 同一個 shim 行程狀態)連續呼叫;between(i) 在第 i 次之後跑。"""
    async def go():
        out = []
        async with Client(den_mcp.build_server(client),
                          client_info=Implementation(name="claude-code", version="2.1.314")) as c:
            for i, (name, args) in enumerate(calls):
                out.append(await c.call_tool(name, args))
                if between:
                    between(i)
        return out
    return anyio.run(go)


def _discussions(den):
    c = _conn(den)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM discussion")]
    finally:
        c.close()


def _utterance_count(den):
    c = _conn(den)
    try:
        return c.execute("SELECT COUNT(*) FROM utterance").fetchone()[0]
    finally:
        c.close()


def test_talk_returns_companion_text_and_reuses_session(cden):
    r1, r2 = _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                                       ("talk_to_companion", {"message": "結尾呢", "work": "mini"})])
    assert not r1.is_error and _text(r1).startswith("AB")
    assert len(_discussions(cden)) == 1 and _utterance_count(cden) == 3   # 開場 1 + 一來一回 2


def test_talk_without_work_uses_last_story(cden):
    r1, r2 = _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                                       ("talk_to_companion", {"message": "嗯"})])
    assert not r2.is_error and len(_discussions(cden)) == 1


def test_resolve_none_falls_back_to_den_recent(cden):
    r = _call(cden.client(), "talk_to_companion", {"message": "嗨"})   # 新 shim、沒聊過
    assert not r.is_error and ("POST", "/discuss/mini") in cden.paths


def test_talk_without_any_work_is_tool_error(tmp_path):
    from den.tests.test_app_discuss import FakeChat
    url = f"sqlite:///{tmp_path}/t.db"
    c = db.connect(url)
    db.migrate(c, tmp_path / "t.db")
    c.close()
    d = FakeDen((url, tmp_path), chat=FakeChat())
    try:
        r = _call(d.client(), "talk_to_companion", {"message": "嗨"})
        assert r.is_error and "還沒有任何作品" in _text(r) and "檔案路徑" in _text(r)
        assert not any(p.startswith("/discuss") for _, p in d.paths)
    finally:
        d.stop()


def test_talk_work_by_title_keyword(cden):
    _add_story(cden, "d07", "海的另一邊", "她走到岸邊。")
    r = _call(cden.client(), "talk_to_companion", {"work": "海"})
    assert not r.is_error and ("POST", "/discuss/d07") in cden.paths


def test_talk_bad_mode_rejected_locally(cden):
    r = _call(cden.client(), "talk_to_companion", {"work": "mini", "mode": "doubt"})
    assert r.is_error and "direct(直說)" in _text(r)
    assert not any(p.startswith("/discuss") for _, p in cden.paths)


def test_talk_records_home_mcp_and_client_name(cden):
    _call(cden.client(), "talk_to_companion", {"work": "mini", "mode": "direct"})
    (d,) = _discussions(cden)
    assert (d["home"], d["client"]) == ("mcp", "claude-code")
    assert "你的讀法:直說" in cden.chat.calls[-1][0]


def test_talk_worker_error_tells_host_to_report_failure(cden):
    cden.chat.outcome = "usage-limit"
    r = _call(cden.client(), "talk_to_companion", {"work": "mini"})
    assert r.is_error and "用量已達上限" in _text(r) and "照實告訴作者" in _text(r)


def test_talk_busy_is_tool_error(cden):
    import types

    def jam(i):
        sid = _discussions(cden)[0]["external_id"]
        cden.tc.app.state.chat_locks[f"mini/{sid}"] = types.SimpleNamespace(locked=lambda: True)
    _, r = _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                                     ("talk_to_companion", {"message": "再來"})], between=jam)
    assert r.is_error and "上一輪還在跑" in _text(r)
    assert len(cden.chat.calls) == 1


def test_talk_unknown_session_starts_fresh(cden):
    def wipe(i):
        if i:
            return
        c = _conn(cden)
        with c:
            c.execute("DELETE FROM utterance")
            c.execute("DELETE FROM discussion")
        c.close()
    _, r = _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                                     ("talk_to_companion", {"message": "還在嗎"})], between=wipe)
    assert not r.is_error and len(_discussions(cden)) == 1 and _utterance_count(cden) == 2


def test_talk_survives_den_restart(cden):
    def restart(i):
        cden.stop()
        cden.start()
    _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                             ("talk_to_companion", {"message": "繼續"})], between=restart)
    assert len(_discussions(cden)) == 1 and _utterance_count(cden) == 3


def test_talk_unknown_slug(cden):
    r = _call(cden.client(), "talk_to_companion", {"work": "nope"})
    assert r.is_error and "找不到「nope」這篇" in _text(r)


def test_server_instructions_lead_with_verbatim_relay(den):
    async def go():
        async with Client(den_mcp.build_server(den.client())) as c:
            return c.instructions
    text = anyio.run(go)
    assert text.startswith("talk_to_companion 回傳的是") and "一字不改" in text
    assert len(text) <= 4096


def test_talk_first_turn_double_call_runs_one_worker(cden):
    """首輪還沒有局 id,den 的鎖擋不到:shim 自己擋,免得兩個工人、付兩次錢。"""
    cden.chat.hang = True

    async def go():
        async with Client(den_mcp.build_server(cden.client()),
                          client_info=Implementation(name="claude-code", version="2.1.314")) as c:
            out = {}
            async with anyio.create_task_group() as tg:
                async def first():
                    out["a"] = await c.call_tool("talk_to_companion", {"work": "mini"})
                tg.start_soon(first)
                await anyio.to_thread.run_sync(cden.chat.started.wait, 5)
                out["b"] = await c.call_tool("talk_to_companion", {"work": "mini"})
                cden.chat.release.set()
            return out
    out = anyio.run(go)
    assert out["b"].is_error and "上一輪還在跑" in _text(out["b"]) and "照實告訴作者" in _text(out["b"])
    assert not out["a"].is_error and len(cden.chat.calls) == 1


def test_talk_rejections_tell_host_to_report(cden):
    r = _call(cden.client(), "talk_to_companion", {"work": "nope"})
    assert "照實告訴作者" in _text(r)


def test_talk_oversize_message_rejected_locally(cden):
    from den.config import MAX_CHAT_CHARS
    r = _call(cden.client(), "talk_to_companion", {"work": "mini", "message": "字" * (MAX_CHAT_CHARS + 1)})
    assert r.is_error and "字字字字" not in _text(r)
    assert not any(p.startswith("/discuss") for _, p in cden.paths)


# ── 作品:find_works / read_work / 解析 ──

def _add_story(den, slug, title, text, now=50.0):
    c = _conn(den)
    try:
        with c:
            sid = repo.ensure_story(c, slug, title, now)
            repo.add_source_version(c, sid, text, now)
    finally:
        c.close()


def _list_tools(den):
    async def go():
        async with Client(den_mcp.build_server(den.client())) as c:
            return (await c.list_tools()).tools
    return anyio.run(go)


def test_resolve_ambiguous_lists_candidates(cden):
    _add_story(cden, "d01", "海的另一邊", "她走到岸邊。")
    _add_story(cden, "d02", "海邊的豆花", "早上。")
    r = _call(cden.client(), "talk_to_companion", {"work": "海"})
    t = _text(r)
    assert r.is_error and "有 2 篇符合「海」,請問作者是哪一篇:\n〈" in t
    assert "〈海的另一邊〉" in t and "〈海邊的豆花〉" in t
    assert not any(p.startswith("/discuss") for _, p in cden.paths)


def test_resolve_not_found(cden):
    r = _call(cden.client(), "read_work", {"work": "不存在的", "part": "source"})
    assert r.is_error and "找不到「不存在的」這篇" in _text(r) and "find_works" in _text(r)


def test_find_works_lists_state(den):
    _add_story(den, "d01", "海", "她走到岸邊。")
    t = _text(_call(den.client(), "find_works", {}))
    lines = t.splitlines()
    assert lines[0].startswith("〈海〉開頭「她走到岸邊。」· 沒有分析 · 還沒聊過")
    assert any(l.startswith("〈") and "分析好了" in l for l in lines)


def test_find_works_query_and_empty(den):
    _add_story(den, "d01", "海", "她走到岸邊。")
    assert _text(_call(den.client(), "find_works", {"query": "海"})).count("〈") == 1
    assert _text(_call(den.client(), "find_works", {"query": "沒有這種"})) == "沒有符合「沒有這種」的作品。"


def test_read_work_parts(den):
    src = _text(_call(den.client(), "read_work", {"work": "mini", "part": "source"}))
    assert "第 1 版原文" in src
    r = _call(den.client(), "read_work", {"work": "mini", "part": "feedback"})
    assert r.is_error and "沒有舊版客觀回饋" in _text(r)
    _add_story(den, "d01", "海", "x")
    r = _call(den.client(), "read_work", {"work": "d01", "part": "analysis"})
    assert r.is_error and _text(r).endswith("〈海〉還沒有分析。")


def test_read_work_bad_part_local_reject(den):
    r = _call(den.client(), "read_work", {"work": "mini", "part": "notes"})
    assert r.is_error and "source" in _text(r)
    assert den.paths == []


def test_readonly_annotations(den):
    tools = {t.name: t for t in _list_tools(den)}
    assert tools["find_works"].annotations.read_only_hint is True
    assert tools["read_work"].annotations.read_only_hint is True


# ── submit_work / cancel_work ──

def _last_job(den):
    c = _conn(den)
    try:
        return dict(c.execute("SELECT * FROM job ORDER BY id DESC LIMIT 1").fetchone())
    finally:
        c.close()


def _job_count(den):
    c = _conn(den)
    try:
        return c.execute("SELECT COUNT(*) FROM job").fetchone()[0]
    finally:
        c.close()


def test_submit_happy(den, tmp_path):
    r = _call(den.client(), "submit_work", {"path": str(_write(tmp_path))})
    assert not r.is_error
    t = _text(r)
    assert "作品〈a〉" in t and "分析已開始" in t and "第一次跑" in t and "訂閱額度" in t
    assert t.splitlines()[-1].startswith("分析在背景跑,不用等")
    assert "job" not in t and "d01" not in t                     # 不叫作者記編號
    assert json.loads(_last_job(den)["params"])["client"]["name"] == "claude-code"


def test_submit_legacy_era_client_info(den, tmp_path):
    r = _call(den.client(), "submit_work", {"path": str(_write(tmp_path))}, mode="legacy")
    assert not r.is_error and json.loads(_last_job(den)["params"])["client"]["name"] == "claude-code"


def test_submit_reports_name_mtime_chars(den, tmp_path):
    p = _write(tmp_path, "海.md", "她走。\n\n  海很冷。\n")
    ts = time.mktime((2026, 10, 30, 14, 2, 0, 0, 0, -1))
    os.utime(p, (ts, ts))
    first = _text(_call(den.client(), "submit_work", {"path": str(p)})).splitlines()[0]
    assert first == "收到 海.md(10/30 14:02 修改,7 字),作品〈海〉。"


def test_submit_expands_home(den, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(tmp_path)
    assert not _call(den.client(), "submit_work", {"path": "~/a.md"}).is_error


def test_submit_big5_with_title(den, tmp_path):
    p = _write(tmp_path, "b.txt", "他走進門。屋裡沒有人。燈還亮著。\n", enc="big5")
    r = _call(den.client(), "submit_work", {"path": str(p), "title": "門"})
    assert not r.is_error and "作品〈門〉" in _text(r)
    c = _conn(den)
    try:
        st = repo.story_by_slug(c, "d01")
        assert st["title"] == "門"
        assert repo.latest_source_version(c, st["id"])["text"] == "他走進門。屋裡沒有人。燈還亮著。\n"
    finally:
        c.close()


@pytest.mark.parametrize("make, want", [
    (lambda d: d / "nope.md", "找不到"),
    (lambda d: (d / "dir.md").mkdir() or d / "dir.md", "不是檔案"),
    (lambda d: _write(d, "a.pdf"), ".txt"),
    (lambda d: _write(d, "e.md", "  \n\n"), "空的"),
    (lambda d: _write(d, "big.TXT", "字" * (MAX_SOURCE_BYTES // 3 + 1)), "上限"),
], ids=["missing", "directory", "pdf", "empty", "oversize"])
def test_submit_rejects(den, tmp_path, make, want):
    before = _story_count(den)
    r = _call(den.client(), "submit_work", {"path": str(make(tmp_path))})
    assert r.is_error and want in _text(r)
    assert _story_count(den) == before


def test_submit_same_file_twice_reuses(den, tmp_path):
    p = str(_write(tmp_path))
    c = den.client()
    _call(c, "submit_work", {"path": p})
    second = _text(_call(c, "submit_work", {"path": p}))
    assert "沿用那篇" in second and _story_count(den) == 2   # mini + d01


def test_submit_revision_keeps_title(den, tmp_path):
    c = den.client()
    _call(c, "submit_work", {"path": str(_write(tmp_path, "海.md", "第一版。"))})
    r = _call(c, "submit_work", {"path": str(_write(tmp_path, "海-v2.md", "第二版。")), "work": "海"})
    assert not r.is_error and "作品〈海〉" in _text(r)
    conn = _conn(den)
    try:
        st = repo.story_by_slug(conn, "d01")
        assert st["title"] == "海" and repo.latest_source_version(conn, st["id"])["n"] == 2
    finally:
        conn.close()
    assert _story_count(den) == 2


def test_submit_twice_while_inflight_no_second_job(data, tmp_path):
    d = FakeDen(data, run=Run(released=False))
    try:
        p = str(_write(tmp_path))
        c = d.client()
        _call(c, "submit_work", {"path": p})
        t = _text(_call(c, "submit_work", {"path": p}))
        assert "已經在分析中,沒有再開一次" in t and "分析已開始" not in t
        assert _job_count(d) == 1
    finally:
        d.run.release.set()
        d.stop()


@pytest.mark.parametrize("state, cls, why", [
    ("paused", "usage-limit", "上次停在:訂閱額度用完"),
    ("cancelled", None, "上次是你取消的"),
    ("failed", None, "上次沒有跑完"),
], ids=["paused-usage-limit", "cancelled", "failed-no-class"])
def test_submit_same_version_after_stop_resumes(den, tmp_path, state, cls, why):
    p = str(_write(tmp_path))
    c = den.client()
    _call(c, "submit_work", {"path": p})
    jid = _last_job(den)["id"]
    conn = _conn(den)
    try:
        for _ in range(500):   # 假分析的引文對不上 → 閘門耗盡 → paused;worker 就此閒下
            if repo.get_job(conn, jid)["state"] == "paused":
                break
            time.sleep(0.02)
        with conn:
            repo.set_job_state(conn, jid, state, time.time(), error_class=cls)
    finally:
        conn.close()
    t = _text(_call(c, "submit_work", {"path": p}))
    assert "這一版之前跑到一半,已接續(已完成的步驟不重跑)。" in t and why in t
    assert "分析已開始" not in t and _job_count(den) == 1


def test_submit_without_path_after_done_says_ready(den):
    r = _call(den.client(), "submit_work", {"work": "mini"})
    assert r.is_error and "最新一版已經分析好了,不用再跑" in _text(r)
    assert _job_count(den) == 0


def test_submit_without_path_never_ran(den):
    _add_story(den, "d01", "海", "x")
    r = _call(den.client(), "submit_work", {"work": "海"})
    assert r.is_error and "〈海〉最新一版還沒開始分析" in _text(r) and _job_count(den) == 0


def test_submit_without_path_resumes_paused(den):
    jid = _make_job(den, "paused", "usage-limit")
    r = _call(den.client(), "submit_work", {"work": "mini"})
    assert not r.is_error and "已接著上次停下的地方續跑" in _text(r)
    assert _job_count(den) == 1 and _last_job(den)["id"] == jid


def test_cancel_work_running_and_idle(data, tmp_path):
    d = FakeDen(data, run=Run(released=False))
    try:
        c = d.client()
        _call(c, "submit_work", {"path": str(_write(tmp_path))})
        r = _call(c, "cancel_work", {})
        assert not r.is_error and "〈a〉的分析已停下" in _text(r)
        r = _call(c, "cancel_work", {"work": "mini"})
        assert r.is_error and "現在沒有在分析" in _text(r)
    finally:
        d.run.release.set()
        d.stop()


def test_write_tools_not_readonly(den):
    tools = {t.name: t for t in _list_tools(den)}
    for name in ("submit_work", "cancel_work", "talk_to_companion"):
        a = tools[name].annotations
        assert not (a and a.read_only_hint)


# ── prompts / instructions ──

def _prompts(den):
    async def go():
        async with Client(den_mcp.build_server(den.client())) as c:
            listed = (await c.list_prompts()).prompts
            got = {p.name: await c.get_prompt(p.name) for p in listed}
            return listed, got
    return anyio.run(go)


def test_prompts_listed_without_arguments(den):
    listed, _ = _prompts(den)
    assert {p.name for p in listed} == {"companion", "continue"}
    assert all(not p.arguments for p in listed)
    assert den.spawns == 0


def test_prompt_texts(den):
    _, got = _prompts(den)
    comp = got["companion"].messages[0].content.text
    cont = got["continue"].messages[0].content.text
    assert "submit_work" in comp and "talk_to_companion" in comp and "一字不改" in comp
    assert "talk_to_companion" in cont and "一字不改" in cont


def test_instructions_name_new_tools_only():
    t = den_mcp.INSTRUCTIONS
    assert t.startswith("talk_to_companion 回傳的是陪讀角色 companion 對作者說的話") and len(t) <= 4096
    assert all(n in t for n in ("submit_work", "find_works", "read_work", "cancel_work"))
    assert "start_critique" not in t and "critique_status" not in t


def test_resolve_full_title_reachable_despite_longer_titles(cden):
    _add_story(cden, "d01", "海", "她走到岸邊。")
    _add_story(cden, "d02", "海-v2", "x")
    r = _call(cden.client(), "talk_to_companion", {"work": "海"})
    assert not r.is_error and ("POST", "/discuss/d01") in cden.paths


def test_talk_after_submit_targets_submitted_work(cden, tmp_path):
    _session(cden.client(), [("talk_to_companion", {"work": "mini"}),
                             ("submit_work", {"path": str(_write(tmp_path, "海.md", "海很冷。"))}),
                             ("talk_to_companion", {})])
    assert ("POST", "/discuss/d01") in cden.paths


def test_cancel_after_resume_targets_resumed_work(data, tmp_path):
    from den.tests.test_app_discuss import FakeChat
    d = FakeDen(data, run=Run(released=False), chat=FakeChat())
    try:
        _session(d.client(), [("talk_to_companion", {"work": "mini"}),
                              ("submit_work", {"path": str(_write(tmp_path, "海.md", "海很冷。"))}),
                              ("cancel_work", {})])
        assert ("POST", "/works/d01/cancel") in d.paths
    finally:
        d.run.release.set()
        d.stop()


_MINI_SRC = (_REPO / "tests" / "fixtures" / "mini" / "source.md").read_text(encoding="utf-8")


def test_submit_unchanged_analyzed_file_does_not_rerun(den, tmp_path):
    p = _write(tmp_path, "燈.md", _MINI_SRC)          # mini 這版已分析好
    r = _call(den.client(), "submit_work", {"path": str(p)})
    t = _text(r)
    assert not r.is_error and "沿用那篇" in t and "已經分析好了,沒有重跑" in t
    assert "分析已開始" not in t and "分析在背景跑" not in t and _job_count(den) == 0


def test_submit_unchanged_never_analyzed_file_starts(den, tmp_path):
    _add_story(den, "d01", "海", TEXT)                 # 有這版原文、從沒跑過分析
    r = _call(den.client(), "submit_work", {"path": str(_write(tmp_path))})
    assert not r.is_error and "分析已開始" in _text(r) and _job_count(den) == 1
