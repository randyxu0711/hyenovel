"""critique.Run 的行為契約 —— 全是我們的政策,SDK 不知道也不管。

最重的一條:**F1 迴歸** —— 重跑既有故事失敗/取消時,
絕不能刪掉使用者「沒有版控退路」的 source.md(stories/ 不進版控)。
刪掉就是永久資料遺失。
"""
import asyncio
import json

import pytest

import runstate
from server import config, critique


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORIES", tmp_path / "stories")
    (tmp_path / "stories").mkdir()
    critique._runs.clear()
    yield
    critique._runs.clear()


def _mk_story(slug="s01"):
    d = config.STORIES / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    return d


def _fake_critique(events):
    async def run(slug, on_client=None):
        for ev in events:
            yield ev
    return run


# ── start():防重複派工(= 防雙倍燒錢)────────────────────────────────

def test_start_returns_existing_run_when_already_running(monkeypatch):
    """同一 slug 已在跑 → 回既有 Run。

    這條擋的是「前端重整 = 又送一次 POST = 又派一支 claude = 雙倍燒錢」。
    """
    _mk_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600)
        yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        a = critique.start("s01", "標題")
        b = critique.start("s01", "標題")          # 重整後又送一次
        assert a is b, "重送不該開第二個 Run(會雙倍燒錢)"
        a.task.cancel()
        try:
            await a.task
        except BaseException:
            pass

    asyncio.run(go())


def test_start_rejects_invalid_slug():
    """Run 只為合法 slug 存在 → run.dir 必在 STORIES 直下(刪檔才安全)。"""
    with pytest.raises(ValueError):
        critique.start("../etc", "壞東西")


def test_start_after_finish_creates_new_run(monkeypatch):
    """上一輪已結束 → 再跑要開新的 Run(不能沿用舊的已完成狀態)。"""
    _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.1}}]))

    async def go():
        a = critique.start("s01", "標題")
        await a.task
        b = critique.start("s01", "標題")
        assert b is not a, "已結束的 Run 不該被重用"
        await b.task

    asyncio.run(go())


# ── _record():step 單調、成本不消失 ─────────────────────────────────

def test_record_step_is_monotonic():
    """step 只進不退 —— 前端的生長動畫靠它,倒退會讓胚胎倒著長。"""
    run = critique.Run("s01", "標題")
    critique._record(run, {"event": "phase", "data": {"name": "criticizer", "status": "ok"}})
    assert run.step == 3
    critique._record(run, {"event": "phase", "data": {"name": "analyst", "status": "start"}})
    assert run.step == 3, "step 不該倒退"


def test_record_done_sets_final_state():
    run = critique.Run("s01", "標題")
    critique._record(run, {"event": "done", "data": {"ok": True, "cost_usd": 0.9}})
    assert run.status == "done"
    assert run.step == 4
    assert run.cost == pytest.approx(0.9)


def test_record_error_keeps_cost():
    """失敗也記已花的錢(F3)—— 不讓成本消失。"""
    run = critique.Run("s01", "標題")
    critique._record(run, {"event": "error", "data": {"message": "撞牆", "cost_usd": 0.42}})
    assert run.status == "error"
    assert run.cost == pytest.approx(0.42)


def test_record_error_does_not_overwrite_cancelled():
    """已標 cancelled → error 事件不得把它改回 error。"""
    run = critique.Run("s01", "標題")
    run.status = "cancelled"
    critique._record(run, {"event": "error", "data": {"message": "取消造成的連線錯誤"}})
    assert run.status == "cancelled"


def test_record_broadcasts_to_subscribers():
    run = critique.Run("s01", "標題")
    q: asyncio.Queue = asyncio.Queue()
    run.subscribers.add(q)
    ev = {"event": "phase", "data": {"name": "analyst", "status": "start"}}
    critique._record(run, ev)
    assert q.get_nowait() is ev


# ── _drive():取消語意 + 失敗誕生清理(F1 的家)──────────────────────

def test_drive_does_not_overwrite_cancelled_with_error(monkeypatch):
    """取消會先 disconnect client,使底層拋連線錯誤而非 CancelledError。
    已標 cancelled 就不准被覆蓋成 error(否則前端會顯示「失敗」而不是「已取消」)。
    """
    _mk_story()

    async def blows_up(slug, on_client=None):
        raise RuntimeError("Stream closed at sendRequest")
        yield

    monkeypatch.setattr(critique.orchestrator, "run_critique", blows_up)

    run = critique.Run("s01", "標題")
    run.status = "cancelled"
    asyncio.run(critique._drive(run))
    assert run.status == "cancelled", "cancelled 被覆蓋成 error 了"


