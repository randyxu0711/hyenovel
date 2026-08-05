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
import time
from pathlib import Path

from jsonschema import Draft202012Validator

import atomicio
import conclusions

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


# 兩族被判為「同一族」所需的成員重疊度(Jaccard)下限。
# 0.5 = 一半以上成員相同。太低會讓不相干的族互相繼承 id,太高會讓正常的增減就換號。
JACCARD_MIN = 0.5


def _members_key(c):
    """concept 的成員集合(只取 (slug, node),忽略措辭)。

    **只防 members 的內容,不防 c 本身不是 dict** —— 兩個呼叫端都保證餵 dict 進來:
    drafts 已過 parse_drafts 的逐元素閘門,prev 的 concepts 在下面被 isinstance 濾過。
    再多防一層就是**測不到的防禦**,那種分支會讓 100% 門檻變成演的(要嘛湊不滿、
    要嘛靠 pragma 藏)。防禦要防真的會到的形狀。
    """
    out = set()
    for m in c.get("members") or []:
        if isinstance(m, dict) and isinstance(m.get("slug"), str) \
                and isinstance(m.get("node"), str):
            out.add((m["slug"], m["node"]))
    return out


def _jaccard(a, b):
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def assign_ids(drafts, prev):
    """替草稿鑄 id(純函式)。LLM 不給 id —— 那要它造字,等於把穩定性交回給它。

    沿用判準是**成員集合重疊度**,不是 canonical 字串相同:本設計同時要求族有權被
    重切,而重切時 LLM 幾乎不可能逐字重打同一個族名。集合重疊度不看措辭只看內容。

    一族裂成兩族時,成員留得多(重疊度高)的那支繼承 id,另一支鑄新號。
    一個舊 id 最多被沿用一次。已消失的族不回收號碼。
    """
    old = []
    for c in (prev or {}).get("concepts") or []:
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            old.append((c["id"], _members_key(c)))

    nums = [int(i[1:]) for i, _ in old if i[1:].isdigit()]
    nxt = max(nums, default=0) + 1

    # 先算全部配對的重疊度,由高到低指派 —— 保證裂族時大的那支先拿到 id。
    pairs = []
    for di, d in enumerate(drafts):
        dk = _members_key(d)
        for oid, ok in old:
            score = _jaccard(dk, ok)
            if score >= JACCARD_MIN:
                pairs.append((score, di, oid))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    taken_draft, taken_old, assigned = set(), set(), {}
    for score, di, oid in pairs:
        if di in taken_draft or oid in taken_old:
            continue
        assigned[di] = oid
        taken_draft.add(di)
        taken_old.add(oid)

    out = []
    for di, d in enumerate(drafts):
        c = dict(d)
        if di in assigned:
            c["id"] = assigned[di]
        else:
            c["id"] = f"L{nxt:03d}"
            nxt += 1
        out.append(c)
    return out


def _path():
    """每次現算 —— STORIES 是模組層變數,測試會 monkeypatch 它。"""
    return STORIES / "label-map.json"


def fingerprints():
    """現況每篇 analysis.json 的 sha1。沿用 conclusions.analysis_fp(單一正本)。

    只收真的有 analysis.json 的篇:analysis_fp 對不存在的檔回空字串,
    把「沒有分析」與「指紋是空的」混為一談會讓 stale 判定失準。
    """
    out = {}
    if not STORIES.is_dir():
        return out
    for d in sorted(STORIES.iterdir()):
        if not d.is_dir() or not (d / "analysis.json").exists():
            continue
        fp = conclusions.analysis_fp(d.name)
        if fp:
            out[d.name] = fp
    return out


def load():
    """讀 label-map.json;不存在 / 壞掉 / 不是 dict 一律回 None。

    壞掉當作不存在(而不是炸):它是衍生快取,重建的成本是幾分錢,
    而讓一個壞檔擋住整條討論路徑不划算。
    """
    p = _path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_bytes())
    except (OSError, json.JSONDecodeError):
        log.warning("event=label-map-load-fail")
        return None
    return data if isinstance(data, dict) else None


def is_stale(mapping):
    """地圖跟現況對不上了嗎(純函式,雙向比對)。

    三個成因,任一成立即 stale:
      ① 某 slug 的 fp 對不上   —— 該篇被 re-analyze,node id 已重鑄
      ② 現況有 slug 不在表裡   —— 新增了篇
      ③ 表裡有 slug 但檔沒了   —— 篇被刪掉(member 會指向不存在的篇)
    地圖本身讀不到 / 形狀不對 → 一律 stale。
    """
    recorded = (mapping or {}).get("analysis_fps")
    if not isinstance(recorded, dict):
        return True
    return recorded != fingerprints()


