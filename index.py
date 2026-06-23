#!/usr/bin/env python3
"""hyenovel index — 掃 stories/*/,出 stories/index.json(全集列表契約)。

與 viz.json 同性質:前端的「故事列表 / 首頁」讀這份枚舉故事;CLI 階段也能拿來看全集。
只讀各篇 analysis.json / feedback.json 的表層欄位,不重算、不開閘門(那是 viz.py 的事)。

用法:
  python index.py            # 出 stories/index.json
  python index.py --check    # 只印摘要,不寫檔
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"


def entry(d):
    """組一篇的列表項;analysis.json 缺/壞則跳過(回 None)。
    單篇壞掉不該讓整份列表生不出來,故這裡容錯跳過(印警告),不像閘門那樣 sys.exit。"""
    slug = d.name
    aj = d / "analysis.json"
    if not aj.exists():
        return None
    try:
        a = json.loads(aj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ⚠ 跳過 {slug}:analysis.json 不是合法 JSON({e.msg},行 {e.lineno})")
        return None
    fb = d / "feedback.json"
    mtime = aj.stat().st_mtime
    if fb.exists():
        mtime = max(mtime, fb.stat().st_mtime)  # feedback 較新則以它為準
    iso = datetime.fromtimestamp(mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "slug": a.get("slug", slug),
        "title": a.get("title") or slug,
        "synopsis": a.get("synopsis", ""),
        "nodes": len(a.get("nodes", [])),
        "edges": len(a.get("edges", [])),
        "has_feedback": fb.exists(),
        "has_viz": (d / "viz.json").exists(),
        "updated": iso,
    }


def build():
    stories = []
    for d in sorted(p for p in STORIES.iterdir() if p.is_dir()):
        e = entry(d)
        if e:
            stories.append(e)
    return {
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "count": len(stories),
        "stories": stories,
    }


def main():
    check = "--check" in sys.argv[1:]
    data = build()
    for s in data["stories"]:
        fb = "✓feedback" if s["has_feedback"] else "—"
        print(f"  {s['slug']}  {s['title']}  ({s['nodes']}節點/{s['edges']}邊, {fb})")
    if check:
        print(f"共 {data['count']} 篇(--check,未寫檔)。")
        return
    out = STORIES / "index.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 出列表契約:{out}  ({data['count']} 篇)")


if __name__ == "__main__":
    main()
