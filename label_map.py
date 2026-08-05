#!/usr/bin/env python3
"""跨篇概念地圖的確定性層:stories/label-map.json。

**這個檔是衍生快取,可整份刪掉重建。** 任何資料不得只存在於它裡面。

分工同 conclusions.py / settled.py:本模組是純函式層 —— 不認識 SDK、不認識 server/。
分群是 LLM 的判斷,由 server/align.py 餵草稿進來;本模組負責驗、鑄 id、蓋章、落地。
**重新思考是 LLM 的事,穩定是程式的事。**

設計正本:docs/superpowers/specs/2026-07-30-cross-story-align-design.md
"""
import json
import logging
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"

# 吃哪些節點型別。beat 是篇內事件序列(跨篇沒有對應物)、character 大多是「他」
# 「無名敘事者」(歸一會產生垃圾族),兩個都不吃。理由見 spec §3。
TYPES = ("motif", "theme", "technique", "effect")

log = logging.getLogger("hyenovel")


def collect():
    """掃 STORIES,回這四型別的全部標籤(純讀檔,無副作用)。

    每筆 {"slug", "node", "type", "label", "quotes"},依 (slug, node) 排序。
    **quotes 一起帶出來**:後面的閘門與蓋章只吃這張表,不再重讀檔 ——
    那讓下游全部是對純資料的純函式。

    讀不到 / 格式壞的故事整篇跳過(不是錯誤:可能正在孕育、可能剛被刪)。
    """
    out = []
    if not STORIES.is_dir():
        return out
    for d in sorted(STORIES.iterdir()):
        if not d.is_dir():
            continue
        try:
            data = json.loads((d / "analysis.json").read_bytes())
        except (OSError, json.JSONDecodeError):
            continue
        nodes = data.get("nodes") if isinstance(data, dict) else None
        if not isinstance(nodes, list):
            continue
        for n in nodes:
            if not isinstance(n, dict) or n.get("type") not in TYPES:
                continue
            nid, label = n.get("id"), n.get("label")
            if not isinstance(nid, str) or not isinstance(label, str):
                continue
            ev = n.get("evidence") if isinstance(n.get("evidence"), list) else []
            out.append({
                "slug": d.name, "node": nid, "type": n["type"], "label": label,
                "quotes": [e["quote"] for e in ev
                           if isinstance(e, dict) and isinstance(e.get("quote"), str)],
            })
    out.sort(key=lambda r: (r["slug"], r["node"]))
    return out


def validate(mapping, table):
    """六道閘門。回錯誤清單(空 = 放行)。純函式,絕不拋例外。

    table = collect() 的結果。閘門順序與 conclusions.validate 同構:
    schema 先跑,再跑語意閘門。**閘門自己炸掉等於沒有閘門** —— 所有型別假設都要防。
    """
    try:
        schema = json.loads(
            (ROOT / "schemas" / "label-map.schema.json").read_text(encoding="utf-8"))
    except OSError as e:
        return [f"讀不到 schema:{type(e).__name__}"]
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(mapping),
                    key=lambda x: list(x.path)):
        path = "/".join(str(p) for p in e.path) or "(root)"
        errors.append(f"[{path}]: {e.message}")

    known = {(r["slug"], r["node"]): r for r in table}
    concepts = mapping.get("concepts")
    if not isinstance(concepts, list):
        return errors        # 形狀錯已由 schema 記過一筆,不逐項迭代非陣列值
    for c in concepts:
        if not isinstance(c, dict):
            continue         # 同上
        cid = c.get("id", "?")
        members = c.get("members")
        if not isinstance(members, list):
            continue
        for mem in members:
            if not isinstance(mem, dict):
                continue
            key = (mem.get("slug"), mem.get("node"))
            row = known.get(key)
            if row is None:
                errors.append(f"{cid}: analysis 裡沒有這個節點「{key[0]}/{key[1]}」")
                continue
            if row["type"] != c.get("node_type"):
                errors.append(f"{cid}: 型別不符 —— {key[0]}/{key[1]} 是 "
                              f"{row['type']},族卻標 {c.get('node_type')}")
            if mem.get("label") != row["label"]:
                errors.append(f"{cid}: label 與 analysis 不符「{mem.get('label')}」"
                              f"(正本是「{row['label']}」)")
            i = mem.get("evidence_index")
            if not isinstance(i, int) or isinstance(i, bool) \
                    or not 0 <= i < len(row["quotes"]):
                errors.append(f"{cid}: evidence_index 超出範圍({key[0]}/{key[1]} "
                              f"只有 {len(row['quotes'])} 條 evidence)")
    return errors
