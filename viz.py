#!/usr/bin/env python3
"""hyenovel viz — 讀 stories/<slug>/analysis.json,出 viz.html。

職責:
  1. 逐字引用硬閘門:每個 evidence.quote 必須在 source.md 找得到,否則報錯。
  2. 算文本軸座標:命中位置 / 全文長度 → 0..1,給文本軸與點擊跳原文。
  3. 出自包含 viz.html:① 意圖鏈(cytoscape) ② 文本軸解剖(SVG)連動。

用法:
  python viz.py <slug>            # 驗證 + 出 viz.html
  python viz.py <slug> --check    # 只驗證引用,不出圖(給 critique 編排當閘門)
"""
import json
import re
import sys
import html
from pathlib import Path

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


def load(slug):
    base = ROOT / "stories" / slug
    aj = base / "analysis.json"
    src = base / "source.md"
    if not aj.exists():
        sys.exit(f"找不到 {aj}(先跑 /story-critique)")
    if not src.exists():
        sys.exit(f"找不到 {src}")
    analysis = json.loads(aj.read_text(encoding="utf-8"))
    source = src.read_text(encoding="utf-8")
    return base, analysis, source


def locate(quote, source):
    """回傳 (start, end) 或 None。先精確找,再容許空白差異。"""
    idx = source.find(quote)
    if idx != -1:
        return idx, idx + len(quote)
    # 容許換行/空白差異
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in quote if not ch.isspace()))
    m = pat.search(source)
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


def build_html(slug, analysis, source, diag):
    title = analysis.get("title") or slug
    nodes = analysis.get("nodes", [])
    edges = analysis.get("edges", [])

    # cytoscape elements
    cy_nodes = []
    for n in nodes:
        cls = sorted(diag.get(n["id"], set()))
        cy_nodes.append({"data": {
            "id": n["id"], "label": n.get("label", n["id"]),
            "ntype": n["type"], "note": n.get("note", ""),
        }, "classes": " ".join(cls)})
    cy_edges = []
    for i, e in enumerate(edges):
        cy_edges.append({"data": {
            "id": f"e{i}", "source": e["from"], "target": e["to"],
            "label": e["type"], "note": e.get("note", ""),
        }})

    # node 附帶 evidence(座標)給文本軸 + 點擊
    node_payload = []
    for n in nodes:
        evs = []
        for ev in n.get("evidence", []) or []:
            evs.append({"quote": ev.get("quote", ""), "start": ev.get("_start", -1),
                        "end": ev.get("_end", -1), "pos": ev.get("_pos")})
        node_payload.append({"id": n["id"], "type": n["type"],
                             "label": n.get("label", n["id"]),
                             "note": n.get("note", ""),
                             "intensity": n.get("intensity"),
                             "evidence": evs})

    data = {
        "slug": slug, "title": title,
        "cyElements": cy_nodes + cy_edges,
        "nodes": node_payload, "edges": edges,
        "colors": NODE_COLORS, "cn": NODE_CN,
        "diag": {k: sorted(v) for k, v in diag.items()},
    }
    data_json = json.dumps(data, ensure_ascii=False)
    source_json = json.dumps(source, ensure_ascii=False)

    vdir = ROOT / "viz"
    tpl = (vdir / "template.html").read_text(encoding="utf-8")
    css = (vdir / "viz.css").read_text(encoding="utf-8")
    js = (vdir / "viz.js").read_text(encoding="utf-8")
    # 注入順序:先 CSS/JS(可能含 placeholder 字面?無),再 data/source/title
    return (tpl
            .replace("/*__CSS__*/", css)
            .replace("/*__JS__*/", js)
            .replace("/*__DATA__*/", data_json)
            .replace("/*__SOURCE__*/", source_json)
            .replace("__TITLE__", html.escape(title)))



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
    errors = validate_and_locate(analysis, source)

    if errors:
        print(f"⚠ 引用硬閘門:{len(errors)} 條 quote 在 source.md 找不到:")
        for nid, q in errors:
            print(f"  [{nid}] {q[:50]}")
    else:
        print(f"✓ 引用硬閘門通過:所有 quote 皆對得上原文。")

    if check:
        sys.exit(1 if errors else 0)

    diag = diagnostics(analysis)
    out = base / "viz.html"
    out.write_text(build_html(slug, analysis, source, diag), encoding="utf-8")
    n_nodes, n_edges = len(analysis.get("nodes", [])), len(analysis.get("edges", []))
    print(f"✓ 出圖:{out}  ({n_nodes} 節點 / {n_edges} 邊)")
    if diag:
        print(f"  診斷:{sum(len(v) for v in diag.values())} 項(孤兒/過載/空心)")


if __name__ == "__main__":
    main()
