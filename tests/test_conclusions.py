"""結論正本(conclusions.jsonl)的閘門與蓋章 —— 確定性層,100% 覆蓋。

閘門有兩道,缺一不可:
  ① schema —— 結構對不對
  ② 逐字引文 —— 引的話真的在原文裡嗎
第二道是這整個記憶系統的存亡關鍵:記憶若能挾帶不存在的原文,它就是污染源不是資產。
"""
import json

import pytest

import conclusions


@pytest.fixture
def base(story, monkeypatch):
    """沿用 tests/conftest.py 的 story fixture(tmp_path 造 stories/mini),
    另把 conclusions 的 ROOT/STORIES 指過去。

    刻意在這裡指、不改 conftest:append() 會**真的寫檔**,萬一路徑沒被導向就是往
    使用者的創作裡寫。安全帶要綁在會開槍的那把槍上,不是綁在共用 fixture 裡。
    目前也只有這一份測試碰 conclusions,改 conftest 是替不存在的第二個呼叫者鋪路。"""
    slug, b = story
    monkeypatch.setattr(conclusions, "ROOT", b.parent.parent)
    monkeypatch.setattr(conclusions, "STORIES", b.parent)
    return slug, b


SOURCE_QUOTE = "他把燈關了。"     # 逐字存在於 tests/fixtures/mini/source.md


def _draft(kind="judgment", text="收尾太快", refs=("e1",), quotes=(SOURCE_QUOTE,)):
    return {"kind": kind, "text": text, "refs": list(refs), "quotes": list(quotes)}


# ── parse_drafts:LLM 吐的是文字,不是檔案 ────────────────────────────
def test_parse_drafts_plain_array():
    got, err = conclusions.parse_drafts('[{"kind":"judgment","text":"x"}]')
    assert err is None and got == [{"kind": "judgment", "text": "x"}]


def test_parse_drafts_strips_code_fence():
    """LLM 幾乎一定會包 ```json —— 這不是它的錯,是我們該接住。"""
    got, err = conclusions.parse_drafts('```json\n[{"kind":"question","text":"x"}]\n```')
    assert err is None and got[0]["kind"] == "question"


def test_parse_drafts_bare_fence():
    got, err = conclusions.parse_drafts('```\n[]\n```')
    assert err is None and got == []


def test_parse_drafts_fence_without_closing():
    """圍欄開了但沒關 —— 不強求收尾對稱,能剝就剝、不能剝就照樣丟給 json.loads。"""
    got, err = conclusions.parse_drafts('```json\n[]')
    assert err is None and got == []


def test_parse_drafts_rejects_non_json():
    got, err = conclusions.parse_drafts("我覺得這篇收尾太快了。")
    assert got == [] and err is not None and "JSON" in err


def test_parse_drafts_rejects_non_array():
    got, err = conclusions.parse_drafts('{"kind":"judgment"}')
    assert got == [] and err is not None and "陣列" in err


def test_parse_drafts_strips_leading_preamble():
    """minor 9:LLM 有時會在 JSON 陣列前加一句開場白(「以下是結論:」)——
    跟圍欄一樣可以預期會發生,不該燒一次付費回合換回一句「不是合法 JSON」。"""
    got, err = conclusions.parse_drafts('以下是結論:\n[{"kind":"judgment","text":"x"}]')
    assert err is None and got == [{"kind": "judgment", "text": "x"}]


def test_parse_drafts_rejects_non_json_even_with_brackets():
    """退化保護:就算文字裡剛好有 [ ] ,切出來的東西還是壞 JSON 就老實回錯,
    不能半信半疑放行成看起來合法的東西。"""
    got, err = conclusions.parse_drafts("我覺得 [這篇] 收尾太快了。")
    assert got == [] and err is not None and "JSON" in err


# ── stamp:確定性層蓋章 ──────────────────────────────────────────────
def test_stamp_fills_all_derived_fields():
    r = conclusions.stamp(_draft(), idx=3, ts=100.0, session="abc", turns=[0, 4], fp="deadbeef")
    assert r["id"] == "c0003", "id 序號補零到四位"
    assert r["ts"] == 100.0 and r["valid_from"] == 100.0
    assert r["invalidated_at"] is None, "P1 一律 null;失效標記是 P2 的事"
    assert r["provenance"] == {"session": "abc", "turns": [0, 4], "analysis_fp": "deadbeef"}
    assert r["kind"] == "judgment" and r["refs"] == ["e1"]


