#!/usr/bin/env python3
"""hyenovel render — 讀 stories/<slug>/{analysis,feedback}.json,出人讀的 md(Obsidian 友善)。

確定性渲染:同 json 進、同 md 出,不依賴 LLM。md 只服務「人讀 / Obsidian viewer」,
不是前端 app 的資料來源(那是 viz.json)。故意做成機械、可重現——
不重現 criticizer 手寫信的文采,只忠實攤開 feedback.json 的全部內容。

用法:
  python render.py <slug>          # 出 analysis.md + feedback.md(feedback 可選)
  python render.py <slug> --analysis-only
"""
import json
import sys
from pathlib import Path

import atomicio

ROOT = Path(__file__).resolve().parent

# 章節順序與中文名(對齊 viz.py 的 NODE_CN)
SECTIONS = [("theme", "主題"), ("motif", "意象"), ("technique", "技法"),
            ("effect", "效果"), ("character", "角色"), ("beat", "節拍")]
NODE_CN = dict(SECTIONS)


def read_json(path):
    """讀 JSON;格式錯誤給乾淨訊息 + 退出碼 1(別吐 traceback)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"✗ {path.name} 不是合法 JSON:{e.msg}(行 {e.lineno} 欄 {e.colno})。修正後重跑。")


def parse_slug(raw):
    p = Path(raw.rstrip("/"))
    if p.name in ("source.md", "analysis.json", "feedback.json"):
        return p.parent.name
    if "stories" in p.parts:
        return p.parts[p.parts.index("stories") + 1]
    return p.name


def linked_themes(node, nodes_by_id, edges):
    """意象→manifests→主題、效果→serves→主題:回傳該節點關聯的主題 label 清單。"""
    out = []
    for e in edges:
        if e["from"] == node["id"] and e["type"] in ("manifests", "serves"):
            t = nodes_by_id.get(e["to"])
            if t and t["type"] == "theme":
                out.append(t["label"])
    return out


def render_analysis(analysis):
    title = analysis.get("title") or analysis.get("slug", "")
    slug = analysis.get("slug", "")
    nodes = analysis.get("nodes", [])
    edges = analysis.get("edges", [])
    by_id = {n["id"]: n for n in nodes}

    L = [f"---\ntitle: \"{title}\"\nslug: {slug}\ntags: [hyenovel, story-analysis]\n---", ""]
    L.append(f"# {title} — 結構分析\n")
    if analysis.get("synopsis"):
        L.append(f"> {analysis['synopsis']}\n")

    for typ, cn in SECTIONS:
        group = [n for n in nodes if n["type"] == typ]
        if not group:
            continue
        L.append(f"## {cn}\n")
        for n in group:
            head = f"### {n['label']}"
            if typ in ("effect", "beat") and n.get("intensity") is not None:
                head += f"  ·強度 {n['intensity']}"
            L.append(head)
            if n.get("note"):
                L.append(n["note"])
            for ev in n.get("evidence", []) or []:
                line = f"- 「{ev['quote']}」"
                if ev.get("note"):
                    line += f" — {ev['note']}"
                L.append(line)
            if typ in ("motif", "effect"):
                themes = linked_themes(n, by_id, edges)
                if themes:
                    L.append("關聯主題:" + " ".join(f"[[{t}]]" for t in themes))
            L.append("")

    # 意圖鏈:technique →produces→ effect →serves→ theme
    L.append("## 意圖鏈(technique → effect → theme)\n")
    serves = {}  # effect_id -> [theme_label]
    for e in edges:
        if e["type"] == "serves":
            t = by_id.get(e["to"])
            if t and t["type"] == "theme":
                serves.setdefault(e["from"], []).append(t["label"])
    for e in edges:
        if e["type"] != "produces":
            continue
        tech, eff = by_id.get(e["from"]), by_id.get(e["to"])
        if not tech or not eff:
            continue
        themes = serves.get(eff["id"])
        if themes:
            for th in themes:
                L.append(f"- {tech['label']} →produces→ {eff['label']} →serves→ [[{th}]]")
        else:
            L.append(f"- {tech['label']} →produces→ {eff['label']}")
    return "\n".join(L).rstrip() + "\n"


def render_feedback(feedback, title):
    def quotes(qs):
        return [f"> 「{q}」" for q in (qs or [])]

    L = ["---\ntags: [hyenovel, story-feedback]\n---", ""]
    L.append(f"# 給作者的話 —〈{title}〉\n")
    if feedback.get("read"):
        L.append("## 這篇在做什麼(我讀到的)\n")
        L.append(feedback["read"] + "\n")

    if feedback.get("strengths"):
        L.append("## 最有效的地方(為什麼有效)\n")
        for p in feedback["strengths"]:
            L.append(f"### {p['title']}")
            L += quotes(p.get("quotes"))
            if p.get("body"):
                L.append("\n" + p["body"])
            L.append("")

    if feedback.get("key_points"):
        L.append("## 我會往下推的關鍵(2–3 件,非枝節)\n")
        for i, p in enumerate(feedback["key_points"], 1):
            L.append(f"### {i}. {p['title']}")
            L += quotes(p.get("quotes"))
            if p.get("body"):
                L.append("\n" + p["body"])
            if p.get("experiment"):
                L.append(f"\n- **可以試的實驗**:{p['experiment']}")
            if p.get("question"):
                L.append(f"- **留給作者的問題**:{p['question']}")
            L.append("")

    if feedback.get("minor"):
        L.append("## 枝節(可選,簡短)\n")
        for m in feedback["minor"]:
            L.append(f"- {m}")
        L.append("")

    if feedback.get("one_line"):
        L.append("## 一句話\n")
        L.append(f"如果只能改一件事:**{feedback['one_line']}**")
    return "\n".join(L).rstrip() + "\n"


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("用法:python render.py <slug> [--analysis-only]")
    analysis_only = "--analysis-only" in args
    raw = next((a for a in args if not a.startswith("--")), None)
    if not raw:
        sys.exit("缺 slug")
    slug = parse_slug(raw)
    base = ROOT / "stories" / slug
    aj = base / "analysis.json"
    if not aj.exists():
        sys.exit(f"找不到 {aj}(先跑 /story-critique)")

    analysis = read_json(aj)
    atomicio.write_text_atomic(base / "analysis.md", render_analysis(analysis))
    print(f"✓ 出:{base / 'analysis.md'}")

    fp = base / "feedback.json"
    if not analysis_only and fp.exists():
        feedback = read_json(fp)
        title = analysis.get("title") or slug
        atomicio.write_text_atomic(base / "feedback.md", render_feedback(feedback, title))
        print(f"✓ 出:{base / 'feedback.md'}")
    elif not fp.exists():
        print("(無 feedback.json,略過 feedback.md)")


if __name__ == "__main__":
    main()
