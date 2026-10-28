"""den.mcp 行為契約:五個 tool、clientInfo 帶給 den、錯誤一律 ToolError、提示只附一次、stdout 乾淨。

den 端是 test_client 的 FakeDen(in-process TestClient,Run() 立即放行);絕不 spawn 真 den / 真 claude,
data dir 一律 tmp_path。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp_types import Implementation

from den import mcp as den_mcp
from den.config import MAX_SOURCE_BYTES
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
    assert anyio.run(go) == {"start_critique", "critique_status", "cancel_critique",
                             "resume_critique", "open_discussion"}
    assert den.spawns == 0   # 列 tool 不碰 den


def _job_id(text):
    return int(text.split("job ")[1].split("(")[0])


def test_start_critique_happy(den, tmp_path):
    r = _call(den.client(), "start_critique", {"path": str(_write(tmp_path))})
    assert not r.is_error
    t = _text(r)
    assert "d01" in t and "claude" in t and "訂閱額度" in t
    assert "第一次跑" in t and "critique_status" in t
    assert _job_params(den, _job_id(t))["client"]["name"] == "claude-code"


def test_start_critique_legacy_era_client_info(den, tmp_path):
    r = _call(den.client(), "start_critique", {"path": str(_write(tmp_path))}, mode="legacy")
    assert not r.is_error
    assert _job_params(den, _job_id(_text(r)))["client"]["name"] == "claude-code"


def test_start_expands_home(den, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(tmp_path)
    r = _call(den.client(), "start_critique", {"path": "~/a.md"})
    assert not r.is_error and "d01" in _text(r)


def test_start_big5(den, tmp_path):
    p = _write(tmp_path, "b.txt", "他走進門。屋裡沒有人。燈還亮著。\n", enc="big5")
    r = _call(den.client(), "start_critique", {"path": str(p), "title": "門"})
    assert not r.is_error
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
def test_start_rejects(den, tmp_path, make, want):
    before = _story_count(den)
    r = _call(den.client(), "start_critique", {"path": str(make(tmp_path))})
    assert r.is_error and want in _text(r)
    assert _story_count(den) == before


def test_start_same_file_twice_reuses(den, tmp_path):
    p = str(_write(tmp_path))
    c = den.client()
    first, second = _call(c, "start_critique", {"path": p}), _call(c, "start_critique", {"path": p})
    assert "d01" in _text(first) and "d01" in _text(second) and "沿用" in _text(second)
    assert _story_count(den) == 2   # mini + d01


def test_start_unknown_slug_is_error(den, tmp_path):
    r = _call(den.client(), "start_critique", {"path": str(_write(tmp_path)), "slug": "d99"})
    assert r.is_error and "unknown slug" in _text(r)


def test_status_maps_states(den):
    c = den.client()
    cases = [(_make_job(den, "done"), ["完成", "open_discussion"], ["resume_critique"]),
             (_make_job(den, "paused", "usage-limit"), ["已暫停", "額度用完", "resume_critique"], []),
             (_make_job(den, "failed", "gate"), ["失敗", "引文閘門", "resume_critique"], []),
             (_make_job(den, "cancelled"), ["已取消", "resume_critique"], []),
             (_make_job(den, "queued"), ["排隊中"], ["resume_critique"])]
    for jid, has, lacks in cases:
        t = _text(_call(c, "critique_status", {"job_id": jid}))
        assert all(h in t for h in has), t
        assert not any(x in t for x in lacks), t


def test_status_running_step(den):
    jid = _make_job(den, "running")
    conn = _conn(den)
    with conn:
        repo.set_job_state(conn, jid, "running", time.time(), step="criticizer")
    conn.close()
    assert "分析中" in _text(_call(den.client(), "critique_status", {"job_id": _make_job(den, "running")}))
    assert "評論中" in _text(_call(den.client(), "critique_status", {"job_id": jid}))


def test_status_unknown_job(den):
    r = _call(den.client(), "critique_status", {"job_id": 999})
    assert r.is_error and "999" in _text(r)


def test_cancel_409_message(den):
    r = _call(den.client(), "cancel_critique", {"job_id": _make_job(den, "done")})
    assert r.is_error and "這個 job 目前不能取消" in _text(r)


def test_resume_409_message(den):
    r = _call(den.client(), "resume_critique", {"job_id": _make_job(den, "done")})
    assert r.is_error and "這個 job 目前不能續跑" in _text(r)


def test_resume_ok(den):
    r = _call(den.client(), "resume_critique", {"job_id": _make_job(den, "paused", "usage-limit")})
    assert not r.is_error and "critique_status" in _text(r)


def test_cancel_ok(den):
    r = _call(den.client(), "cancel_critique", {"job_id": _make_job(den, "queued")})
    assert not r.is_error and "已取消" in _text(r)


def test_open_discussion_ok(den):
    t = _text(_call(den.client(), "open_discussion", {"slug": "mini"}))
    assert "你是和作者來回討論的出版編輯" in t
    assert "他走進門。屋裡沒有人。" in t
    assert "不會被存成結論" in t
    assert "[k1] technique 物件擬人" in t and "k1 -produces-> e1" in t
    assert "原文已改稿" not in t


def test_open_discussion_not_analyzed(den):
    c = den.client()
    assert c.request("POST", "/stories", json={"text": TEXT}).json()["slug"] == "d01"
    r = _call(c, "open_discussion", {"slug": "d01"})
    assert r.is_error and "start_critique" in _text(r)


def test_open_discussion_unknown(den):
    r = _call(den.client(), "open_discussion", {"slug": "zz"})
    assert r.is_error and "zz" in _text(r)


def test_den_unavailable_is_tool_error(den):
    def spawn():
        (den.dir / "den.log").write_text("boot\nRuntimeError: 找不到 claude CLI\n", encoding="utf-8")
    r = _call(den.client(spawn=spawn, spawn_wait=0.3), "critique_status", {"job_id": 1})
    assert r.is_error and "RuntimeError: 找不到 claude CLI" in _text(r)


def test_notices_appended_once(den):
    c = den.client()
    c.notices.append("提示一條")
    first = _text(_call(c, "open_discussion", {"slug": "mini"}))
    second = _text(_call(c, "open_discussion", {"slug": "mini"}))
    assert first.rstrip().endswith("提示一條")
    assert "提示一條" not in second


def test_notices_appended_to_errors(den):
    c = den.client()
    c.notices.append("提示一條")
    r = _call(c, "critique_status", {"job_id": 999})
    assert r.is_error and _text(r).rstrip().endswith("提示一條")


def test_client_name_truncated(den, tmp_path):
    async def go():
        async with Client(den_mcp.build_server(den.client()),
                          client_info=Implementation(name="x" * 200, version="1")) as c:
            return await c.call_tool("start_critique", {"path": str(_write(tmp_path))})
    r = anyio.run(go)
    assert not r.is_error
    assert _job_params(den, _job_id(_text(r)))["client"]["name"] == "x" * 64


# ── render_discussion ──

def _ctx(**kw):
    base = {"slug": "s", "title": "題", "source": "原文。\n", "stale": False,
            "analysis": {"synopsis": None, "nodes": [], "edges": []},
            "feedback": None, "conclusions": []}
    return {**base, **kw}


def test_render_stale_and_feedback_and_conclusions():
    out = den_mcp.render_discussion(_ctx(
        stale=True,
        feedback={"read": "讀法", "one_line": "改一件事",
                  "strengths": [{"title": "S", "body": "SB", "refs": None, "quotes": ["QQQ"]}],
                  "key_points": [{"title": "K", "body": "KB", "refs": ["k1", "e1"],
                                  "quotes": ["PPP"]}],
                  "minor": ["枝節一"]},
        conclusions=[{"kind": "insight", "text": "結論文", "refs": ["t1"], "quotes": ["CQ"]},
                     {"kind": "open", "text": "沒錨", "refs": None, "quotes": None}]))
    assert "原文已改稿、分析是舊版的" in out
    assert "S / SB" in out and "K / KB / refs: k1, e1" in out and "枝節一" in out
    assert "(insight) 結論文 [t1]" in out and "(open) 沒錨" in out
    assert "QQQ" not in out and "PPP" not in out and "CQ" not in out


def test_open_discussion_within_budget():
    source = ("風" * 99 + "。") * 100   # 10,000 字
    nodes = [{"id": f"n{i}", "type": "motif", "label": f"標籤{i}",
              "note": "這個意象在全篇反覆出現,承擔了敘事者不肯說出口的那部分重量。" * 2,
              "intensity": None,
              "evidence": [{"quote": f"證據{i:02d}" + "引" * 46, "note": None}]}
             for i in range(60)]
    edges = [{"type": "relates_to", "from": f"n{i % 60}", "to": f"n{(i + 7) % 60}", "note": None}
             for i in range(80)]
    out = den_mcp.render_discussion(_ctx(source=source,
                                         analysis={"synopsis": "梗概", "nodes": nodes, "edges": edges}))
    print(f"\nrender_discussion budget chars={len(out)}", file=sys.stderr)
    assert len(out) < 50_000
    assert not any(n["evidence"][0]["quote"] in out for n in nodes)


# ── 入口 ──

def test_main_keeps_stdout_clean(tmp_path):
    env = {**os.environ, "HYENOVEL_DATA_DIR": str(tmp_path)}
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    p = subprocess.run([sys.executable, "-m", "den.mcp"], cwd=_REPO, env=env,
                       input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, timeout=60)
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    got = [json.loads(ln) for ln in lines]
    listed = next(m for m in got if m.get("id") == 2)
    assert len(listed["result"]["tools"]) == 5
    assert not (tmp_path / "den.json").exists()   # 沒拉起 den
