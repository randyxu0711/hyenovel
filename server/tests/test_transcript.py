"""討論逐字正本(transcript)零成本 canary。
跑法(repo 根):  server/.venv/bin/python -m pytest server/tests/test_transcript.py
"""
import json
import logging
import tempfile
from pathlib import Path

import conclusions

from server import config, transcript

logging.getLogger("hyenovel").addHandler(logging.NullHandler())


class _tmp_stories:
    """把 config.STORIES 指到臨時空目錄,離開還原;transcript 於呼叫時讀 config.STORIES,故生效。
    同時把 conclusions.STORIES 指到同一個目錄 —— transcript.append() 現在會呼叫
    conclusions.analysis_fp(slug) 幫每一行蓋指紋,兩邊沒指到同一處,測試看到的
    analysis.json 就會是別的東西(甚至是真實 stories/ 底下的),而不是這個臨時故事的。"""
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._orig = config.STORIES
        self._orig_c = conclusions.STORIES
        config.STORIES = Path(self._t.name)
        conclusions.STORIES = Path(self._t.name)
        return config.STORIES

    def __exit__(self, *a):
        config.STORIES = self._orig
        conclusions.STORIES = self._orig_c
        self._t.cleanup()


def test_append_writes_both_roles_and_load_reads():
    """使用者訊息也必須留下 —— 這正是接線前整個系統丟掉的東西。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        transcript.append("s99", "abc123", "user", "這個結尾收太快了吧", anchors=["e1"])
        transcript.append("s99", "abc123", "assistant", "你指的是關燈那句?")
        rows = transcript.load("s99")
        assert len(rows) == 2, "兩輪都該在"
        assert rows[0]["role"] == "user" and rows[0]["text"] == "這個結尾收太快了吧"
        assert rows[0]["anchors"] == ["e1"], "錨定該原樣留下"
        assert rows[0]["session"] == "abc123"
        assert rows[1]["role"] == "assistant" and rows[1]["anchors"] is None, "無錨定寫 None"
        assert isinstance(rows[0]["ts"], float)


def test_append_skips_missing_dir():
    with _tmp_stories():
        transcript.append("s_nonexistent", "abc", "user", "hi")   # 不該炸
        assert transcript.load("s_nonexistent") == []


def test_load_skips_bad_line():
    """一行壞掉不該讓整份讀不了。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "transcript.jsonl").write_text(
            '{"role":"user","text":"好"}\n{壞掉的\n\n{"role":"assistant","text":"嗯"}\n',
            encoding="utf-8")
        rows = transcript.load("s99")
        assert len(rows) == 2, "壞行與空行跳過,其餘照讀"


def test_load_missing_file():
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        assert transcript.load("s99") == []


def test_append_survives_write_failure(monkeypatch):
    """磁碟寫不進去也絕不打斷正在進行的討論。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "open", boom)
        transcript.append("s99", "abc", "user", "hi")   # 不該炸


def test_non_ascii_not_escaped():
    """中文要能直接讀 —— 這份檔是人也會打開看的正本。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        transcript.append("s99", "abc", "user", "月光")
        raw = (S / "s99" / "transcript.jsonl").read_text(encoding="utf-8")
        assert "月光" in raw, "不該被 \\u 轉義"
        assert json.loads(raw)["text"] == "月光"


def test_session_range_picks_that_session_only():
    """收束時要知道「這一局」涵蓋 transcript 的哪幾行 —— 純函式,不碰檔案。"""
    rows = [{"session": "a"}, {"session": "b"}, {"session": "a"}, {"session": "b"}]
    assert transcript.session_range(rows, "a") == [0, 2]
    assert transcript.session_range(rows, "b") == [1, 3]
    assert transcript.session_range(rows, "zzz") == [-1, -1], (
        "minor 6:沒有該 session 要回自明為空的 [-1,-1],不能是 [0,0] —— "
        "[0,0] 跟『這個 session 剛好只涵蓋第 0 行』無法區分")


def test_record_of_includes_analysis_fp():
    """important 3:transcript 每一行都要帶當時 analysis.json 的指紋,不能只有裸的 node id ——
    node id 會在每次 re-analyze 被重鑄,沒有指紋就無從偵測『這個錨定已經懸空』。"""
    r = transcript.record_of("s", "user", "text", ["t1"], "deadbeef")
    assert r["analysis_fp"] == "deadbeef"


