"""marrow.voice:讀伴回覆機械指標與唯讀報表。合成 DB,不碰真資料。"""
import contextlib
import io
import json
import sqlite3

import pytest

from marrow import db, repo, voice

CARD = {"spec": "chara_card_v3", "data": {"name": "鬣狗", "mes_example": "<example>作者:嗯\n鬣狗:菜脯放了二十年還捨不得丟</example>"}}


def test_scan_counts_rules_and_shapes():
    assert voice.scan("我覺得這段太長。你覺得呢？") == {"判斷後補問": 1}
    assert voice.scan("很好。但結尾鬆。") == {"先褒後貶": 1}
    assert voice.scan("「冰箱」不是容器而是墓。——象徵") == {"不是X而是Y": 1, "破折號": 1, "講意義": 1, "引文開頭": 1}
    assert voice.scan("") == {}


def test_closing_quote_stays_with_its_sentence():
    text = "我覺得這段太長。她真的會說「你還好嗎？」"
    assert voice.sentences(text) == ["我覺得這段太長。", "她真的會說「你還好嗎？」"]
    assert voice.metrics(text, "", None, None)["question_end"] is False


def test_copy_ratio():
    assert voice.copy_ratio("菜脯放了二十年", "菜脯放了二十年還在") == 1.0
    assert voice.copy_ratio("完全不同的句子喔", "菜脯放了二十年") == 0.0
    assert voice.copy_ratio("短", "菜脯放了二十年") is None
    assert voice.copy_ratio("菜脯放了二十年", "") is None


def test_metrics_shapes_usage():
    m = voice.metrics("嗯 好喔。為什麼？", "", {"output": 100, "thinking": 80, "duration_ms": 9, "first_delta_ms": 4}, "想")
    assert (m["len"], m["question_end"], m["opening"], m["thinking_share"], m["thinking_chars"],
            m["duration_ms"], m["first_delta_ms"]) == (9, True, "嗯好喔。", 0.8, 1, 9, 4)
    bare = voice.metrics("", "", None, None)
    assert (bare["question_end"], bare["thinking_share"], bare["thinking_chars"]) == (False, None, 0)
    assert voice.metrics("好", "", {"output": 0, "thinking": 0}, None)["thinking_share"] is None


def _db(tmp_path):
    url = f"sqlite:///{tmp_path / 'h.db'}"
    conn = db.connect(url)
    db.migrate(conn, None)
    with conn:
        repo.add_character(conn, "hyena", "builtin", 0)
        v = repo.add_character_version(conn, "hyena", CARD, 0)
        s = repo.ensure_story(conn, "s1", None, 0)
        d1 = repo.ensure_discussion(conn, s, "a", "web", None, 0)
        d2 = repo.ensure_discussion(conn, None, "b", "web", None, 0)
        recipe = {"character_v": v, "retrieved": ["m1", "t1"]}
        usage = {"output": 10, "thinking": 5, "duration_ms": 100, "first_delta_ms": 30}
        repo.add_utterance(conn, d1, 0, "user", "問", 1, "den", [], None)
        repo.add_utterance(conn, d1, 1, "assistant", "菜脯放了二十年。", 2, "den", [], "fp",
                           usage=usage, character="hyena", recipe=recipe)
        repo.replace_reply(conn, d1, 1, text="菜脯放了二十年還捨不得丟吧？", ts=3, usage=usage, recipe=recipe,
                           analysis_fp="fp", thinking="she keeps it\nbecause")
        repo.add_utterance(conn, d1, 2, "assistant", "菜脯放了二十年。", 4, "den", [], "fp",
                           usage=usage, character="hyena", recipe=recipe)
        repo.add_utterance(conn, d1, 3, "assistant", "作者自己改的長長長長長長長長長長長", 5, "den", [], "fp",
                           usage=usage, character="hyena", recipe=recipe)
        repo.edit_reply(conn, d1, 3, "作者改過", 6)
        repo.add_utterance(conn, d2, 0, "assistant", "舊的回覆", 7, "den", [], None)
        repo.add_utterance(conn, d2, 1, "assistant", "別的角色", 8, "den", [], None,
                           character="deer", recipe={"character_v": 9})
    conn.close()
    return url


def _rows(tmp_path):
    with contextlib.closing(db.connect_readonly(_db(tmp_path))) as conn:
        return voice.load(conn)


