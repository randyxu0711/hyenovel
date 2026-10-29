"""den.mcp 行為契約:五個 tool、clientInfo 帶給 den、錯誤一律 ToolError、提示只附一次、stdout 乾淨。

den 端是 test_client 的 FakeDen(in-process TestClient,Run() 立即放行);絕不 spawn 真 den / 真 claude,
data dir 一律 tmp_path。
"""
import json
import logging
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


def test_start_twice_while_inflight_no_second_job(data, tmp_path):
    """第一個 job 還沒跑完就再送同一份 → 回同一個 job,說明沒有新花費。"""
    d = FakeDen(data, run=Run(released=False))
    try:
        p = str(_write(tmp_path))
        c = d.client()
        first = _job_id(_text(_call(c, "start_critique", {"path": p})))
        r = _call(c, "start_critique", {"path": p})
        assert not r.is_error
        t = _text(r)
        assert f"job {first}" in t and "已在分析" in t and "不會再花" in t
        assert "已送出" not in t
        conn = _conn(d)
        try:
            assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        d.run.release.set()
        d.stop()


@pytest.mark.parametrize("state, cls, why", [
    ("paused", "usage-limit", "上次停在:訂閱額度用完"),
    ("failed", "gate", "上次停在:引文閘門重試耗盡"),
    ("cancelled", None, "上次是你取消的"),
], ids=["paused-usage-limit", "failed-gate", "cancelled"])
def test_start_same_version_after_stop_resumes(den, tmp_path, state, cls, why):
    """同一份原文之前停在半路 → 接續那個 job、說出上次停在哪,不說「已送出」新 job。"""
    p = str(_write(tmp_path))
    c = den.client()
    first = _job_id(_text(_call(c, "start_critique", {"path": p})))
    conn = _conn(den)
    try:
        for _ in range(500):   # 假分析的引文對不上 TEXT → 閘門耗盡 → paused;worker 就此閒下
            if repo.get_job(conn, first)["state"] == "paused":
                break
            time.sleep(0.02)
        with conn:
            repo.set_job_state(conn, first, state, time.time(), error_class=cls)
    finally:
        conn.close()
    r = _call(c, "start_critique", {"path": p})
    assert not r.is_error
    t = _text(r)
    assert f"之前跑到一半(job {first}),已接續:已完成的步驟不重跑。" in t
    assert why in t
    assert f"critique_status job_id={first}" in t
    assert "已送出" not in t


def test_start_unknown_slug_is_error(den, tmp_path):
    r = _call(den.client(), "start_critique", {"path": str(_write(tmp_path)), "slug": "d99"})
    assert r.is_error and "unknown slug" in _text(r)