def test_drive_converges_unexpected_exception_to_error(monkeypatch):
    """任何意外都收斂成 error 事件,不讓背景 Task 默默死掉。"""
    _mk_story()

    async def blows_up(slug, on_client=None):
        raise RuntimeError("完全沒想到的東西")
        yield

    monkeypatch.setattr(critique.orchestrator, "run_critique", blows_up)

    run = critique.Run("s01", "標題")
    asyncio.run(critique._drive(run))
    assert run.status == "error"
    assert any(e["event"] == "error" for e in run.events)


def test_failed_fresh_birth_is_kept_and_marked(monkeypatch):
    """新政策:fresh 誕生失敗 → 不再刪,改寫 run.json 成 failed(可續)。"""
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "閘門耗盡", "recoverable": False,
                                                  "reason": "gate", "cost_usd": 0.4}}]))
    run = critique.Run("s01", "標題", fresh=True)
    asyncio.run(critique._drive(run))
    assert d.exists(), "新政策:失敗不刪,留著給續跑"
    rs = runstate.read(d)
    assert rs["status"] == "failed" and rs["reason"] == "gate"


def test_paused_on_usage_limit(monkeypatch):
    """撞用量上限 → status=paused,帶 resets_at。"""
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "撞牆", "recoverable": True,
                                                  "reason": "usage-limit", "resets_at": 999}}]))
    run = critique.Run("s01", "標題", fresh=True)
    asyncio.run(critique._drive(run))
    rs = runstate.read(d)
    assert rs["status"] == "paused" and rs["resets_at"] == 999


def test_start_persists_running_with_title(monkeypatch):
    """start 立刻寫 run.json(status=running + title)—— 跨重連可見。"""
    d = _mk_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600); yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        run = critique.start("s01", "我的標題")
        rs = runstate.read(d)
        assert rs["status"] == "running" and rs["title"] == "我的標題"
        run.task.cancel()
        try:
            await run.task
        except BaseException:
            pass

    asyncio.run(go())


def test_scan_crashed_marks_orphan_running_as_failed(monkeypatch):
    """server 重啟:run.json 是 running 但 _runs 沒有它 → 標 failed/crash。"""
    d = _mk_story()
    runstate.write(d, status="running", stage="analyst", title="標題")
    critique._runs.clear()
    critique.scan_crashed()
    rs = runstate.read(d)
    assert rs["status"] == "failed" and rs["reason"] == "crash"


def test_done_writes_run_json_done(monkeypatch):
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.9}}]))
    run = critique.Run("s01", "標題", fresh=True)
    asyncio.run(critique._drive(run))
    rs = runstate.read(d)
    assert rs["status"] == "done" and rs["stage"] == "done"


def test_failed_rerun_of_existing_story_keeps_source(monkeypatch):
    """**F1 迴歸(這批最重的一條)**

    重跑既有故事失敗 → 絕不能刪 source.md。
    stories/ 不進版控 —— 使用者的故事沒有任何退路,刪掉就是永久資料遺失。
    """
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "閘門耗盡", "recoverable": False}}]))

    run = critique.Run("s01", "標題", fresh=False)      # 既有故事重跑,不是新孕育
    asyncio.run(critique._drive(run))

    assert d.exists(), "重跑失敗竟刪掉了整個故事目錄"
    assert (d / "source.md").exists(), "重跑失敗竟刪掉了使用者無版控退路的 source.md"


def test_successful_fresh_birth_is_kept(monkeypatch):
    """fresh 但成功 → 當然不能刪(只有 error 才清)。"""
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.5}}]))

    run = critique.Run("s01", "標題", fresh=True)
    asyncio.run(critique._drive(run))
    assert (d / "source.md").exists(), "成功的誕生被誤刪了"


def test_discard_story_refuses_non_fresh():
    """_discard_story 對非 fresh 的 Run 直接罷工(opt-in 刪除)。"""
    d = _mk_story()
    run = critique.Run("s01", "標題", fresh=False)
    critique._discard_story(run)
    assert d.exists()


def test_discard_story_refuses_symlink(tmp_path):
    """目錄是 symlink → 拒刪(不順著刪到 stories/ 外面去)。"""
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "important.txt").write_text("別刪我", encoding="utf-8")

    link = config.STORIES / "s01"
    link.symlink_to(outside, target_is_directory=True)

    run = critique.Run("s01", "標題", fresh=True)
    critique._discard_story(run)

    assert outside.exists() and (outside / "important.txt").exists(), "順著 symlink 刪到外面了"


