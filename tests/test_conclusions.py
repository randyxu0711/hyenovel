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
