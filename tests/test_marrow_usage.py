import io
import json

import pytest

from marrow import db, repo, usage

TOK = {"input": 2, "output": 28, "cache_read": 649, "cache_creation": 1512, "thinking": 20}


def call(conn, kind="chat", outcome="ok", tokens=TOK, partial=False, started=10.0, ms=100, fp="fp1", tag=None,
         rate=None, ended=None, model="m", **keys):
    cid = repo.start_call(conn, kind, started, fp, tag=tag, **keys)
    if outcome is not None:
        repo.finish_call(conn, cid, outcome=outcome, ended_at=ended or started + 1, duration_ms=ms, tokens=tokens,
                         tokens_partial=partial, cost_usd=0.01 if tokens else None, model=model, rate_limit=rate)
    return repo.get_call(conn, cid)


@pytest.fixture
def disc(conn):
    d = repo.ensure_discussion(conn, None, "s1", "web", None, 0.0)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "assistant", "答", 1.0, "den", [], None)
    return d


def kinds(conn, rows):
    return [usage.classify(conn, r) for r in rows]


def test_outcomes_map_to_classes(conn):
    rows = [call(conn, outcome=None, tokens=None), call(conn, outcome="gate_rejected"),
            call(conn, outcome="discarded"), call(conn, outcome="cancelled"), call(conn, outcome="timeout"),
            call(conn, outcome="usage-limit"), call(conn, kind="analyst"), call(conn, kind="reviewer")]
    assert kinds(conn, rows) == ["error", "rejected", "unsaved", "cancelled", "error", "error",
                                 "adopted", "adopted"]


def test_null_outcome_is_error_and_unknown(conn):
    row = call(conn, outcome=None)
    [g] = usage.summarize(conn, [row])
    assert g["classes"]["error"] == 1 and g["unknown"] == 1 and g["ms_median"] is None and g["cache_hit"] is None


def test_chat_without_seq_is_unsaved(conn):
    assert usage.classify(conn, call(conn)) == "unsaved"


def test_chat_on_deleted_turn_counts_adopted(conn):
    assert usage.classify(conn, call(conn, discussion_id=99, seq=1, variant=1)) == "adopted"


def test_pick_reply_flips_adoption(conn, disc):
    first = call(conn, discussion_id=disc, seq=1, variant=1)
    repo.replace_reply(conn, disc, 1, text="重說", ts=2.0, usage=None, recipe=None, analysis_fp=None)
    second = call(conn, kind="redo", discussion_id=disc, seq=1, variant=2)
    assert kinds(conn, [first, second]) == ["unselected", "adopted"]
    repo.pick_reply(conn, disc, 1, 1)
    assert kinds(conn, [first, second]) == ["adopted", "unselected"]


def test_compact_and_candidates(conn):
    rows = [call(conn, kind="compact", seq=3), call(conn, kind="compact"),
            call(conn, kind="candidates", character_id="c1"), call(conn, kind="candidate_revise")]
    assert kinds(conn, rows) == ["adopted", "unsaved", "adopted", "unselected"]


def _digest(conn, d, text="摘要", root=None, edited=False, at=5.0):
    return repo.add_digest(conn, d, text, 1, at, root_id=root, edited=edited)


def _bring(conn, d, seq, ids, table="utterance"):
    recipe = {"prior": {"digests": ids, "threads": []}}
    if table == "utterance":
        repo.add_utterance(conn, d, seq, "assistant", "x", 9.0, "den", [], None, recipe=recipe)
    else:
        repo.replace_reply(conn, d, seq, text="y", ts=9.5, usage=None, recipe=None, analysis_fp=None)
        conn.execute("UPDATE utterance_variant SET recipe = ? WHERE discussion_id = ? AND seq = ?",
                     (json.dumps(recipe), d, seq))


def test_digest_adopted_directly_and_not_injected(conn, disc):
    g = _digest(conn, disc)
    row = call(conn, kind="digest", digest_id=g)
    assert usage.classify(conn, row) == "not_injected"
    assert usage.classify(conn, call(conn, kind="digest")) == "unsaved"
    other = repo.ensure_discussion(conn, None, "s2", "web", None, 0.0)
    _bring(conn, other, 0, [g])
    assert usage.classify(conn, row) == "adopted"


def test_digest_adopted_via_edited_copy(conn, disc):
    g = _digest(conn, disc)
    root = repo.digest_by_id(conn, g)["root_id"]
    e = _digest(conn, disc, "作者改的", root=root, edited=True)
    row = call(conn, kind="digest", digest_id=g)
    other = repo.ensure_discussion(conn, None, "s2", "web", None, 0.0)
    _bring(conn, other, 0, [e])
    assert usage.classify(conn, row) == "adopted"


