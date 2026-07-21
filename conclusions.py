#!/usr/bin/env python3
"""討論結論正本:stories/<slug>/conclusions.jsonl 的唯一寫入者與閘門。

分工沿用「LLM 寫內容、確定性層驗」——但比 analysis/feedback 更嚴:
LLM 只交出 kind/text/refs/quotes 四欄草稿,id / ts / provenance / valid_from
一律由這裡蓋章。讓 LLM 自己填 transcript 行號跟 sha1 只會得到看起來很像的幻覺。

兩道閘門,缺一不可:
  ① schema      —— 結構對不對(schemas/conclusions.schema.json)
  ② 逐字引文    —— quotes 必須能在 source.md 定位(走 viz.locate 的三層寬鬆匹配)
第二道是整個記憶系統的存亡關鍵:記憶若能挾帶不存在的原文,它就是污染源而非資產。

寫入語意:全過才寫(all-or-nothing)。半套落地的正本比沒寫更難救。
"""
import hashlib
import json
import time
from pathlib import Path

from jsonschema import Draft202012Validator

import viz

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"


def _path(slug):
    return STORIES / slug / "conclusions.jsonl"


def load(slug):
    """讀該篇所有結論;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。"""
    p = _path(slug)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def analysis_fp(slug):
    """當時 analysis.json 的 sha1。日後它變了 → 這條結論可能已經懸空。
    沒有 analysis.json 就回空字串:不是錯誤,是「無從指紋」。"""
    p = STORIES / slug / "analysis.json"
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""


def parse_drafts(text):
    """把 LLM 吐的文字解析成草稿陣列,回 (drafts, error)。純函式。
    會剝掉 ``` 圍欄 —— LLM 幾乎一定會包,那不是它的錯,是我們該接住。"""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return [], "收束回應不是合法 JSON"
    if not isinstance(data, list):
        return [], "收束回應必須是 JSON 陣列"
    return data, None


def stamp(draft, idx, ts, session, turns, fp):
    """把四欄草稿蓋成完整 record(純函式)。
    草稿缺欄位不在這裡炸 —— 留給 schema 閘門去報一個看得懂的錯。"""
    d = draft if isinstance(draft, dict) else {}
    return {
        "id": f"c{idx:04d}",
        "ts": ts,
        "kind": d.get("kind"),
        "text": d.get("text"),
        "refs": list(d.get("refs") or []),
        "quotes": list(d.get("quotes") or []),
        "provenance": {"session": session, "turns": list(turns), "analysis_fp": fp},
        "valid_from": ts,
        "invalidated_at": None,
    }


def validate(records, source):
    """兩道閘門。回錯誤清單(空 = 放行)。純函式。"""
    schema = json.loads((ROOT / "schemas" / "conclusions.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = []
    for r in records:
        rid = r.get("id", "?")
        for e in sorted(validator.iter_errors(r), key=lambda x: list(x.path)):
            path = "/".join(str(p) for p in e.path) or "(root)"
            errors.append(f"{rid} [{path}]: {e.message}")
        for q in r.get("quotes", []):
            if viz.locate(q, source) is None:
                errors.append(f"{rid}: 原文中找不到這句引用「{q[:20]}」")
    return errors


def append(slug, drafts, session, turns):
    """蓋章 → 驗 → 全過才寫。回 (寫入筆數, 錯誤清單)。"""
    if not drafts:
        return 0, []
    base = STORIES / slug
    if not (base / "source.md").exists():
        return 0, [f"{slug} 不存在或沒有 source.md"]
    source = (base / "source.md").read_text(encoding="utf-8")
    start = len(load(slug))
    ts = round(time.time(), 3)
    fp = analysis_fp(slug)
    records = [stamp(d, start + i + 1, ts, session, turns, fp) for i, d in enumerate(drafts)]
    errors = validate(records, source)
    if errors:
        return 0, errors
    with _path(slug).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records), []