def parse_drafts(text):
    """把 LLM 的回應剝成 concepts 陣列。回 (drafts, 錯誤或 None)。

    照抄 conclusions.parse_drafts 的寬容度:剝 ``` 圍欄、容忍開場白 ——
    那兩件事幾乎一定會發生,不該燒掉一次付費呼叫換一句「不是合法 JSON」。
    寬容比對器 + 嚴格契約:剝完照樣要過全部閘門。

    **元素必須是物件這道檢查在這裡做完,是下游的前提**:assign_ids 的 dict(d)
    對字串會拋 ValueError —— 那會讓 build() 從「回錯誤清單」變成「炸例外」,
    而它是 LLM 輸出的閘門,閘門不可以炸。在入口一次擋掉,下游就不必各防一次。
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("["), s.rfind("]")
        if i == -1 or j == -1 or j <= i:
            return [], "分群回應不是合法 JSON"
        try:
            data = json.loads(s[i:j + 1])
        except json.JSONDecodeError:
            return [], "分群回應不是合法 JSON"
    if not isinstance(data, list):
        return [], "分群回應必須是 JSON 陣列"
    if not all(isinstance(c, dict) for c in data):
        return [], "分群回應的每個元素都必須是物件"
    return data, None


def _stamp_quotes(concepts, table):
    """照 evidence_index 從正本取引文蓋上(純函式)。

    LLM 不寫 quote 這欄:既然它必須是該 node evidence 裡已有的一條,讓它整句重打
    就只剩下抄錯的機會。index 不合法時蓋空字串,留給閘門去報一個看得懂的錯 ——
    不在這裡炸,也不悄悄重塑成看起來合法的東西。
    """
    known = {(r["slug"], r["node"]): r for r in table}
    for c in concepts:
        if not isinstance(c.get("members"), list):
            continue     # c 本身一定是 dict(parse_drafts 已擋),但 members 可能是任何東西
        for m in c["members"]:
            if not isinstance(m, dict):
                continue
            row = known.get((m.get("slug"), m.get("node")))
            i = m.get("evidence_index")
            ok = (row is not None and isinstance(i, int) and not isinstance(i, bool)
                  and 0 <= i < len(row["quotes"]))
            m["quote"] = row["quotes"][i] if ok else ""
    return concepts


def build(text, now=None):
    """總入口:解析 → 鑄 id → 蓋章 → 驗 → **全過才寫**。回 (mapping 或 None, 錯誤清單)。

    全過才寫的理由同 conclusions.append:部分寫入會產生一份「看起來合法但缺角」的
    地圖,那比沒有地圖更糟 —— 討論會拿它當完整的講。
    """
    drafts, err = parse_drafts(text)
    if err:
        return None, [err]
    if not drafts:
        return None, ["分群回應是空陣列"]
    table = collect()
    concepts = _stamp_quotes(assign_ids(drafts, load()), table)
    mapping = {
        "built_at": round(time.time(), 3) if now is None else now,
        "analysis_fps": fingerprints(),
        "source_node_count": len(table),
        "concepts": concepts,
    }
    errors = validate(mapping, table)
    if errors:
        return None, errors
    atomicio.write_text_atomic(
        _path(), json.dumps(mapping, ensure_ascii=False, indent=1) + "\n")
    return mapping, []


def count_singletons(mapping):
    """只跨一篇的族有幾個(純函式)。

    **這不是閘門,是一條備查線。** 只跨一篇不代表錯 —— 它可能是還沒長成的族
    (全量重歸下,第 8 篇寫了同樣的東西它明天就跨兩篇了),砍掉等於把「七篇時的
    視野」寫死。而 spec §5 承認視覺押後 → 沒人會去開 JSON 看 → 分錯了是靜默的;
    這個數字進 log 之後,「1/29」與「12/29」的差別才看得見。
    """
    n = 0
    for c in (mapping or {}).get("concepts") or []:
        if not isinstance(c, dict):
            continue
        slugs = {m.get("slug") for m in c.get("members") or []
                 if isinstance(m, dict)}
        if len(slugs) == 1:
            n += 1
    return n