def test_status_maps_states(den):
    c = den.client()
    cases = [(_make_job(den, "done"), ["完成", 'open_discussion(slug="mini")'], ["resume_critique"]),
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


def test_status_without_id_lists_three_groups(den):
    done = _make_job(den, "done")
    paused = _make_job(den, "paused", "usage-limit")
    queued = _make_job(den, "queued")
    failed = _make_job(den, "failed", "gate")
    t = _text(_call(den.client(), "critique_status", {}))
    assert t.index("進行中") < t.index("可續跑") < t.index("最近完成")
    run_sec = t[t.index("進行中"):t.index("可續跑")]
    res_sec = t[t.index("可續跑"):t.index("最近完成")]
    done_sec = t[t.index("最近完成"):]
    assert f"job {queued} ·〈極小合成樣本〉(mini) · 排隊中" in run_sec
    assert f"job {paused} ·〈極小合成樣本〉(mini) · 已暫停(訂閱額度用完)" in res_sec
    assert f"job {failed} ·〈極小合成樣本〉(mini) · 失敗(引文閘門重試耗盡)" in res_sec
    assert "resume_critique(job_id=N)" in res_sec
    assert f"job {done} ·〈極小合成樣本〉(mini) · 完成" in done_sec
    assert den.paths[-1] == ("GET", "/jobs")


def test_status_list_uses_title_and_omits_empty_groups(den):
    c = den.client()
    assert c.request("POST", "/stories", json={"text": TEXT, "title": "信"}).json()["slug"] == "d01"
    conn = _conn(den)
    try:
        with conn:
            st = repo.story_by_slug(conn, "d01")
            sv = repo.latest_source_version(conn, st["id"])
            jid = repo.create_job(conn, "critique", st["id"], sv["id"], {}, time.time())
            repo.set_job_state(conn, jid, "done", time.time())
    finally:
        conn.close()
    t = _text(_call(c, "critique_status", {}))
    assert f"job {jid} ·〈信〉(d01) · 完成" in t
    assert "進行中" not in t and "可續跑" not in t and "resume_critique" not in t


def test_status_list_empty(den):
    t = _text(_call(den.client(), "critique_status", {}))
    assert "目前沒有任何分析紀錄" in t


def test_status_description_mentions_listing(den):
    async def go():
        async with Client(den_mcp.build_server(den.client())) as c:
            return {t.name: t.description for t in (await c.list_tools()).tools}
    assert "不帶 job_id 會列出最近的 job" in anyio.run(go)["critique_status"]


def test_status_unknown_job(den):
    r = _call(den.client(), "critique_status", {"job_id": 999})
    assert r.is_error and "999" in _text(r)


def test_cancel_409_message(den):
    r = _call(den.client(), "cancel_critique", {"job_id": _make_job(den, "done")})
    assert r.is_error and "這個 job 目前不能取消" in _text(r)


def test_resume_409_message(den):
    r = _call(den.client(), "resume_critique", {"job_id": _make_job(den, "done")})
    t = _text(r)
    assert r.is_error and "這個 job 目前不能續跑" in t
    assert "已結束" in t and "舊版原文" in t and "同一版已有別的 job 在跑或已完成" in t


def test_status_list_marks_stale_version(den):
    jid = _make_job(den, "paused", "usage-limit")
    conn = _conn(den)
    try:
        with conn:
            repo.add_source_version(conn, repo.story_by_slug(conn, "mini")["id"], "改過的稿。",
                                    time.time())
    finally:
        conn.close()
    t = _text(_call(den.client(), "critique_status", {}))
    assert f"job {jid} ·〈極小合成樣本〉(mini) · 已暫停(訂閱額度用完)" in t
    assert "舊版原文,不能續跑——改稿後請用 start_critique 跑新版" in t
    assert "resume_critique" not in t       # 組內只有舊版:不給續跑提示


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


def test_open_discussion_bad_slug_rejected_locally(den, caplog):
    with caplog.at_level(logging.INFO, logger="hyenovel"):
        r = _call(den.client(), "open_discussion", {"slug": "../x?y"})
    assert r.is_error and "slug" in _text(r) and "../x?y" in _text(r)
    assert "event=reject where=mcp reason=slug" in caplog.text
    assert den.paths == []   # 沒送到 den


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
                                  "quotes": ["PPP"], "question": "問作者", "experiment": "試試看"},
                                 {"title": "K2", "body": "KB2", "refs": None, "quotes": [],
                                  "question": None, "experiment": None}],
                  "minor": ["枝節一"]},
        conclusions=[{"kind": "insight", "text": "結論文", "refs": ["t1"], "quotes": ["CQ"]},
                     {"kind": "open", "text": "沒錨", "refs": None, "quotes": None}]))
    assert "原文已改稿、分析是舊版的" in out
    assert "S / SB" in out and "K / KB / refs: k1, e1" in out and "枝節一" in out
    assert "  提問:問作者" in out and "  實驗:試試看" in out
    assert out.count("提問:") == 1 and out.count("實驗:") == 1   # null 不出行
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
    point = {"title": "標題" * 5, "body": "正文說明。" * 40, "refs": ["n1", "n2"], "quotes": ["引"],
             "question": "想問作者的一個問題,開啟討論的第一步?" * 3,
             "experiment": "試著把這段刪掉、重讀一次,看看效果是否更好。" * 3}
    feedback = {"read": "讀法。" * 50, "one_line": "改一件事。" * 10,
                "strengths": [point] * 3, "key_points": [point] * 5, "minor": ["枝節。" * 10] * 5}
    out = den_mcp.render_discussion(_ctx(source=source, feedback=feedback,
                                         analysis={"synopsis": "梗概", "nodes": nodes, "edges": edges}))
    print(f"\nrender_discussion budget chars={len(out)}", file=sys.stderr)
    assert len(out) < 50_000
    assert not any(n["evidence"][0]["quote"] in out for n in nodes)
    assert out.count("提問:") == 8 and out.count("實驗:") == 8


# ── 入口 ──

def test_main_keeps_stdout_clean(tmp_path):
    """真 client 會開著 stdin:一問一答地送,收到回覆才送下一則(一次寫完再關 stdin,
    server 可能先看到 EOF 就退出,tools/list 沒回 → 偶發失敗)。"""
    env = {**os.environ, "HYENOVEL_DATA_DIR": str(tmp_path)}
    p = subprocess.Popen([sys.executable, "-m", "den.mcp"], cwd=_REPO, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(ln) for ln in p.stdout], daemon=True).start()
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
    for ln in lines.queue:                    # 收尾後殘留的也得是 JSON
        if ln.strip():
            json.loads(ln)
    assert len(listed["result"]["tools"]) == 5
    assert not (tmp_path / "den.json").exists()   # 沒拉起 den