def test_append_stamps_analysis_fp_from_conclusions():
    """端到端:append() 要重用 conclusions.analysis_fp(),不是自己重算一份指紋邏輯。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text('{"nodes":[]}', encoding="utf-8")
        transcript.append("s99", "abc", "user", "hi")
        row = transcript.load("s99")[0]
        assert row["analysis_fp"] == conclusions.analysis_fp("s99")
        assert row["analysis_fp"] != "", "有 analysis.json 就該有非空指紋"


def test_append_stamps_empty_analysis_fp_when_missing():
    """還沒跑過 critique(沒有 analysis.json)—— 指紋是空字串,不是錯誤也不炸。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        transcript.append("s99", "abc", "user", "hi")
        assert transcript.load("s99")[0]["analysis_fp"] == ""


def test_append_survives_unreadable_analysis_json():
    """fix pass 2 / important 1:analysis.json 存在但讀不了(換成目錄 →
    read_bytes() 炸 IsADirectoryError)—— conclusions.analysis_fp() 這行邏輯現在
    掛在 run_discuss 的 try 之外(:99 之前、:135 之後都不在 try 區塊內),炸出去
    會逃出 _sse(app.py 沒有 catch-all)讓 SSE 串流當場中斷,還讓這輪的
    ledger.append 整個蒸發。transcript.append 承諾『記錄失敗不該打斷使用者正在
    進行的對話』,這裡不能真的炸。"""
    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").mkdir()   # 換成目錄,read_bytes() 會 IsADirectoryError
        transcript.append("s99", "abc", "user", "hi")   # 不該炸
        row = transcript.load("s99")[0]
        assert row["analysis_fp"] == ""


def test_record_of_does_not_explode_scalar_anchors():
    """minor 5:anchors 給成純量字串(如 "t1")不能被 list() 拆成 ['t','1'] ——
    目前 app._anchors 在 HTTP 邊界擋著只會送 list,但這正是 Task 4 那道閘門被攻破過
    三次的同一個形狀:第二個呼叫端(終端機捕獲、P2)一出現就會直接餵純量。"""
    r = transcript.record_of("s", "user", "text", "t1", "fp")
    assert r["anchors"] == "t1", "原樣照抄,不被拆成單字元陣列"


# ── Task 2:接線 discuss ────────────────────────────────────────────
def test_discuss_captures_both_sides(monkeypatch):
    """跑一輪討論 → transcript 同時有 user 與 assistant。
    這是接線前最大的洞:ledger 只留 assistant 的成本,使用者說了什麼完全沒保存。"""
    import asyncio
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    from server import discuss

    class FakeClient:
        async def connect(self):
            pass

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="關燈那句確實收得急。")], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(discuss, "ClaudeSDKClient", lambda options=None: FakeClient())

        async def go():
            return [ev async for ev in discuss.run_discuss("s99", None, "結尾收太快了")]

        asyncio.run(go())

        rows = transcript.load("s99")
        roles = [r["role"] for r in rows]
        assert roles == ["user", "assistant"], f"該一問一答各一行,實際 {roles}"
        assert rows[0]["text"] == "結尾收太快了", "使用者原話要留原話,不是加工過的 prompt"
        assert rows[1]["text"] == "關燈那句確實收得急。"
        assert rows[0]["session"] == rows[1]["session"], "同一輪同一個 session id"


def test_discuss_captures_all_text_blocks_in_a_turn(monkeypatch):
    """important 2:一輪可能有不只一個 AssistantMessage(discuss client 是
    allowed_tools=["Read"],開場的 /story-discuss skill 會讀 analysis/feedback/source,
    讀檔前後常各自帶一段文字)。原本『final = b.text』是覆寫不是累積,只有最後一個
    TextBlock 進得了 transcript —— 但使用者透過 token 串流兩句都看到了,逐字正本卻
    悄悄丟掉前面那句。"""
    import asyncio
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    from server import discuss

    class FakeClient:
        async def connect(self):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="我先讀一下原文。")], model="m")
            yield AssistantMessage(content=[TextBlock(text="關燈那句確實收得急。")], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(discuss, "ClaudeSDKClient", lambda options=None: FakeClient())

        async def go():
            return [ev async for ev in discuss.run_discuss("s99", None, "結尾如何")]

        asyncio.run(go())

        rows = transcript.load("s99")
        assistant_rows = [r for r in rows if r["role"] == "assistant"]
        assert len(assistant_rows) == 1, "還是一輪一行,不是每個 block 各起一行"
        text = assistant_rows[0]["text"]
        assert "我先讀一下原文。" in text, "第一個 TextBlock 不能被第二個悄悄覆寫掉"
        assert "關燈那句確實收得急。" in text


def test_discuss_skips_empty_user_message(monkeypatch):
    """開場沒帶訊息(只點開討論)不該產生一行空的 user 記錄。"""
    import asyncio
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    from server import discuss

    class FakeClient:
        async def connect(self):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="我們從孤兒技法聊起?")], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(discuss, "ClaudeSDKClient", lambda options=None: FakeClient())

        async def go():
            return [ev async for ev in discuss.run_discuss("s99", None, "")]

        asyncio.run(go())

        rows = transcript.load("s99")
        assert [r["role"] for r in rows] == ["assistant"], "只有開場白,沒有空的 user 行"