def test_stamp_tolerates_missing_draft_fields():
    """草稿缺欄位不在這裡炸 —— 讓 schema 閘門去報清楚的錯。"""
    r = conclusions.stamp({}, idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert r["kind"] is None and r["refs"] == [] and r["quotes"] == []


def test_stamp_does_not_explode_scalar_quotes():
    """critical:quotes 給成純量字串(LLM 格式失手)不能被 list() 拆成單字元陣列 ——
    那樣每個單字元都會輕易通過 viz.locate,一句捏造引文就混進正本。
    形狀錯要原樣照抄,讓 schema 閘門(quotes 必須是 array)誠實地擋下。"""
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": ["e1"],
                            "quotes": "他等他。"}, idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert r["quotes"] == "他等他。", "原樣照抄,不被 list() 拆成 ['他','等','他','。']"


def test_stamp_does_not_explode_scalar_refs():
    """important:refs 給成純量字串同樣不能被 list() 拆成單字元 node id。"""
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": "e1",
                            "quotes": []}, idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert r["refs"] == "e1", "原樣照抄,不被 list() 拆成 ['e','1']"


# ── validate:兩道閘門 ───────────────────────────────────────────────
def test_validate_accepts_good_record(base):
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert conclusions.validate([r], src) == []


def test_validate_rejects_bad_kind(base):
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(kind="opinion"), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and "kind" in errs[0]


def test_validate_rejects_hallucinated_quote(base):
    """整個記憶系統的存亡閘門:引文必須真的在原文裡。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(quotes=("他把整座城市關了。",)), idx=1, ts=1.0,
                          session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and "找不到" in errs[0]


def test_validate_rejects_scalar_quotes(base):
    """critical 端到端:quotes 給成純量字串,經 stamp() 誠實照抄後,要被 schema 閘門擋下 ——
    而不是被拆成單字元陣列後每個字都通過 viz.locate。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": ["e1"], "quotes": "他等他。"},
                          idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs, "純量字串 quotes 必須被擋下,不能悄悄放行"
    assert not any("找不到" in e for e in errs), "不該退化成逐字比對,應該是型別錯"


def test_validate_rejects_scalar_refs(base):
    """important 端到端:refs 給成純量字串,經 stamp() 誠實照抄後要被 schema 擋下。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": "e1", "quotes": []},
                          idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("refs" in e for e in errs)


def test_validate_rejects_empty_quote_string(base):
    """minor 1:schema 對 quotes 的每一項要求 minLength 1 ——
    否則 "" 會因為 viz.locate("", source) 永遠回 (0,0) 而被誤判定位成功。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(quotes=("",)), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("quotes" in e for e in errs)


def test_validate_rejects_whitespace_only_quote(base):
    """important(Fix pass 3):minLength 1 擋得住字面空字串,但擋不住 " " 這種
    全是空白字元的引文 —— viz.locate 的第三層(忽略空白)把非空白字元組 pattern,
    引文全是空白時 generator 為空 → 組出空 pattern → 在位置 0 無條件命中,等於
    「定位成功」。schema 補 pattern: \\S(至少一個非空白字元)在這道之前擋下。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(quotes=(" ",)), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("quotes" in e for e in errs)
    assert not any("找不到" in e for e in errs), "不該退化成逐字比對後才發現,應該是 schema 型別/格式錯"


def test_validate_rejects_fullwidth_whitespace_quote(base):
    """同上,全形空白(U+3000)也是空白字元,一樣要被擋。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(quotes=("　",)), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("quotes" in e for e in errs)


def test_validate_does_not_crash_on_malformed_quotes(base):
    """minor 2:validate() 是公開介面,下一個呼叫者(server/discuss.py)不一定會先過 stamp()。
    餵進畸形 quotes(None)不該讓 for 迴圈拋未捕捉的 TypeError,應該回一份錯誤清單。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    r["quotes"] = None
    errs = conclusions.validate([r], src)  # 不炸就是過
    assert errs, "quotes 型別錯,schema 閘門要有意見"


def test_validate_rejects_non_string_quote_element(base):
    """quotes 是 list 但裡面混了非字串元素(如 [123])—— LLM 自由文字輸出完全可能吐出
    這種形狀。viz.locate 需要字串,拿非字串去呼叫會炸 AttributeError;validate() 必須
    在呼叫前擋下,誠實記一筆錯誤,而不是讓 append() 炸穿到呼叫者(下一個 task 是
    server/discuss.py 的 distill())。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    r["quotes"] = [123]
    errs = conclusions.validate([r], src)  # 不炸就是過
    assert errs and any("非字串" in e for e in errs)


