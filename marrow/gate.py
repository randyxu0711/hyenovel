"""確定性閘門:三層引文匹配 + v1 結構完整性(node id、edge 端點、quote、refs)。

錯誤訊息會原樣餵回工人修補:只說錯在哪、不給正解。
形狀不對(非 list / dict)的欄位跳過該檢查而不拋例外,schema 錯已另行回報。
"""
import re

from marrow import schema

# 標點正規化(1:1 等長,故正規化後的索引在原文仍有效)。
# 容忍作者手打/子代理難辨的半形⇄全形與引號方向差異,但不放過真正缺字的幻覺引用。
_PUNCT = str.maketrans({
    ",": "，", ".": "。", "!": "！", "?": "？",
    ":": "：", ";": "；", "(": "（", ")": "）",
    # 引號:ASCII 與左右彎引號視為等價(作者常混用、子代理難辨方向),全部正規化到右彎引號
    '"': "”", "“": "”",
    "'": "’", "‘": "’",
})


def locate(quote, source):
    """回傳 (start, end) 或 None。容許半形/全形標點與空白差異;仍要求逐字。"""
    nq, ns = quote.translate(_PUNCT), source.translate(_PUNCT)
    for q, s in ((quote, source), (nq, ns)):
        idx = s.find(q)
        if idx != -1:
            return idx, idx + len(quote)
    # 容許換行/空白差異(在標點正規化後)
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in nq if not ch.isspace()))
    m = pat.search(ns)
    if m:
        return m.start(), m.end()
    return None


def _dicts(value):
    """list 裡的 dict 項;不是 list 回空。"""
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _node_ids(body):
    return [n["id"] for n in _dicts(body.get("nodes")) if isinstance(n.get("id"), str)]


def gate_analysis(body: dict, source: str) -> list[str]:
    errs = [f"schema: {m}" for m in schema.validate_v1("analysis", body)]
    if not isinstance(body, dict):
        return errs
    nodes = _dicts(body.get("nodes"))
    ids = _node_ids(body)
    seen = set()
    for i in ids:
        if i in seen:
            errs.append(f"node {i}: id 重複")
        seen.add(i)
    for e in _dicts(body.get("edges")):
        for end in (e.get("from"), e.get("to")):
            if end not in ids:
                errs.append(f"edge {e.get('from')}->{e.get('to')}: 端點 {end} 不存在")
    for n in nodes:
        for ev in _dicts(n.get("evidence")):
            q = ev.get("quote")
            if isinstance(q, str) and not (q and locate(q, source)):
                errs.append(f"node {n.get('id')}: 引文在原文找不到:「{q[:50]}」")
    return errs


def gate_feedback(body: dict, analysis: dict, source: str) -> list[str]:
    errs = [f"schema: {m}" for m in schema.validate_v1("feedback", body)]
    if not isinstance(body, dict):
        return errs
    ids = _node_ids(analysis) if isinstance(analysis, dict) else []
    for key in ("strengths", "key_points"):
        for p in _dicts(body.get(key)):
            label = f"feedback「{str(p.get('title'))[:14]}」"
            quotes = p.get("quotes")
            for q in quotes if isinstance(quotes, list) else []:
                if isinstance(q, str) and not (q and locate(q, source)):
                    errs.append(f"{label}: 引文在原文找不到:「{q[:50]}」")
            refs = p.get("refs")
            for r in refs if isinstance(refs, list) else []:
                if r not in ids:
                    errs.append(f"{label}: refs {r} 不是存在的 node id")
    return errs
