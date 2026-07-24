#!/usr/bin/env python3
"""討論記憶檢索(P2 recall / 喚燼):讓單篇討論召回自己過去的結論。

純函式、零寫入副作用、不呼叫 LLM(可讀檔,決定性)。契約凍結於
docs/superpowers/specs/2026-07-21-ember-discussion-memory-design.md §3。

隔離是**程式閘門**:layer="observation" 的呼叫者在程式上取不到 judgment/
question/feedback —— analyst/criticizer 隔離在記憶顆粒度上的同一條規則。
"""
import json
import logging
from pathlib import Path

import conclusions

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"
log = logging.getLogger("hyenovel")

# 層 → 放行的 kind(凍結,spec §3)。不對稱是刻意的:觀察是判斷的輸入,反之不然。
_LAYER_KINDS = {
    "observation": {"observation"},
    "judgment": {"observation", "judgment", "question"},
}

# 邊型權重(凍結,spec §3):意圖鏈核心最重,relates_to 最輕。
_EDGE_WEIGHT = {
    "produces": 1.0, "serves": 1.0,
    "manifests": 0.7, "recurs_in": 0.7,
    "tensions_with": 0.5, "characterizes": 0.5, "precedes": 0.5,
    "relates_to": 0.3,
}


def est_tokens(s):
    """token 保守高估:中文一字約一 token 上界,直接用 len。純函式。"""
    return len(s or "")


def _layer_allows(kind, layer):
    """該 kind 在該 layer 是否放行(隔離硬閘門的判定核心)。純函式。"""
    return kind in _LAYER_KINDS.get(layer, set())


def _stale(conclusion, cur_fp):
    """結論是否可能懸空:invalidated 或 analysis_fp 與現況不符。純函式。
    cur_fp 空('' = 無 analysis.json / 讀不到)→ 無從比對,不誤標 stale。"""
    if conclusion.get("invalidated_at") is not None:
        return True
    if not cur_fp:
        return False
    prov = conclusion.get("provenance") or {}
    return prov.get("analysis_fp") != cur_fp


def _expand(anchors, edges, hops):
    """從 anchors 沿 edges 無向 BFS 最多 hops 跳。純函式。
    回 {node_id: (min_hop, best_weight)}:min_hop 是最短跳距,best_weight 是
    抵達它那一跳所走邊的權重。每一跳只從「上一層已達」的節點外擴(先 snapshot),
    否則同一輪內剛加入的節點會被當成同跳的起點,把兩跳誤算成一跳。"""
    reached = {a: (0, 1.0) for a in anchors}
    for hop in range(1, hops + 1):
        prev = dict(reached)          # 本跳只從上一層外擴
        added = False
        for e in edges:
            w = _EDGE_WEIGHT.get(e.get("type"), 0.0)
            for a, b in ((e.get("from"), e.get("to")), (e.get("to"), e.get("from"))):
                if a in prev and b is not None and b not in reached:
                    reached[b] = (hop, w)
                    added = True
        if not added:
            break
    return reached


def _rank(conclusions_list, reached, anchors, nodes, cur_fp):
    """依 spec §3 排序訊號排序,回 [(conclusion, stale), ...]。純函式。
    key(全部化成「小者優先」):
      0. stale(invalidated / fp 不符)—— True 一律排最後
      1. 精確命中錨點(refs∩anchors 非空)—— 命中優先
      2. 最小 hop 距離 —— 近者優先
      3. 最大邊權 —— 重者優先
      4. ref 節點最大 intensity —— 強者優先
      5. ts —— 新者優先
    """
    anchor_set = set(anchors)
    scored = []
    for c in conclusions_list:
        refs = [r for r in (c.get("refs") or []) if isinstance(r, str)]
        st = _stale(c, cur_fp)
        exact = 1 if anchor_set.intersection(refs) else 0
        hopdists = [reached[r][0] for r in refs if r in reached]
        best_hop = min(hopdists) if hopdists else 10 ** 9
        weights = [reached[r][1] for r in refs if r in reached]
        best_w = max(weights) if weights else 0.0
        intens = [nodes[r].get("intensity") or 0.0 for r in refs if r in nodes]
        best_i = max(intens) if intens else 0.0
        key = (st, -exact, best_hop, -best_w, -best_i, -(c.get("ts") or 0.0))
        scored.append((key, c, st))
    scored.sort(key=lambda x: x[0])
    return [(c, st) for _, c, st in scored]


