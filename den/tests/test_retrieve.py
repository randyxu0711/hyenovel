from den import retrieve

SOURCE = "她把傘收進門縫。" + "風" * 200 + "他把燈關了。" + "雨" * 200 + "海水漫過門檻。"


def _node(nid, label, *quotes, note="細", type_="motif"):
    return {"id": nid, "type": type_, "label": label, "note": note, "intensity": None,
            "evidence": [{"quote": q, "note": None} for q in quotes]}


ANALYSIS = {
    "nodes": [_node("m1", "傘", "她把傘收進門縫"), _node("m2", "燈", "他把燈關了"),
              _node("m3", "海水", "海水漫過門檻"), _node("c1", "她", note=None, type_="character")],
    "edges": [{"type": "serves", "from": "m1", "to": "m2", "note": None}],
}


def _ids(**kw):
    args = {"quotes": (), "message": "", "last_reply": "", **kw}
    return [n["id"] for n in retrieve.pick(ANALYSIS, SOURCE, **args)]


def test_no_analysis_picks_nothing():
    assert retrieve.pick(None, SOURCE, quotes=["他把燈關了"], message="", last_reply="") == []


def test_carried_quote_finds_node_with_overlapping_evidence():
    assert _ids(quotes=["他把燈關了"]) == ["m2"]


def test_quote_in_message_counts():
    assert _ids(message="「他把燈關了」這句呢") == ["m2"]


def test_quote_not_in_source_is_not_an_anchor():
    assert _ids(message="這很「厲害」的感覺") == []


def test_near_window_is_inclusive_at_the_limit_and_excludes_beyond():
    gap = "。" * retrieve.NEAR
    src = "甲甲甲" + gap + "乙乙乙" + "。" + gap + "丙丙丙"
    a = {"nodes": [_node("a", "x", "甲甲甲"), _node("c", "y", "丙丙丙")], "edges": []}
    got = retrieve.pick(a, src, quotes=["乙乙乙"], message="", last_reply="")
    assert [n["id"] for n in got] == ["a"]


def test_nearer_node_comes_first():
    src = "甲甲" + "。" * 50 + "乙乙" + "。" * 10 + "丙丙"
    a = {"nodes": [_node("far", "x", "甲甲"), _node("close", "y", "丙丙")], "edges": []}
    got = retrieve.pick(a, src, quotes=["乙乙"], message="", last_reply="")
    assert [n["id"] for n in got] == ["close", "far"]


def test_label_in_message_counts_but_single_char_label_does_not():
    assert _ids(message="海水那段") == ["m3"]
    assert _ids(message="傘那段") == []


def test_previous_reply_quote_counts():
    assert _ids(last_reply="我停在「他把燈關了」") == ["m2"]


def test_label_in_previous_reply_does_not_count():
    assert _ids(last_reply="海水那段") == []


def test_priority_order_and_dedupe():
    got = _ids(quotes=["他把燈關了"], message="海水,「他把燈關了」", last_reply="「她把傘收進門縫」")
    assert got == ["m2", "m3", "m1"]


def test_author_quote_outranks_label_outranks_previous_reply_at_the_cap(monkeypatch):
    monkeypatch.setattr(retrieve, "MAX_NODES", 2)
    assert _ids(quotes=["他把燈關了"], message="海水", last_reply="「她把傘收進門縫」") == ["m2", "m3"]


def test_cap_applies_to_nodes_sharing_one_quote():
    a = {"nodes": [_node(f"m{i}", f"標{i}", "他把燈關了") for i in range(retrieve.MAX_NODES + 3)], "edges": []}
    assert len(retrieve.pick(a, SOURCE, quotes=["他把燈關了"], message="", last_reply="")) == retrieve.MAX_NODES


def test_null_evidence_and_edges_are_tolerated():
    a = {"nodes": [{"id": "c1", "type": "character", "label": "阿海", "note": None, "evidence": None}], "edges": None}
    assert [n["id"] for n in retrieve.pick(a, SOURCE, quotes=(), message="阿海呢", last_reply="")] == ["c1"]


def test_exact_match_on_later_quote_beats_distant_neighbour_of_first_quote(monkeypatch):
    monkeypatch.setattr(retrieve, "MAX_NODES", 1)
    src = "甲甲" + "。" * 100 + "乙乙" + "。" * 300 + "丙丙"
    a = {"nodes": [_node("far", "x", "乙乙"), _node("exact", "y", "丙丙")], "edges": []}
    got = retrieve.pick(a, src, quotes=["甲甲", "丙丙"], message="", last_reply="")
    assert [n["id"] for n in got] == ["exact"]


def test_previous_turn_nodes_come_last_and_unknown_ids_drop():
    assert _ids(previous=["m1", "gone"]) == ["m1"]
    assert _ids(message="海水", previous=["m1"]) == ["m3", "m1"]


def test_blank_evidence_quote_gives_no_position():
    a = {"nodes": [{"id": "x", "type": "motif", "label": "z", "note": None,
                    "evidence": [{"quote": "  ", "note": None}]}], "edges": []}
    assert retrieve.pick(a, SOURCE, quotes=["她把傘"], message="", last_reply="") == []


def test_render_skips_dangling_edges():
    a = {"nodes": [ANALYSIS["nodes"][0]], "edges": [{"type": "serves", "from": "m1", "to": "gone", "note": None},
                                                    {"type": "serves", "from": "gone", "to": "m1", "note": None}]}
    assert "serves" not in retrieve.render(a, a["nodes"])


def test_render_empty_when_nothing_picked():
    assert retrieve.render(ANALYSIS, []) == ""


def test_render_has_note_quotes_and_one_hop_edges_both_ways():
    m1, m2 = ANALYSIS["nodes"][0], ANALYSIS["nodes"][1]
    out = retrieve.render(ANALYSIS, [m1])
    assert "- motif 傘:細" in out and "「她把傘收進門縫」" in out
    assert "serves → motif 燈" in out and "不要原樣念給作者" in out
    assert "serves ← motif 傘" in retrieve.render(ANALYSIS, [m2])


def test_render_node_without_note_or_evidence():
    out = retrieve.render(ANALYSIS, [ANALYSIS["nodes"][3]])
    assert "- character 她\n" in out + "\n" and "「" not in out