def test_validate_rejects_mixed_type_quotes_list(base):
    """quotes 是 list,裡面一個合法引文混一個非字串 —— 確認不會因為前面有合法元素
    就整批誤放行,也不會在處理到非字串元素時炸例外。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    r["quotes"] = [SOURCE_QUOTE, 123]
    errs = conclusions.validate([r], src)  # 不炸就是過
    assert errs and any("非字串" in e for e in errs)


def test_validate_rejects_nested_list_quotes(base):
    """quotes 裡的元素本身是 list(如 [["他把燈關了。"]])—— 巢狀形狀一樣不是字串,
    不能被拿去呼叫 viz.locate,要被誠實地記一筆型別錯,不能被輕易「定位成功」。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    r["quotes"] = [[SOURCE_QUOTE]]
    errs = conclusions.validate([r], src)  # 不炸就是過
    assert errs and any("非字串" in e for e in errs)
    assert not any("找不到" in e for e in errs), "不該退化成逐字比對"


def test_validate_rejects_dict_shaped_quotes(base):
    """quotes 給成 dict(形狀完全錯,既不是純量也不是陣列)—— stamp() 的 _as_list()
    對非 list/tuple 原樣照抄,dict 會抵達這裡,schema 的 array 型別要擋下。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": ["e1"],
                            "quotes": {"q": SOURCE_QUOTE}},
                          idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)  # 不炸就是過
    assert errs and any("quotes" in e for e in errs)


def test_validate_rejects_nested_list_refs(base):
    """refs 同根因:元素是 list(如 [["e1"]])一樣要被 schema 擋下,不是被 list()
    拆開或悄悄接受。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": [["e1"]], "quotes": []},
                          idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("refs" in e for e in errs)


def test_validate_rejects_dict_shaped_refs(base):
    """refs 給成 dict —— 同樣原樣照抄後由 schema 擋下。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp({"kind": "judgment", "text": "x", "refs": {"r": "e1"}, "quotes": []},
                          idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src)
    assert errs and any("refs" in e for e in errs)


def test_validate_allows_empty_quotes(base):
    """有些結論(尤其 question)本來就沒有可引的句子 —— 不強迫湊。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(kind="question", quotes=()), idx=1, ts=1.0,
                          session="a", turns=[0, 0], fp="f")
    assert conclusions.validate([r], src) == []


