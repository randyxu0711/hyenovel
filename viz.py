#!/usr/bin/env python3
"""hyenovel viz — 讀 stories/<slug>/{analysis,feedback}.json,出 viz.json + viz.html。

職責:
  1. schema 閘門:analysis.json / feedback.json 須合 schemas/*.schema.json,否則報錯擋下。
  2. 逐字引用硬閘門:每個 evidence.quote 必須在 source.md 找得到,否則報錯擋下。
  3. 算文本軸座標:命中位置 / 全文長度 → 0..1,給文本軸與點擊跳原文。
  4. 出 viz.json:前端資料契約正本(viz.html 與未來 app 共用)。
  5. 出自包含 viz.html:① 意圖鏈(cytoscape) ② 文本軸解剖(SVG)連動,消費 viz.json。

用法:
  python viz.py <slug>            # 兩道閘門 + 出 viz.json + viz.html
  python viz.py <slug> --check    # 只驗兩道閘門,不出檔(給 critique 編排當閘門)
"""
import json
import re
import sys
import html
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
NODE_COLORS = {
    "theme": "#c0392b",      # 紅
    "motif": "#8e44ad",      # 紫
    "technique": "#2980b9",  # 藍
    "effect": "#e67e22",     # 橘
    "character": "#27ae60",  # 綠
    "beat": "#7f8c8d",       # 灰
}
NODE_CN = {"theme": "主題", "motif": "意象", "technique": "技法",
           "effect": "效果", "character": "角色", "beat": "節拍"}


