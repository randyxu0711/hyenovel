"""自動收束的行為契約(server/settle.py)—— 零成本,不碰真實 stories/、不打真 SDK。

覆蓋率不設數字門檻(這個模組混了 ClaudeSDKClient 接線),靠下列契約逐條守:
  ① 煉出來的東西照樣過三道閘門 —— 收束不是免死金牌
  ② **成敗都要留下水位**,否則不是重煉出重複結論、就是永遠重試
  ③ 逐字由我們組進 prompt,不讓 LLM 自己讀整篇 transcript(會串到別局)
  ④ 一輪有上限、一篇炸掉不吃掉整個 worker
"""
import asyncio
import logging
import tempfile
from pathlib import Path

import conclusions
import settled

from server import config, settle, transcript

logging.getLogger("hyenovel").addHandler(logging.NullHandler())


class _tmp_stories:
    """同 test_transcript:config/conclusions/settled 三邊的 STORIES 都要指到同一處,
    否則測試看到的會是別的東西(甚至是真實 stories/ 底下的)。"""
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._orig = (config.STORIES, conclusions.STORIES, settled.STORIES)
        p = Path(self._t.name)
        config.STORIES = conclusions.STORIES = settled.STORIES = p
        return p

    def __exit__(self, *a):
        config.STORIES, conclusions.STORIES, settled.STORIES = self._orig
        self._t.cleanup()


def _fixture_source():
    return (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mini"
            / "source.md").read_text(encoding="utf-8")


def _story(S, slug="s99"):
    (S / slug).mkdir()
    (S / slug / "analysis.json").write_text(
        '{"nodes":[{"id":"e1","type":"effect","label":"空缺感"}]}', encoding="utf-8")
    (S / slug / "source.md").write_text(_fixture_source(), encoding="utf-8")
    return S / slug


