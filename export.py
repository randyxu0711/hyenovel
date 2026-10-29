"""匯出:從 DB 的 current artifact 產一份可分享的 Markdown(人與 agent 都能直接讀)
加一份 viz HTML(人看圖)。手動執行,den 不自動匯出——DB 維持唯一正本。

用法:python -m export <slug> [--out DIR]   (預設 stories/<slug>/)
"""
import argparse
import sys
from pathlib import Path

import atomicio
from den.config import valid_slug
from marrow import db, repo
from marrow.vizdata import viz_payload
from render import render_analysis, render_feedback
from viz import build_html

ROOT = Path(__file__).resolve().parent


class NotAnalyzed(LookupError):
    """故事存在但沒有 current analysis。"""


def build(conn, slug: str) -> tuple[str, str]:
    """回 (markdown, html)。找不到故事 → LookupError;沒有 current analysis → NotAnalyzed。"""
    story = repo.story_by_slug(conn, slug)
    if story is None:
        raise LookupError(slug)
    art = repo.current_artifact(conn, story["id"], "analysis")
    if art is None:
        raise NotAnalyzed("not-analyzed")
    analysis = art["body"]
    fb = repo.current_artifact(conn, story["id"], "feedback")
    feedback = fb["body"] if fb else None
    # 原文取 analysis 當時對照的那一版;之後改稿不該讓引用對不上。
    source = repo.source_version(conn, art["source_version_id"])["text"]
    # 一份文件一個標題、一個 front matter;分析標題也用同一個(淺拷貝,不動 DB body)。
    title = analysis.get("title") or story["title"] or slug
    tags = "hyenovel, story-feedback, story-analysis" if feedback is not None else "hyenovel, story-analysis"
    parts = [f'---\ntitle: "{title}"\nslug: {slug}\ntags: [{tags}]\n---\n\n']
    if feedback is not None:
        parts += [render_feedback(feedback, title, front_matter=False), "\n---\n\n"]
    parts.append(render_analysis({**analysis, "title": title}, front_matter=False))
    return "".join(parts), build_html(viz_payload(slug, analysis, feedback, source), source)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m export")
    ap.add_argument("slug")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not valid_slug(args.slug):
        print(f"✗ slug 不合法:{args.slug}", file=sys.stderr)
        return 1
    url = db.database_url()
    conn = db.connect(url)
    try:
        db.migrate(conn, db.sqlite_path(url))
        md, html = build(conn, args.slug)
    except NotAnalyzed:
        print(f"✗ {args.slug} 還沒分析過,先用 start_critique 送分析。", file=sys.stderr)
        return 1
    except LookupError:
        print(f"✗ 找不到故事:{args.slug}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    out = args.out or ROOT / "stories" / args.slug
    out.mkdir(parents=True, exist_ok=True)
    for name, text in ((f"{args.slug}.md", md), (f"{args.slug}.html", html)):
        atomicio.write_text_atomic(out / name, text)
        print(f"✓ 出:{out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