def read_json(path):
    """讀 JSON;格式錯誤給乾淨訊息 + 退出碼 1(別吐 traceback,讓修正迴路能用)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"✗ {path.name} 不是合法 JSON:{e.msg}(行 {e.lineno} 欄 {e.colno})。修正後重跑。")


def load(slug):
    base = ROOT / "stories" / slug
    aj = base / "analysis.json"
    src = base / "source.md"
    if not aj.exists():
        sys.exit(f"找不到 {aj}(先跑 /story-critique)")
    if not src.exists():
        sys.exit(f"找不到 {src}")
    analysis = read_json(aj)
    source = src.read_text(encoding="utf-8")
    return base, analysis, source


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


def validate_and_locate(analysis, source):
    """就地把命中座標寫進 evidence(_start/_end/_pos),回傳錯誤清單。"""
    total = len(source) or 1
    errors = []
    for node in analysis.get("nodes", []):
        for ev in node.get("evidence", []) or []:
            q = ev.get("quote", "")
            span = locate(q, source) if q else None
            if span is None:
                errors.append((node.get("id", "?"), q))
                ev["_start"] = ev["_end"] = -1
                ev["_pos"] = None
            else:
                ev["_start"], ev["_end"] = span
                ev["_pos"] = span[0] / total
    return errors


def load_feedback(base, source):
    """讀 feedback.json(可選),就地把 quote 命中座標寫進 _quotes,回傳 (feedback, errors)。"""
    fp = base / "feedback.json"
    if not fp.exists():
        return None, []
    fb = read_json(fp)
    errors = []
    for sec in ("strengths", "key_points"):
        for pt in fb.get(sec, []) or []:
            loc = []
            for q in pt.get("quotes", []) or []:
                span = locate(q, source)
                if span is None:
                    errors.append(("feedback:" + pt.get("title", "?")[:14], q))
                    loc.append({"quote": q, "start": -1, "end": -1})
                else:
                    loc.append({"quote": q, "start": span[0], "end": span[1]})
            pt["_quotes"] = loc
    return fb, errors


def validate_schemas(base):
    """對磁碟原始 json 驗 schema,回傳錯誤訊息清單。
    必須在 validate_and_locate 寫入座標前做:_start/_end/_pos 等附加欄位
    會被 schema 的 additionalProperties:false 擋下,故這裡重讀原始檔。"""
    errors = []
    checks = [("analysis.json", "analysis.schema.json", True),
              ("feedback.json", "feedback.schema.json", False)]
    for fname, sname, required in checks:
        fp = base / fname
        if not fp.exists():
            if required:
                errors.append(f"{fname} 不存在")
            continue
        schema = json.loads((ROOT / "schemas" / sname).read_text(encoding="utf-8"))
        data = read_json(fp)
        for e in sorted(Draft202012Validator(schema).iter_errors(data),
                        key=lambda x: list(x.path)):
            path = "/".join(str(p) for p in e.path) or "(root)"
            errors.append(f"{fname} [{path}]: {e.message}")
    return errors


def diagnostics(analysis):
    """意圖鏈診斷:孤兒技法 / 過載主題 / 空心主題。回傳 {node_id: set(classes)}。"""
    nodes = {n["id"]: n for n in analysis.get("nodes", [])}
    edges = analysis.get("edges", [])
    out_produces = {}   # technique -> [effect]
    serves_to = {}      # theme -> [effect] (incoming serves)
    for e in edges:
        if e["type"] == "produces":
            out_produces.setdefault(e["from"], []).append(e["to"])
        if e["type"] == "serves":
            serves_to.setdefault(e["to"], []).append(e["from"])
    # motif manifests theme 也算餵養主題
    manifests_to = {}
    for e in edges:
        if e["type"] == "manifests":
            manifests_to.setdefault(e["to"], []).append(e["from"])

    classes = {}
    for nid, n in nodes.items():
        t = n["type"]
        if t == "technique" and not out_produces.get(nid):
            classes.setdefault(nid, set()).add("orphan")        # 孤兒技法
        if t == "theme":
            feeders = len(serves_to.get(nid, [])) + len(manifests_to.get(nid, []))
            if feeders == 0:
                classes.setdefault(nid, set()).add("hollow")    # 空心主題
            elif feeders >= 4:
                classes.setdefault(nid, set()).add("overloaded")  # 過載主題
    return classes


def build_viz_data(slug, analysis, source, diag, feedback=None):
    """組出前端資料契約 dict —— 落成 stories/<slug>/viz.json,也是 build_html 的輸入。
    與 source 解耦:原文由 source.md 提供(HYENOVEL_SRC),不重複塞進 viz.json。
    欄位名須與 viz.js 一致(尤其 diag,非 diagnostics)。"""
    title = analysis.get("title") or slug

    # node 附帶 evidence(座標)給文本軸 + 點擊
    node_payload = []
    for n in analysis.get("nodes", []):
        evs = []
        for ev in n.get("evidence", []) or []:
            evs.append({"quote": ev.get("quote", ""), "start": ev.get("_start", -1),
                        "end": ev.get("_end", -1), "pos": ev.get("_pos")})
        node_payload.append({"id": n["id"], "type": n["type"],
                             "label": n.get("label", n["id"]),
                             "note": n.get("note", ""),
                             "intensity": n.get("intensity"),
                             "evidence": evs})

    feedback_payload = None
    if feedback:
        def pts(key):
            out = []
            for pt in feedback.get(key, []) or []:
                out.append({"title": pt.get("title", ""), "body": pt.get("body", ""),
                            "experiment": pt.get("experiment"), "question": pt.get("question"),
                            "refs": pt.get("refs", []) or [], "quotes": pt.get("_quotes", [])})
            return out
        feedback_payload = {"read": feedback.get("read", ""),
                            "strengths": pts("strengths"), "key_points": pts("key_points"),
                            "minor": feedback.get("minor", []), "one_line": feedback.get("one_line", "")}

    return {
        "slug": slug, "title": title,
        "nodes": node_payload, "edges": analysis.get("edges", []),
        "colors": NODE_COLORS, "cn": NODE_CN,
        "diag": {k: sorted(v) for k, v in diag.items()},
        "feedback": feedback_payload,
    }


def build_html(data, source):
    """讀 viz/{template,css,js},把資料契約 dict + source 注入成自包含 viz.html。
    viz.html 與未來前端 app 消費同一個 data 契約(差別只在 app 用 HTTP 取 viz.json)。"""
    data_json = json.dumps(data, ensure_ascii=False)
    source_json = json.dumps(source, ensure_ascii=False)
    vdir = ROOT / "viz"
    tpl = (vdir / "template.html").read_text(encoding="utf-8")
    css = (vdir / "viz.css").read_text(encoding="utf-8")
    js = (vdir / "viz.js").read_text(encoding="utf-8")
    return (tpl
            .replace("/*__CSS__*/", css)
            .replace("/*__JS__*/", js)
            .replace("/*__DATA__*/", data_json)
            .replace("/*__SOURCE__*/", source_json)
            .replace("__TITLE__", html.escape(data["title"])))



def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        sys.exit("用法:python viz.py <slug> [--check]")
    check = "--check" in args
    raw = next((a for a in args if not a.startswith("--")), None)
    if not raw:
        sys.exit("缺 slug")
    # 容許傳 <slug>、stories/<slug> 或 stories/<slug>/source.md
    p = Path(raw.rstrip("/"))
    if p.name == "source.md":
        slug = p.parent.name
    elif "stories" in p.parts:
        slug = p.parts[p.parts.index("stories") + 1]
    else:
        slug = p.name

    base, analysis, source = load(slug)

    # 閘門一:schema(對磁碟原始 json,須在寫入座標前)
    schema_errors = validate_schemas(base)
    if schema_errors:
        print(f"⚠ schema 閘門:{len(schema_errors)} 項不合契約:")
        for e in schema_errors:
            print(f"  {e}")
    else:
        print("✓ schema 閘門通過:analysis.json / feedback.json 皆合契約。")

    # 閘門二:逐字引用(順帶算文本軸座標,就地寫進 analysis/feedback)
    errors = validate_and_locate(analysis, source)
    feedback, fb_errors = load_feedback(base, source)
    errors += fb_errors
    if errors:
        print(f"⚠ 引用閘門:{len(errors)} 條 quote 在 source.md 找不到:")
        for nid, q in errors:
            print(f"  [{nid}] {q[:50]}")
    else:
        print("✓ 引用閘門通過:所有 quote(含 feedback)皆對得上原文。")

    gate_failed = bool(schema_errors or errors)
    if check:
        sys.exit(1 if gate_failed else 0)
    if gate_failed:
        sys.exit("✗ 閘門未過,不出 viz.json / viz.html。修正後重跑。")

    diag = diagnostics(analysis)
    data = build_viz_data(slug, analysis, source, diag, feedback)
    (base / "viz.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "viz.html").write_text(build_html(data, source), encoding="utf-8")
    n_nodes, n_edges = len(analysis.get("nodes", [])), len(analysis.get("edges", []))
    print(f"✓ 出資料契約:{base / 'viz.json'}")
    print(f"✓ 出圖:{base / 'viz.html'}  ({n_nodes} 節點 / {n_edges} 邊)")
    if diag:
        print(f"  診斷:{sum(len(v) for v in diag.values())} 項(孤兒/過載/空心)")


if __name__ == "__main__":
    main()