# ── attach():補播不漏不重 ───────────────────────────────────────────

def test_attach_replays_backlog_without_gaps_or_dupes(monkeypatch):
    """重整後重接:已發事件要補播、後續要直播,不漏不重。

    靠的是「註冊 subscriber 和快照 backlog 之間沒有 await」這個原子性。
    """
    _mk_story()

    async def three_then_done(slug, on_client=None):
        for i in range(3):
            yield {"event": "phase", "data": {"name": "analyst", "status": "start", "i": i}}
            await asyncio.sleep(0)
        yield {"event": "done", "data": {"ok": True, "cost_usd": 0.1}}

    monkeypatch.setattr(critique.orchestrator, "run_critique", three_then_done)

    async def go():
        got = [ev async for ev in critique.attach("s01", "標題")]
        assert [e["event"] for e in got].count("done") == 1
        idxs = [e["data"]["i"] for e in got if e["event"] == "phase"]
        assert idxs == [0, 1, 2], f"補播漏了或重了:{idxs}"

    asyncio.run(go())


def test_attach_to_finished_run_gets_full_backlog(monkeypatch):
    """晚到的重整(Run 已結束)→ 仍要拿到完整事件並乾淨結束,不得卡住。"""
    _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "phase", "data": {"name": "analyst", "status": "ok"}},
                                        {"event": "done", "data": {"ok": True, "cost_usd": 0.2}}]))

    async def go():
        run = critique.start("s01", "標題")
        await run.task                                    # 先讓它跑完
        got = [ev async for ev in critique.attach("s01", "標題")]
        assert [e["event"] for e in got] == ["phase", "done"]

    asyncio.run(go())


# ── list_running / cancel ────────────────────────────────────────────

def test_list_running_only_shows_running(monkeypatch):
    _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.1}}]))

    async def go():
        run = critique.start("s01", "標題")
        await run.task
        assert critique.list_running() == [], "已結束的 Run 不該出現在 running 列表"

    asyncio.run(go())


def test_cancel_unknown_slug_returns_false():
    async def go():
        assert await critique.cancel("s99") is False

    asyncio.run(go())


def test_cancel_marks_cancelled_and_discards_fresh(monkeypatch):
    """取消 fresh Run → 標 cancelled + 清掉剛 ingest 的孤兒。"""
    d = _mk_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600)
        yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        run = critique.start("s01", "標題", fresh=True)
        await asyncio.sleep(0)
        assert await critique.cancel("s01") is True
        assert run.status == "cancelled"
        assert not d.exists(), "取消 fresh 誕生該清掉孤兒"

    asyncio.run(go())


def test_cancel_existing_story_keeps_source(monkeypatch):
    """**F1 的另一半**:取消「重跑既有故事」→ 絕不能刪 source.md。"""
    d = _mk_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600)
        yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        critique.start("s01", "標題", fresh=False)      # 既有故事重跑
        await asyncio.sleep(0)
        await critique.cancel("s01")
        assert (d / "source.md").exists(), "取消重跑竟刪掉使用者無版控退路的 source.md"

    asyncio.run(go())


# ── reanalyze():snapshot .prev + done-only 守門 ─────────────────────

def _mk_complete_story(slug="s01"):
    d = config.STORIES / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    (d / "analysis.json").write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    (d / "feedback.json").write_text(json.dumps({"key_points": []}), encoding="utf-8")
    (d / "viz.json").write_text("{}", encoding="utf-8")
    for name in ("analysis.md", "feedback.md"):
        (d / name).write_text("md", encoding="utf-8")
    return d


def test_reanalyze_snapshots_then_runs(monkeypatch):
    d = _mk_complete_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600); yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        run = critique.reanalyze("s01", "標題")
        assert (d / ".prev" / "analysis.json").exists(), "重新分析要先把舊 artifact 搬進 .prev"
        assert not (d / "analysis.json").exists(), "搬走後目錄該空,resume_point 才會回 analyst"
        assert run.reanalyze is True
        run.task.cancel()
        try:
            await run.task
        except BaseException:
            pass

    asyncio.run(go())


def test_reanalyze_rejects_incomplete_story():
    _mk_story()                                  # 只有 source.md,不完整
    with pytest.raises(ValueError):
        critique.reanalyze("s01", "標題")