def _truncate(ranked, budget_tokens):
    """依序累加 est_tokens(text) 到超過 budget_tokens。純函式。
    回 (保留清單, truncated)。至少放行第一條 —— 空手而回比超一點點更無用。"""
    out, used, truncated = [], 0, False
    for c, st in ranked:
        cost = est_tokens(c.get("text"))
        if out and used + cost > budget_tokens:
            truncated = True
            break
        out.append((c, st))
        used += cost
    return out, truncated


def _read_json(slug, name):
    """讀 stories/<slug>/<name>;不存在或壞掉回 None(不炸,recall 對缺檔要優雅)。"""
    try:
        return json.loads((STORIES / slug / name).read_bytes())
    except (OSError, json.JSONDecodeError):
        return None


def _default_anchors(feedback):
    """anchors 空時的預設錨點:feedback key_points 的 refs(spec §3-1)。純函式。"""
    out = []
    if not isinstance(feedback, dict):
        return out
    for pt in feedback.get("key_points") or []:
        for r in pt.get("refs") or []:
            if isinstance(r, str) and r not in out:
                out.append(r)
    return out


def recall(slug, *, anchors=(), layer="judgment", hops=1, budget_tokens=6000, now=None):
    """召回一篇的過去結論,隔離為程式閘門。純函式(零寫入副作用)。見 spec §3。
    now 為凍結簽名保留欄位(時間衰減備用),目前不參與排序。"""
    analysis = _read_json(slug, "analysis.json") or {}
    feedback = _read_json(slug, "feedback.json")
    rows = conclusions.load(slug)
    cur_fp = conclusions.analysis_fp(slug)

    nodes = {n["id"]: n for n in analysis.get("nodes", [])
             if isinstance(n, dict) and isinstance(n.get("id"), str)}
    edges = [e for e in analysis.get("edges", []) if isinstance(e, dict)]

    # 隔離:observation 層不得靠 feedback 的節點選擇當預設錨點——那是 criticizer 的
    # 注意力型態(哪些節點被評過),屬判斷層的回音。只有 judgment 層 fall back 到
    # feedback key_points 的 refs。
    explicit = [a for a in anchors if isinstance(a, str)]
    anchor_list = explicit or (_default_anchors(feedback) if layer != "observation" else [])
    reached = _expand(anchor_list, edges, hops)

    allowed = [c for c in rows if _layer_allows(c.get("kind"), layer)]
    ranked = _rank(allowed, reached, anchor_list, nodes, cur_fp)
    kept, truncated = _truncate(ranked, budget_tokens)

    payload_nodes = []
    for nid, (hop, _w) in sorted(reached.items(), key=lambda kv: kv[1][0]):
        n = nodes.get(nid)
        if not n:
            continue
        payload_nodes.append({
            "id": nid, "type": n.get("type"), "label": n.get("label"), "note": n.get("note"),
            "quotes": [ev.get("quote") for ev in (n.get("evidence") or [])
                       if isinstance(ev, dict) and ev.get("quote")],
        })

    fb_points = []
    if layer != "observation" and isinstance(feedback, dict):
        for pt in feedback.get("key_points") or []:
            if set(pt.get("refs") or []).intersection(reached):
                fb_points.append({"title": pt.get("title"), "body": pt.get("body"),
                                  "question": pt.get("question")})

    return {
        "anchors": anchor_list,
        "conclusions": [{"id": c.get("id"), "kind": c.get("kind"), "text": c.get("text"),
                         "refs": c.get("refs"), "stale": st} for c, st in kept],
        "nodes": payload_nodes,
        "feedback": fb_points,
        "truncated": truncated,
    }


def format_recall(payload):
    """把 recall payload 攤成注入討論開場的文字。無可召回結論 → 空字串。純函式。
    只攤結論(討論本就會讀 analysis/feedback,節點細節不重複塞)。"""
    cs = payload.get("conclusions") or []
    if not cs:
        return ""
    lines = ["【這篇過去討論留下的結論(供參考,標記者可能已隨改稿懸空)】"]
    for c in cs:
        tag = "⚠可能懸空 " if c.get("stale") else ""
        refs = "、".join(r for r in (c.get("refs") or []) if isinstance(r, str))
        suffix = f"({refs})" if refs else ""
        lines.append(f"- {tag}{c.get('text')}{suffix}")
    return "\n".join(lines)