def test_digest_regenerated_not_counted_as_edit(conn, disc):
    g = _digest(conn, disc)
    root = repo.digest_by_id(conn, g)["root_id"]
    newer = _digest(conn, disc, "重摘的", root=root)
    later_edit = _digest(conn, disc, "改重摘的", root=root, edited=True)
    row = call(conn, kind="digest", digest_id=g)
    other = repo.ensure_discussion(conn, None, "s2", "web", None, 0.0)
    _bring(conn, other, 0, [newer, later_edit])
    assert usage.classify(conn, row) == "not_injected"
    assert usage._edited_copies(conn, 999) == []


def test_digest_brought_via_shelved_variant(conn, disc):
    g = _digest(conn, disc)
    repo.add_utterance(conn, disc, 2, "assistant", "沒帶摘要", 9.0, "den", [], None, recipe={"prior": None})
    _bring(conn, disc, 1, [g], table="variant")
    assert usage.classify(conn, call(conn, kind="digest", digest_id=g)) == "adopted"


def test_thinking_not_in_total_and_cache_hit(conn):
    [g] = usage.summarize(conn, [call(conn, kind="analyst"), call(conn, kind="analyst", tokens=None, ms=None)])
    assert g["tokens"]["output"] == 28 and g["tokens"]["thinking"] == 20
    assert g["cache_hit"] == pytest.approx(649 / 2163) and g["unknown"] == 1 and g["ms_median"] == 100
    assert g["n"] == 2 and g["cost_usd"] == pytest.approx(0.01)


def test_partial_marks_group(conn):
    rows = [call(conn, kind="analyst", tokens={"input": 2}, partial=True), call(conn, kind="reviewer")]
    groups = usage.summarize(conn, rows)
    assert [g["partial"] for g in groups] == [True, False]
    text = usage.render(groups, [], None, "kind")
    assert "≥2" in text.splitlines()[1] and "≥" not in text.splitlines()[2]


def test_by_prompt_and_tag(conn):
    rows = [call(conn, kind="analyst", fp="a"), call(conn, kind="analyst", fp="b"),
            call(conn, kind="analyst", fp="b", tag="m6-on")]
    assert [g["group"] for g in usage.summarize(conn, rows, "prompt")] == ["analyst@a", "analyst@b"]
    assert [(g["group"], g["n"]) for g in usage.summarize(conn, rows, "tag")] == [("-", 2), ("m6-on", 1)]


def test_effects_counts_chat_signals(conn, disc):
    row = call(conn, discussion_id=disc, seq=1, variant=1)
    call(conn, discussion_id=disc, outcome="timeout")
    repo.set_voice(conn, disc, 1, 3.0)
    repo.set_reaction(conn, disc, 1, "misread", None, 3.0)
    repo.edit_reply(conn, disc, 1, "改過", 3.0)
    repo.add_memory(conn, "author", "記住", 3.0, quote="問", discussion_id=disc, seq=1)
    [e] = usage.effects(conn, [row])
    assert e == {"group": "chat", "n": 1, "signals": {"edited": 1, "mark:misread": 1, "remembered": 1, "voice": 1}}


def test_effects_counts_digest_signals(conn, disc):
    g = _digest(conn, disc, at=5.0)
    root = repo.digest_by_id(conn, g)["root_id"]
    _digest(conn, disc, "改", root=root, edited=True, at=6.0)
    a = repo.add_candidate(conn, disc, 0, "問", "記這個", "author", 5.0)
    b = repo.add_candidate(conn, disc, 0, "問", "記那個", "author", 5.0)
    a2 = repo.add_candidate(conn, disc, 0, "問", "也記", "author", 5.0)
    repo.add_candidate(conn, disc, 0, "問", "還沒處理", "author", 5.0)
    repo.resolve_candidate(conn, a, "saved", 7.0)
    repo.resolve_candidate(conn, a2, "saved", 7.0)
    repo.resolve_candidate(conn, b, "skipped", 7.0)
    plain = _digest(conn, disc, "另一份", at=8.0)
    rows = [call(conn, kind="digest", digest_id=g), call(conn, kind="digest", digest_id=12345),
            call(conn, kind="digest", digest_id=plain),
            call(conn, kind="analyst")]
    [e] = usage.effects(conn, rows, "prompt")
    assert e == {"group": "digest@fp1", "n": 3, "signals": {"digest_edited": 1, "saved": 1, "skipped": 1}}


def test_latest_rate_limit(conn):
    rl = {"five_hour": {"utilization": 0.22, "resetsAt": 100}, "status": "allowed"}
    rows = [call(conn, rate={"status": "x"}, ended=50.0), call(conn, rate=rl, ended=80.0), call(conn),
            call(conn, outcome=None)]
    assert usage.latest_rate_limit(rows) == (80.0, rl)
    assert usage.latest_rate_limit([]) is None