def test_reanalyze_success_discards_prev(monkeypatch):
    d = _mk_complete_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.9}}]))

    async def go():
        run = critique.reanalyze("s01", "標題")
        await run.task
        assert not (d / ".prev").exists(), "重新分析成功應丟棄 .prev"

    asyncio.run(go())


def test_reanalyze_failure_keeps_prev(monkeypatch):
    """never-worse-off:重新分析失敗 → 舊產物留在 .prev,不是憑空消失。

    _drive 收尾只在 reanalyze 且 status=="done" 才 discard_prev(commit);
    失敗時這個條件不成立,.prev 就該原封不動地留著當退路。
    """
    d = _mk_complete_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "閘門耗盡", "recoverable": False,
                                                  "reason": "gate"}}]))

    async def go():
        run = critique.reanalyze("s01", "標題")
        await run.task

    asyncio.run(go())
    assert (d / ".prev").exists(), "重新分析失敗竟丟了 .prev——舊版本沒有退路了"
    assert runstate.read(d)["status"] == "failed", "失敗的新狀態該被記下,才能續跑"


def test_done_discards_prev_even_when_not_reanalyze_run(monkeypatch):
    """Fix2 迴歸:resume(Run.reanalyze=False)跑到 done 也該丟棄殘留的 .prev。

    情境鏈:reanalyze 失敗留下 .prev(上一條測試證實)→ 使用者改點『續跑』
    (開的是 reanalyze=False 的 Run)把故事跑完 → 舊守門只在 run.reanalyze
    為真才 discard_prev,導致 .prev 永遠留著;下一次 reanalyze 的
    snapshot_to_prev 會直接覆蓋掉它,真正的原始備份就這樣不見了
    (never-worse-off 被打破)。done 就該丟棄任何殘留的 .prev,不看
    這一次 Run 是不是用 reanalyze 開的。
    """
    d = _mk_complete_story()
    (d / ".prev").mkdir()
    (d / ".prev" / "analysis.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.1}}]))

    run = critique.Run("s01", "標題", fresh=False)
    run.reanalyze = False
    asyncio.run(critique._drive(run))

    assert not (d / ".prev").exists(), "resume 跑到 done 沒有清掉殘留的 .prev"


def test_reanalyze_refuses_when_run_already_live(monkeypatch):
    """Fix3:該 slug 已有活的 Run 在跑 → reanalyze 不准 snapshot_to_prev。

    舊行為:reanalyze() 沒檢查就先 snapshot_to_prev 把產物搬走,再呼叫
    start()——但 start() 見已有 running 的 Run 就直接回既有 Run,不會套用
    reanalyze 語意。結果是:產物在活的 orchestrator 底下被搬空了,
    但沒有人在「重新分析」它,活的那個 Run 會在錯誤的空產物狀態下繼續動作。
    正確行為是搬空之前先擋:已有活 Run → 不搬、直接報錯(app 層轉 409)。
    """
    d = _mk_complete_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600); yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        live = critique.start("s01", "標題")
        with pytest.raises(ValueError):
            critique.reanalyze("s01", "新標題")
        assert (d / "analysis.json").exists(), "已有活 Run 時 reanalyze 竟把產物搬進 .prev"
        assert not (d / ".prev").exists()
        live.task.cancel()
        try:
            await live.task
        except BaseException:
            pass

    asyncio.run(go())


# ── 停住的 Run 要讓 index.json 說實話 ────────────────────────────────
#
# index.py 只長在 orchestrator 的 render 那一格(成功路徑)。停住的 Run 若不補一刀,
# index.json 會停在上一次成功的樣子——對 reanalyze 而言,那份舊列表正好在說
# 「這篇完好」,而產物已經被 snapshot 進 .prev/,前端於是畫出一顆騙人的完好星。


def _index(d=None):
    p = (d or config.STORIES) / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def test_stopped_reanalyze_refreshes_index(monkeypatch):
    """reanalyze 失敗 → 列表要立刻反映「產物不在了、這篇可續跑」。

    不修的話 index.json 還是重跑前那份(has_feedback/has_viz 皆 true、resumable false),
    前端據此畫出一顆完好的星:點進去 404 或半殘,hover 出來的「重新分析」按下去是 409,
    而真正的舊版鎖在 .prev/ 裡從 UI 完全看不到。
    """
    _mk_complete_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "逾時", "recoverable": False,
                                                  "reason": "timeout"}}]))

    async def go():
        run = critique.reanalyze("s01", "標題")
        await run.task

    asyncio.run(go())

    idx = _index()
    assert idx is not None, "停住的 Run 沒有重建 index.json —— 列表還在說這篇完好"
    e = next(s for s in idx["stories"] if s["slug"] == "s01")
    assert e["resumable"] is True, "停住的故事在列表上必須是可續跑的"
    assert e["has_feedback"] is False and e["has_viz"] is False, \
        "產物已搬進 .prev,列表卻還說它們在——這正是那顆騙人的星"