# ── refs 落點:結論指到的 node 真的存在嗎 ────────────────────────────
# 引文閘門驗「這句話原文裡有」,這道驗「這個 node id 圖裡有」。同一個問題的兩半。
# 刻意在**寫入時**驗而不是等 P2 檢索時驗:conclusions.jsonl 是 append-only 正本,
# 寫進去的壞 refs 之後改不掉(P2 的 invalidated_at 只能作廢整條結論,不能修欄位)。
def test_validate_rejects_unknown_ref(base):
    """LLM 完全可能吐出一個看起來很合理但圖裡不存在的 node id(如 t9)。
    P2 的 anchor-expand 沿 refs 走邊 BFS,壞 refs 會靜默落空 —— 那時已經來不及。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(refs=("e1", "t9")), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    errs = conclusions.validate([r], src, {"b1", "k1", "e1"})
    assert errs and any("t9" in e for e in errs)
    assert not any("e1" in e for e in errs), "存在的那個不該被連坐"


def test_validate_accepts_known_refs(base):
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(refs=("e1", "k1")), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert conclusions.validate([r], src, {"b1", "k1", "e1"}) == []


def test_validate_skips_ref_check_when_ids_unknown(base):
    """known_ids=None = 「無從得知」(沒有 analysis.json / 讀不了),不是「一個都沒有」。
    這種時候放行 —— 不會因為讀不到圖就把一整局討論的結論全擋掉。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    r = conclusions.stamp(_draft(refs=("t9",)), idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    assert conclusions.validate([r], src) == []


def test_validate_ref_check_survives_malformed_refs(base):
    """refs 形狀壞掉(純量字串 / 元素是 list)時,這道檢查不能自己炸:
    純量字串會被逐字元檢查、巢狀 list 拿去做集合查找會炸 unhashable TypeError。
    形狀錯本來就有 schema 擋,這裡只要「不炸、不誤報」。"""
    slug, b = base
    src = (b / "source.md").read_text(encoding="utf-8")
    scalar = conclusions.stamp({"kind": "judgment", "text": "x", "refs": "e1", "quotes": []},
                               idx=1, ts=1.0, session="a", turns=[0, 0], fp="f")
    nested = conclusions.stamp({"kind": "judgment", "text": "x", "refs": [["e1"]], "quotes": []},
                               idx=2, ts=1.0, session="a", turns=[0, 0], fp="f")
    for r in (scalar, nested):
        errs = conclusions.validate([r], src, {"e1"})   # 不炸就是過
        assert errs and any("refs" in e for e in errs), "由 schema 擋下型別錯"
        assert not any("沒有這個 node id" in e for e in errs), "形狀錯不該退化成落點錯"


def test_node_ids_reads_analysis(base):
    slug, b = base
    assert conclusions.node_ids(slug) == {"b1", "k1", "e1", "t1"}


def test_node_ids_missing_analysis(base):
    """沒有 analysis.json → None(無從得知),不是 set()(驗了但一個都沒有)。
    兩者混用會讓「還沒分析的篇」的結論被整批擋掉。"""
    slug, b = base
    (b / "analysis.json").unlink()
    assert conclusions.node_ids(slug) is None


def test_node_ids_survives_read_failure(base):
    """analysis.json 被換成目錄(TOCTOU)—— 同 analysis_fp,無從得知不是錯誤。"""
    slug, b = base
    p = b / "analysis.json"
    p.unlink()
    p.mkdir()
    assert conclusions.node_ids(slug) is None


def test_node_ids_survives_broken_json(base):
    slug, b = base
    (b / "analysis.json").write_text("{壞掉的 JSON", encoding="utf-8")
    assert conclusions.node_ids(slug) is None


def test_node_ids_survives_wrong_shape(base):
    """analysis.json 是合法 JSON 但形狀不對(頂層是陣列 / 沒有 nodes)——
    一樣是「無從得知」,不能當成「圖是空的」而把所有 refs 打成壞落點。"""
    slug, b = base
    p = b / "analysis.json"
    p.write_text("[]", encoding="utf-8")
    assert conclusions.node_ids(slug) is None
    p.write_text('{"slug":"mini"}', encoding="utf-8")
    assert conclusions.node_ids(slug) is None


def test_node_ids_skips_malformed_nodes(base):
    """nodes 裡混了非物件、或 id 不是字串的項 —— 跳過就好,不炸。"""
    slug, b = base
    p = b / "analysis.json"
    p.write_text(json.dumps({"nodes": ["不是物件", {"type": "theme"}, {"id": 123}, {"id": "t1"}]}),
                 encoding="utf-8")
    assert conclusions.node_ids(slug) == {"t1"}


def test_append_rejects_unknown_ref_all_or_nothing(base):
    """端到端:refs 指到圖裡沒有的 node → 整批不寫。"""
    slug, b = base
    n, errs = conclusions.append(slug, [_draft(), _draft(refs=("t9",))], session="a", turns=[0, 0])
    assert n == 0 and errs and any("t9" in e for e in errs)
    assert conclusions.load(slug) == [], "好的那筆也不該落地"


# ── analysis_fp ─────────────────────────────────────────────────────
def test_analysis_fp_stable_and_changes(base):
    slug, b = base
    fp1 = conclusions.analysis_fp(slug)
    assert len(fp1) == 40, "sha1 十六進位 40 字"
    assert conclusions.analysis_fp(slug) == fp1, "沒動就該一樣"
    d = json.loads((b / "analysis.json").read_text(encoding="utf-8"))
    d["nodes"].append({"id": "zz", "type": "theme", "label": "新加的", "evidence": []})
    (b / "analysis.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert conclusions.analysis_fp(slug) != fp1, "analysis 變了指紋就要變 —— 舊判斷可能懸空"


def test_analysis_fp_missing_file(base):
    slug, b = base
    (b / "analysis.json").unlink()
    assert conclusions.analysis_fp(slug) == "", "沒有 analysis 就沒有指紋,不炸"


def test_analysis_fp_survives_read_failure(base):
    """fix pass 2 / important 1:analysis.json 存在但讀不了(換成目錄 → read_bytes()
    炸 IsADirectoryError)—— 這個函式現在同時掛在 conclusions.append 與
    transcript.append 兩條明文承諾絕不拋例外的熱路徑上,不能真的炸出去。
    沒有指紋跟『沒有 analysis.json』一樣,是『無從指紋』,不是錯誤。"""
    slug, b = base
    p = b / "analysis.json"
    p.unlink()
    p.mkdir()
    assert conclusions.analysis_fp(slug) == ""


# ── append:全過才寫 ─────────────────────────────────────────────────
def test_append_writes_and_load_reads(base):
    slug, b = base
    n, errs = conclusions.append(slug, [_draft(), _draft(kind="observation", text="燈重複出現三次")],
                                 session="abc", turns=[0, 3])
    assert (n, errs) == (2, [])
    rows = conclusions.load(slug)
    assert [r["id"] for r in rows] == ["c0001", "c0002"], "id 接續編號"
    assert rows[0]["provenance"]["session"] == "abc"


def test_append_ids_continue_across_calls(base):
    slug, b = base
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])
    conclusions.append(slug, [_draft()], session="b", turns=[1, 1])
    assert [r["id"] for r in conclusions.load(slug)] == ["c0001", "c0002"]


