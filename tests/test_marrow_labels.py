from marrow.labels import label_map, relabel

L = {"b1": "進門", "m2": "破帽與宮字", "t1": "等待"}


def test_label_map_reads_nodes_and_tolerates_odd_shapes():
    a = {"nodes": [{"id": "b1", "label": "進門"}, {"id": 3, "label": "x"}, {"id": "k1"}, "壞"]}
    assert label_map(a) == {"b1": "進門"}
    assert label_map(None) == label_map({}) == label_map({"nodes": "壞"}) == {}


def test_known_ids_become_labels():
    assert relabel("走完了 b1 到 t1,(t1，強度 0.9)", L) == "走完了 〈進門〉 到 〈等待〉,(〈等待〉，強度 0.9)"
    assert relabel("t1、b1 這些", L) == "〈等待〉、〈進門〉 這些"


def test_id_followed_by_its_own_label_is_not_doubled():
    assert relabel("我想聊 m2「破帽與宮字」。", L) == "我想聊 〈破帽與宮字〉。"
    assert relabel("m2「破帽」那句", L) == "〈破帽與宮字〉「破帽」那句"


def test_unknown_ids_and_words_are_left_alone():
    assert relabel("b9 跟 abc1、t1x、mp3、e2e 不動", L) == "b9 跟 abc1、t1x、mp3、e2e 不動"
    assert relabel("t1", {}) == "t1"
