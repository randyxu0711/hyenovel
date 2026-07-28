"""自動收束的水位(settled.jsonl)—— 確定性層,100% 覆蓋。

這裡守的是**兩個會重複花錢的洞**,它們互為對方的盲點:
  ① 只看 conclusions:煉出零條的局永遠查不到自己 → 每輪重煉 → 無限花錢
  ② 只看 settled:結論落地但這裡寫入失敗 → 重煉 → 結論重複
故 pending() 兩個來源都看,任一有記錄就不再煉。
"""
import json

import pytest

import conclusions
import settled


@pytest.fixture
def base(story, monkeypatch):
    """同 test_conclusions 的立場:record() 會**真的寫檔**,安全帶綁在會開槍的槍上。
    settled 與 conclusions 兩個模組的 STORIES 都要導向 tmp,pending() 兩個都讀。"""
    slug, b = story
    monkeypatch.setattr(settled, "STORIES", b.parent)
    monkeypatch.setattr(conclusions, "ROOT", b.parent.parent)
    monkeypatch.setattr(conclusions, "STORIES", b.parent)
    return slug, b


def _rows(*sessions):
    """假的 transcript rows —— pending() 只讀 session 欄。"""
    return [{"session": s, "role": "user", "text": "x"} for s in sessions]


def _conclusion(session, cid="c0001"):
    return {"id": cid, "kind": "judgment", "text": "x", "refs": ["e1"], "quotes": [],
            "provenance": {"session": session, "turns": [0, 1], "analysis_fp": "f"}}


# ── load:壞行寬容,同 conclusions.load 的契約 ──────────────────────
def test_load_missing_file(base):
    slug, _ = base
    assert settled.load(slug) == []


def test_load_skips_broken_and_blank_lines(base):
    slug, b = base
    (b / "settled.jsonl").write_text(
        '{"session":"a","ok":true}\n\n{壞行\n{"session":"b","ok":false}\n',
        encoding="utf-8")
    assert [r["session"] for r in settled.load(slug)] == ["a", "b"]


def test_load_io_failure_returns_empty(base, monkeypatch):
    """TOCTOU:exists() 過了才壞。吞掉回 [],不讓背景 worker 掛在讀檔上。"""
    slug, b = base
    (b / "settled.jsonl").write_text('{"session":"a"}\n', encoding="utf-8")

    def boom(*a, **k):
        raise OSError("gone")
    monkeypatch.setattr(settled.Path, "read_text", boom)
    assert settled.load(slug) == []


# ── record:成敗都要留下一列 ───────────────────────────────────────
def test_record_appends_row(base):
    slug, b = base
    settled.record(slug, "s1", True, 3, [])
    settled.record(slug, "s2", False, 0, ["炸了"])
    rows = [json.loads(l) for l in
            (b / "settled.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["session"] for r in rows] == ["s1", "s2"]
    assert rows[0]["ok"] is True and rows[0]["written"] == 3
    assert rows[1]["ok"] is False and rows[1]["errors"] == ["炸了"]
    assert isinstance(rows[0]["ts"], float)


def test_record_skips_when_story_dir_gone(base):
    """故事被刪掉了就別憑空造目錄 —— 同 transcript.append 的守則。"""
    slug, _ = base
    settled.record("no-such-slug", "s1", True, 0, [])
    assert not (settled.STORIES / "no-such-slug").exists()


def test_record_swallows_io_failure(base, monkeypatch):
    """寫不進去不能讓 sweep 掛掉。代價是這局會被重煉 —— 由 conclusions 那半邊接住。"""
    slug, _ = base

    def boom(*a, **k):
        raise OSError("readonly")
    monkeypatch.setattr(settled.Path, "open", boom)
    settled.record(slug, "s1", True, 1, [])      # 不拋


# ── pending:四道排除 ─────────────────────────────────────────────
def test_pending_fresh_session(base):
    slug, _ = base
    assert settled.pending(slug, _rows("a"), set()) == ["a"]


def test_pending_skips_live_session(base):
    """還活著的局現在煉會得到半局,而且之後沒有第二次機會。"""
    slug, _ = base
    assert settled.pending(slug, _rows("a", "b"), {"a"}) == ["b"]


def test_pending_skips_already_distilled(base):
    """conclusions 那半邊:settled.jsonl 寫入失敗時靠它擋住重複結論。"""
    slug, b = base
    (b / "conclusions.jsonl").write_text(
        json.dumps(_conclusion("a"), ensure_ascii=False) + "\n", encoding="utf-8")
    assert settled.pending(slug, _rows("a", "b"), set()) == ["b"]


def test_pending_skips_zero_written_success(base):
    """★ 無限花錢閘:煉出零條在 conclusions 裡查不到自己,只有 settled 記得。"""
    slug, _ = base
    settled.record(slug, "a", True, 0, [])
    assert settled.pending(slug, _rows("a"), set()) == []


def test_pending_retries_failed_attempt(base):
    """失敗要重試 —— 一次網路抖動不該讓一局結論永久消失。"""
    slug, _ = base
    settled.record(slug, "a", False, 0, ["timeout"])
    assert settled.pending(slug, _rows("a"), set()) == ["a"]


def test_pending_gives_up_after_max_attempts(base):
    """沒有上限的重試是一個沒有出口的花錢迴圈。"""
    slug, _ = base
    for _ in range(settled.MAX_ATTEMPTS):
        settled.record(slug, "a", False, 0, ["timeout"])
    assert settled.pending(slug, _rows("a"), set()) == []


def test_pending_skips_story_without_analysis(base):
    """refs 閘門沒有基準,煉了也一定過不了 —— 別花那個錢。"""
    slug, b = base
    (b / "analysis.json").unlink()
    assert settled.pending(slug, _rows("a"), set()) == []


def test_pending_dedupes_and_keeps_transcript_order(base):
    slug, _ = base
    assert settled.pending(slug, _rows("b", "a", "b", "c"), set()) == ["b", "a", "c"]


def test_pending_ignores_rows_without_session(base):
    """逐字壞行被 load() 跳過,但缺 session 欄的合法 JSON 進得來。"""
    slug, _ = base
    rows = [{"role": "user"}, {"session": None}, {"session": "a"}]
    assert settled.pending(slug, rows, set()) == ["a"]


def test_pending_ignores_settled_rows_without_session(base):
    """壞掉的水位列不該把 attempts 算到別人頭上。"""
    slug, b = base
    (b / "settled.jsonl").write_text('{"ok":true}\n{"session":null,"ok":true}\n',
                                     encoding="utf-8")
    assert settled.pending(slug, _rows("a"), set()) == ["a"]


def test_pending_ignores_conclusion_without_provenance(base):
    slug, b = base
    (b / "conclusions.jsonl").write_text(
        '{"id":"c1"}\n{"id":"c2","provenance":{}}\n'
        '{"id":"c3","provenance":{"session":null}}\n', encoding="utf-8")
    assert settled.pending(slug, _rows("a"), set()) == ["a"]