def test_append_survives_unreadable_analysis_json(base):
    """fix pass 2 / important 1 端到端:analysis.json 讀不了不該讓 append() 炸例外——
    沒有指紋不是全過才寫的『過不了』,只是這條結論的 analysis_fp 是空字串。"""
    slug, b = base
    p = b / "analysis.json"
    p.unlink()
    p.mkdir()
    n, errs = conclusions.append(slug, [_draft()], session="a", turns=[0, 0])
    assert n == 1 and errs == []
    assert conclusions.load(slug)[0]["provenance"]["analysis_fp"] == ""


def test_append_ids_do_not_collide_after_bad_line(base):
    """important 1 核心重現:append-only 正本原本用『可解析行數』當下一個 id 的起點——
    但 load() 會刻意跳過壞行,兩者自相矛盾。實測:c0001/c0002/c0003 寫好後,
    中間那行(c0002)壞掉,下一次 append 若照行數推算會再吐一次 c0003,跟既有的撞號。
    P2 的 invalidated_at 是以 id 為 handle,撞號代表作廢一筆會靜默作廢到錯的那筆。"""
    slug, b = base
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])   # c0001
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])   # c0002
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])   # c0003

    p = b / "conclusions.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[1] = "{壞掉的第二行"     # 讓 c0002 那行壞掉(load() 會跳過它)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    conclusions.append(slug, [_draft()], session="b", turns=[1, 1])
    ids = [r["id"] for r in conclusions.load(slug)]
    assert ids == ["c0001", "c0003", "c0004"], f"id 不能撞號,實際 {ids}"


def test_append_id_derivation_ignores_malformed_id_shapes(base):
    """推導下一個 id 時,既有行裡形狀不對的 id(非字串/缺欄位/尾巴非數字)要被忽略、
    不炸也不誤算 —— 覆蓋 max() generator 裡 isinstance/isdecimal 兩層過濾各自的假分支。"""
    slug, b = base
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])   # c0001
    with (b / "conclusions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": 123, "other": "id 非字串"}) + "\n")
        f.write(json.dumps({"note": "缺 id 欄位"}) + "\n")
        f.write(json.dumps({"id": "cXYZ"}) + "\n")               # id 尾巴非數字

    conclusions.append(slug, [_draft()], session="b", turns=[1, 1])
    proper_ids = [r["id"] for r in conclusions.load(slug) if isinstance(r.get("id"), str)]
    assert proper_ids[-1] == "c0002", f"該從既有最大合法 id(c0001)往下推,實際 {proper_ids}"


