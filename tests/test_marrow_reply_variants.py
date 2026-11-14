from marrow import repo


def _turns(conn):
    s = repo.ensure_story(conn, "s1", None, 0)
    d = repo.ensure_discussion(conn, s, "sess", "web", None, 0)
    repo.add_utterance(conn, d, 0, "user", "問", 1.0, "den", [], None)
    repo.add_utterance(conn, d, 1, "assistant", "一", 2.0, "den", [], "fp1", usage={"in": 1},
                       character="hyena", recipe={"r": 1})
    return s, d


def _replace(conn, d, text, ts):
    return repo.replace_reply(conn, d, 1, text=text, ts=ts, usage={"in": ts}, recipe={"r": ts}, analysis_fp=f"fp{ts}")


def _all_text(conn):
    return ([r[0] for r in conn.execute("SELECT text FROM utterance")]
            + [r[0] for r in conn.execute("SELECT text FROM utterance_variant")])


def test_replace_shelves_current_and_numbers_versions(conn):
    _, d = _turns(conn)
    assert _replace(conn, d, "二", 3.0) == 2
    assert _replace(conn, d, "三", 4.0) == 3
    u = repo.utterance(conn, d, 1)
    assert (u["text"], u["variant"], u["usage"], u["recipe"], u["analysis_fp"], u["edited_at"]) == \
        ("三", 3, {"in": 4.0}, {"r": 4.0}, "fp4.0", None)
    assert len(repo.utterances(conn, d)) == 2
    shelved = {r["n"]: repo._row(r) for r in conn.execute("SELECT * FROM utterance_variant")}
    assert shelved[1]["text"] == "一" and shelved[1]["usage"] == {"in": 1} and shelved[1]["recipe"] == {"r": 1}
    assert repo.variant_counts(conn, d) == {1: 3}


def test_pick_swaps_all_version_columns(conn):
    _, d = _turns(conn)
    repo.edit_reply(conn, d, 1, "一改", 2.5)
    _replace(conn, d, "二", 3.0)
    assert repo.pick_reply(conn, d, 1, 1)
    u = repo.utterance(conn, d, 1)
    assert (u["text"], u["variant"], u["ts"], u["usage"], u["recipe"], u["analysis_fp"], u["edited_at"]) == \
        ("一改", 1, 2.0, {"in": 1}, {"r": 1}, "fp1", 2.5)
    assert [r[0] for r in conn.execute("SELECT n FROM utterance_variant")] == [2]
    assert repo.pick_reply(conn, d, 1, 1)
    assert not repo.pick_reply(conn, d, 1, 9)
    assert _replace(conn, d, "三", 4.0) == 3


def test_edit_overwrites_without_keeping_old_text(conn):
    _, d = _turns(conn)
    assert not repo.edit_reply(conn, d, 1, "一", 5.0)
    assert repo.utterance(conn, d, 1)["edited_at"] is None
    assert repo.edit_reply(conn, d, 1, "新", 5.0)
    u = repo.utterance(conn, d, 1)
    assert (u["text"], u["edited_at"], u["ts"], u["variant"], u["recipe"]) == ("新", 5.0, 2.0, 1, {"r": 1})
    assert "一" not in _all_text(conn)


def test_marks_follow_the_version(conn):
    _, d = _turns(conn)
    repo.set_reaction(conn, d, 1, "misread", None, 1.0)
    repo.set_reaction(conn, d, 1, "stopped", "c", 1.5)
    repo.set_voice(conn, d, 1, 2.0)
    repo.set_voice(conn, d, 1, 3.0)
    assert repo.reactions(conn, d) == {1: {"mark": "stopped", "comment": "c"}}
    assert repo.voice_marks(conn, d) == {1}
    _replace(conn, d, "二", 3.0)
    assert repo.reactions(conn, d) == {} and repo.voice_marks(conn, d) == set()
    repo.pick_reply(conn, d, 1, 1)
    assert repo.reactions(conn, d) == {1: {"mark": "stopped", "comment": "c"}} and repo.voice_marks(conn, d) == {1}
    repo.clear_reaction(conn, d, 1)
    repo.clear_voice(conn, d, 1)
    assert repo.reactions(conn, d) == {} and repo.voice_marks(conn, d) == set()


def test_voice_samples(conn):
    s, d = _turns(conn)
    other = repo.ensure_discussion(conn, s, "other", "web", None, 0)
    repo.add_utterance(conn, other, 0, "assistant", "先開口", 1.0, "den", [], None, character="hyena")
    repo.add_utterance(conn, other, 1, "assistant", "鹿說", 2.0, "den", [], None, character="deer")
    for seq, ts in ((0, 5.0), (1, 6.0)):
        repo.set_voice(conn, other, seq, ts)
    repo.set_voice(conn, d, 1, 4.0)
    assert repo.voice_samples(conn, "hyena", None) == [
        {"text": "先開口", "prompt": None, "story_id": s, "marked_at": 5.0},
        {"text": "一", "prompt": "問", "story_id": s, "marked_at": 4.0}]
    assert [x["text"] for x in repo.voice_samples(conn, "hyena", d)] == ["先開口"]
    repo.edit_reply(conn, d, 1, "改後", 7.0)
    assert repo.voice_samples(conn, "hyena", other)[0]["text"] == "改後"
    _replace(conn, d, "二", 8.0)
    assert repo.voice_samples(conn, "hyena", other) == []


def test_delete_discussion_removes_versions_and_marks(conn):
    _, d = _turns(conn)
    repo.set_reaction(conn, d, 1, "misread", None, 1.0)
    repo.set_voice(conn, d, 1, 1.0)
    _replace(conn, d, "二", 3.0)
    repo.set_voice(conn, d, 1, 4.0)
    repo.delete_discussion(conn, d)
    for t in ("utterance_variant", "voice_mark", "reaction", "utterance"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_thinking_follows_its_variant(conn):
    _, d = _turns(conn)
    repo.replace_reply(conn, d, 1, text="二", ts=3.0, usage=None, recipe=None, analysis_fp=None, thinking="想二")
    assert repo.utterance(conn, d, 1)["thinking"] == "想二"
    assert repo.pick_reply(conn, d, 1, 1)
    assert repo.utterance(conn, d, 1)["thinking"] is None
    assert repo.pick_reply(conn, d, 1, 2)
    repo.edit_reply(conn, d, 1, "改", 5.0)
    u = repo.utterance(conn, d, 1)
    assert (u["text"], u["thinking"]) == ("改", "想二")
