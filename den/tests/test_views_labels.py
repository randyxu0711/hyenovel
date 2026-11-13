"""D1 守門:畫面拿到的文字裡沒有 node id,一律換成那則發言當時讀的分析的標籤。"""
import pytest

from den import views
from marrow import db, repo


def _ana(label):
    return {"nodes": [{"id": "b1", "type": "beat", "label": label, "evidence": []}], "edges": []}


@pytest.fixture
def c():
    conn = db.connect("sqlite:///:memory:")
    db.migrate(conn, None)
    yield conn
    conn.close()


@pytest.fixture
def story(c):
    sid = repo.ensure_story(c, "x1", "標", 0)
    v1, _ = repo.add_source_version(c, sid, "原文", 1.0)
    old, _ = repo.add_artifact(c, sid, v1, "analysis", 1, _ana("舊標"), {}, 1.5)
    v2, _ = repo.add_source_version(c, sid, "二版", 2.0)
    cur, _ = repo.add_artifact(c, sid, v2, "analysis", 1, _ana("新標"), {}, 2.5)
    repo.set_current(c, sid, "analysis", cur)
    d = repo.ensure_discussion(c, sid, "s", "web", None, 3.0)
    say = lambda seq, role, text, fp=None: repo.add_utterance(c, d, seq, role, text, 3.0 + seq, "den", [], fp)
    say(0, "user", "b1 怎麼看")
    say(1, "assistant", "b1 很短", repo.artifact(c, old)["sha256"])
    say(2, "user", "那 b1 呢")
    say(3, "compact", "談了 b1")
    return sid, d


def test_session_turns_use_the_analysis_each_reply_read(c, story):
    texts = [t.get("text") for t in views.session_turns(c, "s")["turns"]]
    assert texts == ["b1 怎麼看", "〈舊標〉 很短", "那 b1 呢", "談了 〈舊標〉"]


def test_transcript_relabels(c, story):
    assert [t["text"] for t in views.transcript(c, "x1")] == ["b1 怎麼看", "〈舊標〉 很短", "那 b1 呢"]


def test_recent_preview_relabels_before_cutting(c, story):
    sid, d = story
    [row] = views.recent_sessions(c, 10, legacy=True)
    assert row["preview"] == "〈舊標〉 很短" and "fp" not in row and "story_id" not in row
    repo.add_utterance(c, d, 9, "assistant", "一" * 58 + "b1", 9.0, "den", [], None)
    assert views.recent_sessions(c, 10, legacy=True)[0]["preview"] == "一" * 58 + "〈新"


def test_author_text_is_never_rewritten(c, story):
    assert views.sessions(c, "x1", legacy=True)[0]["preview"] == "b1 怎麼看"


def test_unbound_session_keeps_text(c):
    d = repo.ensure_discussion(c, None, "free", "web", None, 1.0)
    repo.add_utterance(c, d, 0, "assistant", "b1 是什麼", 1.0, "den", [], None)
    assert views.session_turns(c, "free")["turns"][0]["text"] == "b1 是什麼"
    assert views.recent_sessions(c, 10, legacy=True)[0]["preview"] == "b1 是什麼"


def test_notes_text_relabels(c, story):
    sid, _ = story
    cur = repo.current_artifact(c, sid, "analysis")
    notes = {"read": "b1 收得快", "one_line": None, "points": [
        {"kind": "opinion", "title": "b1", "body": "b1 太短", "question": "b1 要不要長?", "refs": ["b1"], "quotes": []}]}
    nid, _ = repo.add_artifact(c, sid, cur["source_version_id"], "notes", 1, notes, {}, 3.0)
    repo.set_current(c, sid, "notes", nid)
    got = views.work_map(c, "x1")["notes"]
    assert got["read"] == "〈新標〉 收得快" and got["one_line"] is None
    [p] = got["points"]
    assert (p["title"], p["body"], p["question"]) == ("〈新標〉", "〈新標〉 太短", "〈新標〉 要不要長?")
