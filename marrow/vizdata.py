"""marrow.vizdata:viz 的純組裝(定位引文 → 診斷 → 資料契約 dict)。無檔案 IO。

viz.py(CLI)與 den(從 DB artifact 組 viz)共用這一份。
"""
import copy

from marrow.gate import locate

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


def locate_analysis(analysis, source):
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


def locate_feedback(feedback, source):
    """就地把 quote 命中座標寫進 feedback 的 _quotes,回傳錯誤清單。"""
    errors = []
    for sec in ("strengths", "key_points"):
        for pt in feedback.get(sec, []) or []:
            loc = []
            for q in pt.get("quotes", []) or []:
                span = locate(q, source)
                if span is None:
                    errors.append(("feedback:" + pt.get("title", "?")[:14], q))
                    loc.append({"quote": q, "start": -1, "end": -1})
                else:
                    loc.append({"quote": q, "start": span[0], "end": span[1]})
            pt["_quotes"] = loc
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


def notes_as_feedback(notes):
    """備課筆記 → viz / web 既有的 feedback 形狀(版面不動):打動歸 strengths、其餘照順序歸 key_points。"""
    def pt(p):
        return {"title": p["title"], "quotes": p["quotes"], "refs": p["refs"], "body": p["body"],
                "experiment": None, "question": p["question"]}
    pts = notes["points"]
    return {"read": notes["read"], "one_line": notes["one_line"], "minor": [],
            "strengths": [pt(p) for p in pts if p["kind"] == "moved"],
            "key_points": [pt(p) for p in pts if p["kind"] != "moved"]}


def pick_judgment(analysis_art, notes_art, feedback_art):
    """與分析同版的判斷層(feedback 形狀):同版筆記優先,其次同版舊 feedback,否則 None。
    不同版不配:refs 綁的 node id 與引文對不上這份分析。"""
    sv = analysis_art["source_version_id"]
    if notes_art is not None and notes_art["source_version_id"] == sv:
        return notes_as_feedback(notes_art["body"])
    if feedback_art is not None and feedback_art["source_version_id"] == sv:
        return feedback_art["body"]
    return None


def viz_payload(slug, analysis, feedback, source):
    """DB artifact body → 前端資料契約。深拷貝後再定位,不動呼叫端的 body;
    不回錯誤清單(進 DB 的 artifact 已過閘門)。"""
    analysis = copy.deepcopy(analysis)
    feedback = copy.deepcopy(feedback)
    locate_analysis(analysis, source)
    if feedback is not None:
        locate_feedback(feedback, source)
    return build_viz_data(slug, analysis, source, diagnostics(analysis), feedback)
