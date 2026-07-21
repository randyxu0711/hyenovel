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
import logging
import time
from pathlib import Path

from jsonschema import Draft202012Validator

import viz

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"

# 用跟 server/log.py 一樣的 logger 名字("hyenovel")—— logging 用全域名字查表,
# 不需要真的 import server 套件(conclusions.py 是根層模組,server/ 才反過來 import 它)。
log = logging.getLogger("hyenovel")


def _path(slug):
    return STORIES / slug / "conclusions.jsonl"


def load(slug):
    """讀該篇所有結論;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。
    讀取 I/O 失敗(TOCTOU 被 rmtree/換成目錄)也吞掉,回 []。"""
    p = _path(slug)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning(f"event=conclusions-load-fail slug={slug} err={type(e).__name__}")
        return []
    out = []
    for ln in text.splitlines():
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
        # 圍欄之外,LLM 偶爾會加一句開場白(「以下是結論:」)才接 JSON 陣列——
        # 跟圍欄一樣可以預期會發生,不該燒掉一次付費回合換來一句「不是合法 JSON」。
        # 退而求其次:切出第一個 [ 到最後一個 ] 再試一次;安全性零損失,
        # schema 與引文閘門照樣會跑在切出來的東西上。
        i, j = s.find("["), s.rfind("]")
        if i == -1 or j == -1 or j <= i:
            return [], "收束回應不是合法 JSON"
        try:
            data = json.loads(s[i:j + 1])
        except json.JSONDecodeError:
            return [], "收束回應不是合法 JSON"
    if not isinstance(data, list):
        return [], "收束回應必須是 JSON 陣列"
    return data, None


def _as_list(v):
    """草稿裡本該是陣列的欄位(refs/quotes)正規化用。
    是 list/tuple 才轉成 list;沒給(None)補空陣列;其餘型別(尤其是字串)原樣照抄,
    丟給 schema 閘門去擋 —— 絕不用 list() 硬轉,那會把字串拆成單字元陣列,
    讓一句捏造的引文悄悄變成看起來合法的東西。"""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return v


def stamp(draft, idx, ts, session, turns, fp):
    """把四欄草稿蓋成完整 record(純函式)。
    草稿缺欄位不在這裡炸 —— 留給 schema 閘門去報一個看得懂的錯。
    但「形狀錯」(比如 quotes 給成純量字串)也一樣留給 schema 閘門去擋,
    不在這裡悄悄重塑成看起來合法的陣列。"""
    d = draft if isinstance(draft, dict) else {}
    return {
        "id": f"c{idx:04d}",
        "ts": ts,
        "kind": d.get("kind"),
        "text": d.get("text"),
        "refs": _as_list(d.get("refs")),
        "quotes": _as_list(d.get("quotes")),
        "provenance": {"session": session, "turns": list(turns), "analysis_fp": fp},
        "valid_from": ts,
        "invalidated_at": None,
    }


def validate(records, source):
    """兩道閘門。回錯誤清單(空 = 放行)。純函式。"""
    try:
        schema = json.loads((ROOT / "schemas" / "conclusions.schema.json").read_text(encoding="utf-8"))
    except OSError as e:
        return [f"讀不到 schema:{type(e).__name__}"]
    validator = Draft202012Validator(schema)
    errors = []
    for r in records:
        rid = r.get("id", "?")
        for e in sorted(validator.iter_errors(r), key=lambda x: list(x.path)):
            path = "/".join(str(p) for p in e.path) or "(root)"
            errors.append(f"{rid} [{path}]: {e.message}")
        quotes = r.get("quotes", [])
        if not isinstance(quotes, list):
            continue  # 型別錯已經由上面的 schema 檢查擋下;這裡不逐字迭代非陣列值
        for q in quotes:
            if not isinstance(q, str):
                # list 裡混了非字串元素(如 [123]):schema 會擋,但這裡不能拿它去
                # 呼叫 viz.locate 而炸例外 —— 誠實記一筆型別錯,不悄悄跳過。
                errors.append(f"{rid}: quotes 裡有非字串元素「{q!r}」")
                continue
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
    try:
        source = (base / "source.md").read_text(encoding="utf-8")
    except OSError as e:
        return 0, [f"讀不到 source.md:{type(e).__name__}"]
    # read-then-write 配 id,無鎖:假設單一 session 循序呼叫(目前唯一呼叫者)。
    # Task 5 接線 server/discuss.py 後若出現並發呼叫,這裡需要重新設計。
    # id 從既有 id 的最大值往下推,不數 load() 回傳的行數 —— load() 會跳過壞行,
    # 用行數當起點會在中間有壞行時撞號(c0003 重複發兩次),而 P2 的 invalidated_at
    # 是以 id 為 handle,撞號代表作廢一筆會靜默作廢到錯的那筆。
    start = max((int(r["id"][1:]) for r in load(slug)
                 if isinstance(r.get("id"), str) and r["id"][1:].isdigit()), default=0)
    ts = round(time.time(), 3)
    fp = analysis_fp(slug)
    records = [stamp(d, start + i + 1, ts, session, turns, fp) for i, d in enumerate(drafts)]
    errors = validate(records, source)
    if errors:
        return 0, errors
    try:
        with _path(slug).open("a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning(f"event=conclusions-append-fail slug={slug} err={type(e).__name__}")
        return 0, [f"寫入失敗:{type(e).__name__}"]
    return len(records), []
