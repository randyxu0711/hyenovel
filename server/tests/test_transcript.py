"""討論逐字正本(transcript)零成本 canary。
跑法(repo 根):  server/.venv/bin/python -m pytest server/tests/test_transcript.py
"""
import json
import logging
import tempfile
from pathlib import Path

from server import config, transcript

logging.getLogger("hyenovel").addHandler(logging.NullHandler())


class _tmp_stories:
    """把 config.STORIES 指到臨時空目錄,離開還原;transcript 於呼叫時讀 config.STORIES,故生效。"""
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._orig = config.STORIES
        config.STORIES = Path(self._t.name)
        return config.STORIES

    def __exit__(self, *a):
        config.STORIES = self._orig
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
    assert transcript.session_range(rows, "zzz") == [0, 0], "沒有該 session 回退化區間"