def test_render_text(conn, disc):
    row = call(conn, discussion_id=disc, seq=1, variant=1)
    repo.set_reaction(conn, disc, 1, "stopped", None, 3.0)
    rl = {"five_hour": {"utilization": 0.22, "resetsAt": 100}, "seven_day": {"utilization": None}, "status": "a"}
    text = usage.render(usage.summarize(conn, [row], "prompt"), usage.effects(conn, [row], "prompt"), (80.0, rl), "prompt")
    lines = text.splitlines()
    assert lines[0].startswith("5 小時 22%(重置 ") and "7 天 ?(重置 ?)" in lines[0] and "觀測於" in lines[0]
    assert lines[2].split("\t")[:2] == ["種類@prompt", "次數"] and "未帶入" in lines[2]
    assert "30%" in lines[3] and "100ms" in lines[3]
    assert lines[-1] == "chat@fp1\tn=1\t停下 1/1"
    assert usage._signal_label("mark:other") == "other" and usage._signal_label("custom") == "custom"
    assert usage.render([], [], None, "tag") == "標籤\t次數\t輸入\t輸出\tcache讀\tcache寫\tthinking\t美元(參考)\t" \
        "採用\t未選用\t未帶入\t退回\t中止\t錯誤\t未保存\t用量不明\tcache命中\t延遲中位\n(這段期間沒有呼叫)\n"


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path}/u.db"
    c = db.connect(u)
    db.migrate(c, tmp_path / "u.db")
    with c:
        call(c, kind="analyst", started=1000.0, rate={"five_hour": {"utilization": 0.5}})
        call(c, kind="analyst", started=10.0)
    c.close()
    return u


def test_main_json_and_text(url):
    out = io.StringIO()
    assert usage.main(["--db", url, "--json", "--since", "0.05"], out=out, now=lambda: 1000.0 + 3600) == 0
    got = json.loads(out.getvalue())
    assert [g["n"] for g in got["groups"]] == [1] and got["rate_limit"]["at"] == 1001.0 and got["effects"] == []
    out = io.StringIO()
    assert usage.main(["--db", url, "--by", "tag"], out=out, now=lambda: 1000.0) == 0
    assert out.getvalue().splitlines()[3].startswith("-\t2\t")


def test_main_json_without_rate_limit(tmp_path):
    u = f"sqlite:///{tmp_path}/e.db"
    c = db.connect(u)
    db.migrate(c, tmp_path / "e.db")
    c.close()
    out = io.StringIO()
    assert usage.main(["--db", u, "--json"], out=out) == 0
    assert json.loads(out.getvalue())["rate_limit"] is None


def test_main_reports_missing_table(tmp_path):
    u = f"sqlite:///{tmp_path}/old.db"
    c = db.connect(u)
    c.execute("CREATE TABLE x (a)")
    c.commit()
    c.close()
    err = io.StringIO()
    assert usage.main(["--db", u], err=err) == 1
    assert "讀不到用量帳本" in err.getvalue()


def _kinds_in_schema(tmp_path) -> list[str]:
    import re
    c = db.connect(f"sqlite:///{tmp_path}/k.db")
    db.migrate(c, tmp_path / "k.db")
    sql = c.execute("SELECT sql FROM sqlite_master WHERE name = 'llm_call'").fetchone()[0]
    c.close()
    m = re.search(r"kind IN \(([^)]*)\)", sql)
    return re.findall(r"'([^']+)'", m.group(1)) if m else []


def test_every_kind_has_category(tmp_path):
    found = _kinds_in_schema(tmp_path)
    assert len(found) >= 8
    assert [k for k in found if usage.category(k) == "other"] == []


def test_unknown_kind_is_other():
    assert usage.category("future_kind") == "other"
    assert usage.CATEGORY_ORDER[-1] == "other" and set(usage.CATEGORIES.values()) < set(usage.CATEGORY_ORDER)


def test_by_character_work_model_groups(conn):
    rows = [call(conn, character_id="hyena", character_v=3, story_id=1, effort="high"),
            call(conn, character_id="hyena", character_v=4, story_id=1, model="m2"),
            call(conn, kind="analyst", model=None)]
    assert [g["group"] for g in usage.summarize(conn, rows, by="character")] == ["-", "hyena@3", "hyena@4"]
    assert [g["group"] for g in usage.summarize(conn, rows, by="work")] == ["-", "1"]
    assert [g["group"] for g in usage.summarize(conn, rows, by="model")] == ["-/-", "m/high", "m2/-"]


@pytest.mark.parametrize("by,head", [("character", "讀伴@卡版"), ("work", "作品"), ("model", "模型/effort")])
def test_cli_by_new_keys_text(url, by, head):
    out = io.StringIO()
    assert usage.main(["--db", url, "--by", by], out=out, now=lambda: 1000.0) == 0
    assert head in out.getvalue()