# ── Task 3:anchors 端到端 ──────────────────────────────────────────
def test_discuss_records_anchors(monkeypatch):
    """節點錨定要落成結構化欄位,不能只塞在散文裡 —— P2 的 recall 靠它。"""
    import asyncio
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    from server import discuss

    class FakeClient:
        async def connect(self):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="嗯。")], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(discuss, "ClaudeSDKClient", lambda options=None: FakeClient())

        async def go():
            return [ev async for ev in discuss.run_discuss("s99", None, "這顆呢", anchors=["m2"])]

        asyncio.run(go())

        rows = transcript.load("s99")
        assert rows[0]["anchors"] == ["m2"], "user 行要帶錨定"
        assert rows[1]["anchors"] == ["m2"], "assistant 行也要帶 —— 它回的就是這顆"


# ── Task 5:收束 ────────────────────────────────────────────────────
def _fixture_source():
    """用合成樣本,絕不碰真實 stories/。"""
    return (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mini" / "source.md").read_text(encoding="utf-8")


def _prime_session(monkeypatch, S, reply):
    """造一個活著的 session,並讓下一次 run_turn 回傳指定文字。"""
    import conclusions
    from server import discuss

    class FakeClient:
        async def connect(self):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
            yield AssistantMessage(content=[TextBlock(text=reply)], model="m")
            yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9,
                                is_error=False, num_turns=1, session_id="sdk-1",
                                total_cost_usd=0.01, usage={}, model_usage={})

    monkeypatch.setattr(discuss, "ClaudeSDKClient", lambda options=None: FakeClient())
    monkeypatch.setattr(conclusions, "STORIES", S)
    return discuss


def test_distill_writes_conclusions(monkeypatch):
    import asyncio
    import conclusions

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        # 圖裡要真的有 e1 —— 結論的 refs 落點也是閘門(conclusions 第三道),
        # 空圖配 refs:["e1"] 會被正確擋下,那測到的就不是「收束能寫入」了。
        (S / "s99" / "analysis.json").write_text(
            '{"nodes":[{"id":"e1","type":"effect","label":"空缺感"}]}', encoding="utf-8")
        (S / "s99" / "source.md").write_text(_fixture_source(), encoding="utf-8")
        drafts = '[{"kind":"judgment","text":"收尾太快","refs":["e1"],"quotes":["他把燈關了。"]}]'
        discuss = _prime_session(monkeypatch, S, drafts)

        async def go():
            sid = None
            async for ev in discuss.run_discuss("s99", None, "聊聊結尾"):
                if ev["event"] == "done":
                    sid = ev["data"]["session_id"]
            return await discuss.distill("s99", sid)

        res = asyncio.run(go())
        assert res["written"] == 1 and res["errors"] == []
        rows = conclusions.load("s99")
        assert rows[0]["kind"] == "judgment"
        assert rows[0]["provenance"]["turns"] == [0, 1], "涵蓋這一局的 transcript 行"


def test_distill_rejects_hallucinated_quote(monkeypatch):
    """收束不是免死金牌 —— 引文照樣要過閘門。"""
    import asyncio
    import conclusions

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        (S / "s99" / "analysis.json").write_text('{"nodes":[]}', encoding="utf-8")
        (S / "s99" / "source.md").write_text(_fixture_source(), encoding="utf-8")
        drafts = '[{"kind":"judgment","text":"x","refs":[],"quotes":["這句原文裡根本沒有"]}]'
        discuss = _prime_session(monkeypatch, S, drafts)

        async def go():
            sid = None
            async for ev in discuss.run_discuss("s99", None, "聊聊"):
                if ev["event"] == "done":
                    sid = ev["data"]["session_id"]
            return await discuss.distill("s99", sid)

        res = asyncio.run(go())
        assert res["written"] == 0 and res["errors"], "幻覺引文要被擋"
        assert conclusions.load("s99") == []


def test_distill_needs_live_session(monkeypatch):
    import asyncio
    from server import discuss

    with _tmp_stories() as S:
        (S / "s99").mkdir()
        res = asyncio.run(discuss.distill("s99", "not-a-session"))
        assert res["written"] == 0 and "session" in res["errors"][0]
