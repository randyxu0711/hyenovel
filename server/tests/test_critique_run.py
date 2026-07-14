"""critique.Run 的行為契約 —— 全是我們的政策,SDK 不知道也不管。

最重的一條:**F1 迴歸** —— 重跑既有故事失敗/取消時,
絕不能刪掉使用者「沒有版控退路」的 source.md(stories/ 不進版控)。
刪掉就是永久資料遺失。
"""
import asyncio

import pytest

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


def test_failed_fresh_birth_discards_orphan(monkeypatch):
    """fresh 誕生失敗 → 清掉半成品(它是本流程剛 ingest 的,清掉安全)。"""
    d = _mk_story()
    monkeypatch.setattr(critique.orchestrator, "run_critique",
                        _fake_critique([{"event": "error",
                                         "data": {"message": "閘門耗盡", "recoverable": False}}]))

    run = critique.Run("s01", "標題", fresh=True)
    asyncio.run(critique._drive(run))
    assert not d.exists(), "fresh 誕生失敗該清掉孤兒"


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
