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
import sys
import html
from pathlib import Path

import atomicio
from marrow.gate import _PUNCT, locate  # noqa: F401  (_PUNCT 給測試用)
from marrow.vizdata import (  # noqa: F401  (NODE_* 給測試/外部用)
    NODE_COLORS, NODE_CN, build_viz_data, diagnostics, locate_analysis as validate_and_locate,
    locate_feedback,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent


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


def load_feedback(base, source):
    """讀 feedback.json(可選),就地把 quote 命中座標寫進 _quotes,回傳 (feedback, errors)。"""
    fp = base / "feedback.json"
    if not fp.exists():
        return None, []
    fb = read_json(fp)
    return fb, locate_feedback(fb, source)


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


def build_html(data, source):
    """讀 viz/{template,css,js},把資料契約 dict + source 注入成自包含 viz.html。
    viz.html 與未來前端 app 消費同一個 data 契約(差別只在 app 用 HTTP 取 viz.json)。"""
    # 注入的是 <script> 內文 → 任何 "</script>"（乃至 "</"）都能 break out。
    # JSON 字串裡 "<\/" 與 "</" 等價(解析後一樣),故對兩份 payload 一律 </ → <\/,
    # 內容零改變、卻堵死跳出。source_json 不受引用閘門約束,尤其要守。
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    source_json = json.dumps(source, ensure_ascii=False).replace("</", "<\\/")
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
    atomicio.write_text_atomic(base / "viz.json", json.dumps(data, ensure_ascii=False, indent=2))
    atomicio.write_text_atomic(base / "viz.html", build_html(data, source))
    n_nodes, n_edges = len(analysis.get("nodes", [])), len(analysis.get("edges", []))
    print(f"✓ 出資料契約:{base / 'viz.json'}")
    print(f"✓ 出圖:{base / 'viz.html'}  ({n_nodes} 節點 / {n_edges} 邊)")
    if diag:
        print(f"  診斷:{sum(len(v) for v in diag.values())} 項(孤兒/過載/空心)")


if __name__ == "__main__":
    main()