def _fake_client(monkeypatch, reply, seen=None, boom=False):
    """讓 settle 開出來的專用 client 回傳指定文字。seen 收下它真正送出的 prompt。"""
    class FakeClient:
        async def connect(self):
            if boom:
                raise RuntimeError("connect 炸了")

        async def query(self, prompt):
            if seen is not None:
                seen.append(prompt)

        async def receive_response(self):
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
            yield AssistantMessage(content=[TextBlock(text=reply)], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

        async def disconnect(self):
            pass

    monkeypatch.setattr(settle, "ClaudeSDKClient", lambda options=None: FakeClient())


DRAFT = '[{"kind":"judgment","text":"收尾太快","refs":["e1"],"quotes":["他把燈關了。"]}]'


# ── settle_session:煉一局 ────────────────────────────────────────
def test_settle_writes_conclusions_and_watermark(monkeypatch):
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊結尾")
        transcript.append("s99", "sess1", "assistant", "關燈那句收得很快")
        _fake_client(monkeypatch, DRAFT)

        res = asyncio.run(settle.settle_session("s99", "sess1"))

        assert res["written"] == 1 and res["errors"] == []
        rows = conclusions.load("s99")
        assert rows[0]["kind"] == "judgment"
        assert rows[0]["provenance"]["session"] == "sess1"
        assert rows[0]["provenance"]["turns"] == [0, 1], "涵蓋這一局的 transcript 行"
        w = settled.load("s99")
        assert len(w) == 1 and w[0]["ok"] is True and w[0]["written"] == 1


def test_settle_rejects_hallucinated_quote(monkeypatch):
    """收束不是免死金牌 —— 引文照樣要過閘門。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊")
        transcript.append("s99", "sess1", "assistant", "嗯")
        _fake_client(monkeypatch,
                     '[{"kind":"judgment","text":"x","refs":["e1"],'
                     '"quotes":["這句原文裡根本沒有"]}]')

        res = asyncio.run(settle.settle_session("s99", "sess1"))

        assert res["written"] == 0 and res["errors"], "幻覺引文要被擋"
        assert conclusions.load("s99") == []


def test_settle_records_watermark_when_gates_reject_everything(monkeypatch):
    """★ 閘門全擋仍要記水位 —— 否則這局每輪重煉一次,是個沒有出口的花錢迴圈。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊")
        transcript.append("s99", "sess1", "assistant", "嗯")
        _fake_client(monkeypatch,
                     '[{"kind":"judgment","text":"x","refs":["nope"],"quotes":[]}]')

        asyncio.run(settle.settle_session("s99", "sess1"))

        w = settled.load("s99")
        assert len(w) == 1 and w[0]["ok"] is True, "閘門跑過了就是收束完成,不重試"
        assert settled.pending("s99", transcript.load("s99"), set()) == []


def test_settle_records_watermark_when_client_blows_up(monkeypatch):
    """★ 炸掉也要留下記錄 —— 沒有記錄就是無限重試。但 ok:false,還能再試。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊")
        _fake_client(monkeypatch, DRAFT, boom=True)

        res = asyncio.run(settle.settle_session("s99", "sess1"))

        assert res["written"] == 0 and res["errors"]
        w = settled.load("s99")
        assert len(w) == 1 and w[0]["ok"] is False
        assert settled.pending("s99", transcript.load("s99"), set()) == ["sess1"], "可重試"


def test_settle_parse_failure_is_retryable(monkeypatch):
    """LLM 吐不出 JSON = 這一次的意外,不是這一局的定論 → ok:false,還能再試。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊")
        _fake_client(monkeypatch, "我覺得這個結尾還不錯欸")

        asyncio.run(settle.settle_session("s99", "sess1"))

        assert settled.load("s99")[0]["ok"] is False


def test_settle_refuses_session_absent_from_transcript(monkeypatch):
    """退化區間([-1,-1]):硬煉會蓋出指向別局第一行的 provenance —— 一個看起來合理的謊。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "other", "user", "別局的話")
        _fake_client(monkeypatch, DRAFT)

        res = asyncio.run(settle.settle_session("s99", "no-such"))

        assert res["written"] == 0
        assert conclusions.load("s99") == []
        assert settled.load("s99")[0]["ok"] is True, "放棄且不重試"


def test_settle_prompt_carries_only_this_session(monkeypatch):
    """★ 逐字由我們組進 prompt。transcript.jsonl 含整篇所有 session,
    放 LLM 自己去讀會串局,而它無從分辨哪幾行屬於這一局。"""
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "這一局的話")
        transcript.append("s99", "other", "user", "別局的話")
        seen = []
        _fake_client(monkeypatch, "[]", seen=seen)

        asyncio.run(settle.settle_session("s99", "sess1"))

        assert "這一局的話" in seen[0]
        assert "別局的話" not in seen[0]


def test_settle_writes_cost_to_ledger(monkeypatch):
    """自動路徑照樣要記帳 —— 沒有人按鈕之後,帳本是唯一看得到它花錢的地方。"""
    from server import ledger
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "sess1", "user", "聊聊")
        _fake_client(monkeypatch, "[]")

        asyncio.run(settle.settle_session("s99", "sess1"))

        assert [r["phase"] for r in ledger.load("s99")] == ["distill"]


# ── due / sweep_settle:排程 ──────────────────────────────────────
def test_due_skips_live_sessions(monkeypatch):
    with _tmp_stories() as S:
        _story(S)
        transcript.append("s99", "live1", "user", "還在聊")
        transcript.append("s99", "dead1", "user", "聊完了")
        monkeypatch.setattr(settle, "_live", lambda slug: {"live1"})

        assert settle.due() == [("s99", "dead1")]


def test_due_caps_per_sweep(monkeypatch):
    """意外 backlog 用滴的不用灌的 —— 一輪把十幾局全煉了是一筆無人看管的帳單。"""
    with _tmp_stories() as S:
        _story(S)
        for i in range(6):
            transcript.append("s99", f"s{i}", "user", "x")
        monkeypatch.setattr(settle, "_live", lambda slug: set())

        assert len(settle.due(limit=2)) == 2
        assert len(settle.due()) == settle.MAX_PER_SWEEP


def test_due_ignores_non_directories(monkeypatch):
    with _tmp_stories() as S:
        _story(S)
        (S / "loose.txt").write_text("x", encoding="utf-8")
        transcript.append("s99", "s1", "user", "x")
        monkeypatch.setattr(settle, "_live", lambda slug: set())

        assert settle.due() == [("s99", "s1")]


def test_due_empty_when_stories_dir_missing(monkeypatch):
    monkeypatch.setattr(config, "STORIES", Path("/no/such/dir"))
    assert settle.due() == []


def test_sweep_survives_one_story_blowing_up(monkeypatch):
    """★ 一篇炸掉不能讓整個 worker 靜靜死掉 —— 死掉的守衛跟活著的守衛長得一樣。"""
    calls = []

    async def boom(slug, sid):
        calls.append(sid)
        if sid == "bad":
            raise RuntimeError("炸了")

    async def one_pass():
        monkeypatch.setattr(settle, "due", lambda: [("s99", "bad"), ("s99", "good")])
        monkeypatch.setattr(settle, "settle_session", boom)
        monkeypatch.setattr(settle, "SWEEP_INTERVAL", 0)
        task = asyncio.create_task(settle.sweep_settle())
        await asyncio.sleep(0)
        while len(calls) < 2:
            await asyncio.sleep(0)
        task.cancel()

    asyncio.run(one_pass())
    assert calls[:2] == ["bad", "good"], "前一局炸掉,後一局照跑"


def test_sweep_survives_scan_failure(monkeypatch):
    """掃描本身炸掉(磁碟壞/權限)也不能讓迴圈退出。"""
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("掃不動")
        return []

    async def one_pass():
        monkeypatch.setattr(settle, "due", flaky)
        monkeypatch.setattr(settle, "SWEEP_INTERVAL", 0)
        task = asyncio.create_task(settle.sweep_settle())
        while state["n"] < 2:
            await asyncio.sleep(0)
        task.cancel()

    asyncio.run(one_pass())
    assert state["n"] >= 2, "第一輪炸掉之後仍有第二輪"