def test_done_does_not_refresh_index(monkeypatch):
    """done 不在這裡重建列表:render 那一格已經建過,而且必須是它建。

    done 事件一發,前端就 onBorn → 重抓 index(useGestations)。把重建挪到 _drive 的
    finally(在 done 之後)會變成競態:前端可能抓到還沒更新的那份。
    """
    _mk_complete_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "done", "data": {"ok": True, "cost_usd": 0.5}}]))

    async def go():
        run = critique.start("s01", "標題")
        await run.task

    asyncio.run(go())
    assert _index() is None, "done 竟在 _drive 裡重建 index —— 那是 render 那一格的職責"


def test_cancelled_reanalyze_is_resumable(monkeypatch):
    """取消一次 reanalyze:run.json 要寫 failed(而非 cancelled)+ reason=cancelled。

    index 的 resumable 白名單只認 paused/failed。留著 "cancelled" 這個值域,
    取消過的星就一個出口都沒有:續跑鈕不出(resumable false)、重新分析鈕也不出
    (產物在 .prev,has_feedback false),而舊版拿不回來。
    """
    d = _mk_complete_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600); yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        run = critique.reanalyze("s01", "標題")
        await asyncio.sleep(0)
        await critique.cancel("s01")
        return run

    run = asyncio.run(go())

    rs = runstate.read(d)
    assert rs["status"] == "failed", "取消過的 reanalyze 卡在 cancelled → 列表認不得,星沒有出口"
    assert rs["reason"] == "cancelled"
    e = next(s for s in _index()["stories"] if s["slug"] == "s01")
    assert e["resumable"] is True
    assert e["reason"] == "cancelled", "停住的原因要一路帶到列表,前端才講得出「你取消了」"
    assert any(ev.get("data", {}).get("reason") == "cancelled" for ev in run.events), \
        "取消既有故事的事件要帶 reason,前端才不會把星靜靜收掉"


def test_cancelled_fresh_gestation_carries_no_reason(monkeypatch):
    """取消 fresh 新孕育:事件**不帶** reason,且列表裡不留那篇。

    fresh 取消會連目錄一起刪(_discard_story),沒有東西可續 —— 帶 reason 會讓前端
    長出一顆指向已刪目錄的可續星。這個分野後端自己知道(run.fresh),別讓前端猜。
    """
    _mk_story()

    async def never_ending(slug, on_client=None):
        await asyncio.sleep(3600); yield {}

    monkeypatch.setattr(critique.orchestrator, "run_critique", never_ending)

    async def go():
        run = critique.start("s01", "標題", fresh=True)
        await asyncio.sleep(0)
        await critique.cancel("s01")
        return run

    run = asyncio.run(go())

    assert not any("reason" in ev.get("data", {}) for ev in run.events), \
        "fresh 取消竟帶了 reason —— 前端會留下一顆指向已刪目錄的可續星"
    assert not (config.STORIES / "s01").exists()
    assert _index()["stories"] == [], \
        "取消刪檔後列表沒重刷:_drive 的 finally 早於 _discard_story,那次刷到的是還沒刪的樣子"


def test_scan_crashed_refreshes_index():
    """server 掛在 reanalyze 中間 → 重啟掃孤兒,列表也得跟著更新。

    scan_crashed 只寫 run.json;不補這一刀的話,crash 這條路上 index.json 照樣
    停在重跑前那份完好的樣子(_drive 根本沒機會跑 finally)。
    """
    d = config.STORIES / "s01"
    d.mkdir(parents=True)
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    runstate.write(d, status="running", stage="analyst", title="標題")

    critique.scan_crashed()

    assert runstate.read(d)["status"] == "failed"
    e = next(s for s in _index()["stories"] if s["slug"] == "s01")
    assert e["resumable"] is True and e["reason"] == "crash"


def test_scan_crashed_without_orphans_writes_nothing():
    """沒標到任何一篇就別寫檔:每次啟動白寫一次 index.json 是純噪音。"""
    d = config.STORIES / "s01"
    d.mkdir(parents=True)
    runstate.write(d, status="done", stage="done", title="標題")

    critique.scan_crashed()

    assert _index() is None, "沒有孤兒可標,卻還是重寫了 index.json"