def test_append_id_derivation_ignores_superscript_digit(base):
    """fix pass 2 / minor 3:"c²" 這種 id ——"²".isdigit() 回 True 但 int("²") 拒收,
    用 isdigit() 篩選會讓這個『不炸也不誤算』的 guard 自己拋出未捕捉的 ValueError。
    上一版的 test_append_id_derivation_ignores_malformed_id_shapes 用的是 "cXYZ",
    那條走 isdigit()==False 分支,並沒有釘住這個洞 —— 這裡專門補上標數字的變體。"""
    slug, b = base
    conclusions.append(slug, [_draft()], session="a", turns=[0, 0])   # c0001
    with (b / "conclusions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "c²"}) + "\n")   # "c²":isdigit()==True,isdecimal()==False

    conclusions.append(slug, [_draft()], session="b", turns=[1, 1])   # 不該炸 ValueError
    proper_ids = [r["id"] for r in conclusions.load(slug) if isinstance(r.get("id"), str)]
    assert proper_ids[-1] == "c0002", f"該從既有最大合法 id(c0001)往下推,實際 {proper_ids}"


def test_append_all_or_nothing(base):
    """一筆壞 → 整批不寫。半套寫入的正本比沒寫更難救。"""
    slug, b = base
    n, errs = conclusions.append(slug, [_draft(), _draft(kind="opinion")],
                                 session="a", turns=[0, 0])
    assert n == 0 and errs
    assert conclusions.load(slug) == [], "好的那筆也不該落地"


def test_append_empty_drafts_is_noop(base):
    slug, b = base
    assert conclusions.append(slug, [], session="a", turns=[0, 0]) == (0, [])
    assert conclusions.load(slug) == []


def test_append_rejects_non_dict_draft(base):
    slug, b = base
    n, errs = conclusions.append(slug, ["這不是物件"], session="a", turns=[0, 0])
    assert n == 0 and errs


def test_append_skips_missing_story(base):
    slug, b = base
    n, errs = conclusions.append("no_such_slug", [_draft()], session="a", turns=[0, 0])
    assert n == 0 and errs and "不存在" in errs[0]


def test_load_missing_file(base):
    slug, b = base
    assert conclusions.load(slug) == []


def test_load_skips_bad_line(base):
    slug, b = base
    (b / "conclusions.jsonl").write_text('{"id":"c0001"}\n{壞\n\n{"id":"c0002"}\n', encoding="utf-8")
    assert len(conclusions.load(slug)) == 2


def test_non_ascii_not_escaped(base):
    slug, b = base
    conclusions.append(slug, [_draft(text="月光反覆出現")], session="a", turns=[0, 0])
    raw = (b / "conclusions.jsonl").read_text(encoding="utf-8")
    assert "月光反覆出現" in raw, "中文不該被轉義 —— 這份檔人也會打開看"


# ── minor 8:I/O 失敗要吞掉,不能讓磁碟錯誤冒成 500(與 ledger/transcript 同款一致性)──
def test_load_survives_read_failure(base):
    """把檔案路徑換成目錄 → read_text() 炸 IsADirectoryError(OSError 子類);
    load() 要跟壞行一樣吞掉,回 []。"""
    slug, b = base
    (b / "conclusions.jsonl").mkdir()
    assert conclusions.load(slug) == []


def test_validate_survives_schema_read_failure(base):
    """schema 檔本身讀不到(磁碟錯誤/被換成目錄)不該讓 validate() 炸例外,
    要老實回一筆錯誤 —— 全過才寫的語意下,這等於這批全部不放行。"""
    slug, b = base
    root = b.parent.parent   # 對應 base fixture monkeypatch 的 conclusions.ROOT
    schema_path = root / "schemas" / "conclusions.schema.json"
    schema_path.unlink()
    schema_path.mkdir()
    errs = conclusions.validate([], "隨便的原文")
    assert errs and "schema" in errs[0]


def test_append_survives_source_read_failure(base):
    """source.md 存在(exists() 為真)但讀不了(換成目錄)—— 跟『不存在』是不同分支,
    也要老實回錯,不能讓 IsADirectoryError 冒穿到呼叫端(server/discuss.py 的 distill)。"""
    slug, b = base
    src = b / "source.md"
    src.unlink()
    src.mkdir()
    n, errs = conclusions.append(slug, [_draft()], session="a", turns=[0, 0])
    assert n == 0 and errs and "source.md" in errs[0]


def test_append_survives_write_failure(base):
    """寫入那一步(open('a') 落地)失敗也要老實回錯,不炸例外 —— 磁碟滿/權限的情境。"""
    slug, b = base
    (b / "conclusions.jsonl").mkdir()   # open("a") 對目錄會炸 IsADirectoryError
    n, errs = conclusions.append(slug, [_draft()], session="a", turns=[0, 0])
    assert n == 0 and errs and "寫入失敗" in errs[0]
