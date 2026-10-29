"""export:DB current artifact → 可分享的 md + viz html。合成資料,不碰真實 DB / stories/。"""
import json
from pathlib import Path

import pytest

import export
from marrow import db, repo

MINI = Path(__file__).resolve().parent / "fixtures" / "mini"
ANALYSIS = json.loads((MINI / "analysis.json").read_text(encoding="utf-8"))
FEEDBACK = json.loads((MINI / "feedback.vizdata.json").read_text(encoding="utf-8"))
SOURCE = (MINI / "source.md").read_text(encoding="utf-8")
TITLE = ANALYSIS["title"]            # 標題以 analysis 為先(分析者決定),story.title 只是退路
FB_HEAD = f"# 給作者的話 —〈{TITLE}〉"


def seed(conn, slug="mini", analysis=True, feedback=True):
    sid = repo.ensure_story(conn, slug, "迷你", 1.0)
    svid, _ = repo.add_source_version(conn, sid, SOURCE, 1.0)
    for kind, body, on in (("analysis", ANALYSIS, analysis), ("feedback", FEEDBACK, feedback)):
        if on:
            aid, _ = repo.add_artifact(conn, sid, svid, kind, 1, body, {}, 1.0)
            repo.set_current(conn, sid, kind, aid)
    return sid


def _body(md):
    """去掉文件開頭唯一的 front matter。"""
    assert md.startswith("---\n")
    return md.split("\n---\n", 1)[1]


def test_build_markdown_feedback_first(conn):
    seed(conn)
    md, _ = export.build(conn, "mini")
    analysis_md = export.render_analysis({**ANALYSIS, "title": TITLE}, front_matter=False)
    assert md.index(FB_HEAD) < md.index("\n---\n\n" + analysis_md)
    assert md.endswith(analysis_md)
    assert "tags: [hyenovel, story-feedback, story-analysis]" in md.split("\n---\n", 1)[0]


def test_build_single_front_matter(conn):
    seed(conn)
    md, _ = export.build(conn, "mini")
    assert md.count("\ntitle:") == 1 and md.count("\nslug:") == 1
    assert "tags: [hyenovel, story-feedback]" not in md
    assert f"# {TITLE} — 結構分析" in md


def test_build_without_feedback_has_no_separator_section(conn):
    seed(conn, feedback=False)
    md, _ = export.build(conn, "mini")
    assert FB_HEAD not in md
    assert md.split("\n---\n", 1)[0].endswith("tags: [hyenovel, story-analysis]")
    assert _body(md).lstrip() == export.render_analysis({**ANALYSIS, "title": TITLE}, front_matter=False)
    assert md.count("\ntitle:") == 1 and md.count("\nslug:") == 1


def test_build_html_uses_analysis_source_version(conn):
    sid = seed(conn)
    repo.add_source_version(conn, sid, "改過的新稿。", 2.0)
    _, html = export.build(conn, "mini")
    assert "桌上那盞燈還亮著" in html
    assert "改過的新稿" not in html


def test_build_unknown_slug(conn):
    with pytest.raises(LookupError):
        export.build(conn, "nope")


def test_build_not_analyzed(conn):
    seed(conn, analysis=False, feedback=False)
    with pytest.raises(export.NotAnalyzed):
        export.build(conn, "mini")


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/t.db"
    monkeypatch.setenv("DATABASE_URL", url)
    c = db.connect(url)
    db.migrate(c, db.sqlite_path(url))
    yield c
    c.close()


def test_main_writes_both_files(file_db, tmp_path, capsys):
    seed(file_db)
    file_db.commit()
    out = tmp_path / "out" / "x"
    assert export.main(["mini", "--out", str(out)]) == 0
    assert FB_HEAD in (out / "mini.md").read_text(encoding="utf-8")
    assert "<html" in (out / "mini.html").read_text(encoding="utf-8")
    assert capsys.readouterr().out.count("✓ 出:") == 2


def test_main_default_out_is_stories_slug(file_db, tmp_path, monkeypatch):
    seed(file_db)
    file_db.commit()
    monkeypatch.setattr(export, "ROOT", tmp_path)
    assert export.main(["mini"]) == 0
    assert (tmp_path / "stories" / "mini" / "mini.md").exists()


def test_main_unknown_slug_returns_1(file_db, tmp_path, capsys):
    assert export.main(["nope", "--out", str(tmp_path / "o")]) == 1
    assert "找不到" in capsys.readouterr().err


def test_main_not_analyzed_returns_1(file_db, tmp_path, capsys):
    seed(file_db, analysis=False, feedback=False)
    file_db.commit()
    assert export.main(["mini", "--out", str(tmp_path / "o")]) == 1
    assert "start_critique" in capsys.readouterr().err


def test_main_bad_slug_returns_1(tmp_path, capsys):
    assert export.main(["../x", "--out", str(tmp_path / "o")]) == 1
    assert "不合法" in capsys.readouterr().err


def test_title_order_analysis_then_story_then_slug(conn):
    seed(conn)
    md, _ = export.build(conn, "mini")
    assert f'title: "{TITLE}"' in md and "迷你" not in md.split("\n---\n", 1)[0]
    # analysis 沒標題 → 退到 story.title;story 也沒有 → slug
    no_title = {k: v for k, v in ANALYSIS.items() if k != "title"}
    for slug, story_title, want in (("t1", "迷你", "迷你"), ("t2", None, "t2")):
        sid = repo.ensure_story(conn, slug, story_title, 1.0)
        svid, _ = repo.add_source_version(conn, sid, SOURCE, 1.0)
        aid, _ = repo.add_artifact(conn, sid, svid, "analysis", 1, no_title, {}, 1.0)
        repo.set_current(conn, sid, "analysis", aid)
        md, _ = export.build(conn, slug)
        assert f'title: "{want}"' in md