def test_load_includes_shelved_variants(tmp_path):
    rows = _rows(tmp_path)
    assert [(r["discussion"], r["seq"], r["variant"], r["kept"]) for r in rows] == \
        [(1, 1, 2, True), (1, 1, 1, False), (1, 2, 1, True), (1, 3, 1, True), (2, 0, 1, True), (2, 1, 1, True)]
    kept = rows[0]
    assert (kept["story"], kept["analysis"], kept["retrieved"], kept["card_v"], kept["edited"], kept["thinking"]) == \
        (True, True, 2, 1, False, "she keeps it\nbecause")
    assert rows[1]["thinking"] is None and rows[3]["edited"]
    assert "二十年" in kept["examples"] and rows[4]["examples"] == "" and rows[5]["examples"] == ""


def test_measure_repeat_opening_counts_only_kept_and_filters(tmp_path):
    rows = _rows(tmp_path)
    measured = voice.measure(rows)
    assert [m["repeat_opening"] for m in measured] == [False, None, True, False, False, False]
    assert measured[0]["copy"] > 0.5 and "examples" not in measured[0] and "usage" not in measured[0]
    assert [m["seq"] for m in voice.measure(rows, character="hyena")] == [1, 1, 2, 3]
    assert voice.measure(rows, character="hyena", since_version=2) == []
    assert len(voice.measure(rows, character="deer", since_version=1)) == 1


def test_summarize_skips_edited_and_counts_shelved(tmp_path):
    groups = voice.summarize(voice.measure(_rows(tmp_path)))
    hy = next(g for g in groups if g["character"] == "hyena")
    assert (hy["n"], hy["shelved"], hy["card_v"], hy["story"], hy["question_end"], hy["repeat_opening"],
            hy["thinking_tokens"], hy["first_delta_ms"]) == (3, 1, 1, True, 0.33, 0.5, 5, 30)
    legacy = next(g for g in groups if g["character"] is None)
    assert (legacy["thinking_tokens"], legacy["copy"]) == (None, None)
    assert voice._rate([None]) is None


def test_main_text_report_with_thinking(tmp_path):
    url = _db(tmp_path)
    out = io.StringIO()
    assert voice.main(["--db", url, "--thinking"], out=out) == 0
    text = out.getvalue()
    assert "  thinking: she keeps it\n  because" in text
    assert text.splitlines()[0].startswith("discussion\tseq\tvariant\tkept")
    plain = io.StringIO()
    voice.main(["--db", url], out=plain)
    assert "thinking:" not in plain.getvalue()


def test_main_json_hides_thinking_unless_asked(tmp_path):
    url = _db(tmp_path)
    out = io.StringIO()
    voice.main(["--db", url, "--json", "--character", "hyena", "--since-version", "1"], out=out)
    body = json.loads(out.getvalue())
    assert len(body["rows"]) == 4 and "thinking" not in body["rows"][0] and body["groups"][0]["n"] == 3
    out = io.StringIO()
    voice.main(["--db", url, "--json", "--thinking"], out=out)
    assert json.loads(out.getvalue())["rows"][0]["thinking"] == "she keeps it\nbecause"


def test_since_version_needs_character(tmp_path, capsys):
    with pytest.raises(SystemExit):
        voice.main(["--db", _db(tmp_path), "--since-version", "2"])
    assert "--character" in capsys.readouterr().err


def test_old_or_missing_db_explains(tmp_path):
    err = io.StringIO()
    assert voice.main(["--db", f"sqlite:///{tmp_path / 'nope.db'}"], err=err) == 1
    assert "重啟 den" in err.getvalue()
    old = tmp_path / "old.db"
    with contextlib.closing(sqlite3.connect(old)) as conn:
        conn.execute("CREATE TABLE utterance (discussion_id INTEGER)")
        conn.execute("CREATE TABLE character_version (character_id TEXT, n INTEGER, card TEXT)")
    err = io.StringIO()
    assert voice.main(["--db", f"sqlite:///{old}"], err=err) == 1
    assert "no such" in err.getvalue()


def test_report_never_writes(tmp_path):
    with contextlib.closing(db.connect_readonly(_db(tmp_path))) as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM utterance")
    with contextlib.closing(db.connect_readonly("sqlite:///:memory:")) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
