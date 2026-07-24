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
