"""marrow.importer:舊 stories/ → DB,冪等可重跑(spec §8 R1)。

合成資料一律寫在這裡;stories/ 真實內容絕不碰。
"""
import json
import shutil
from pathlib import Path

from marrow import importer, repo

FIXTURES = Path(__file__).resolve().parent / "fixtures"

FEEDBACK = {"slug": "mini", "read": "讀", "one_line": "改一件",
            "key_points": [{"title": "點", "quotes": ["引"], "body": "說"}]}
TWO_SESSIONS = [
    {"ts": 1.0, "session": "s1", "role": "user", "text": "問一", "anchors": ["t1"], "analysis_fp": "fp"},
    {"ts": 2.0, "session": "s1", "role": "assistant", "text": "答一", "anchors": None, "analysis_fp": "fp"},
    {"ts": 3.0, "session": "s2", "role": "user", "text": "問二", "anchors": None, "analysis_fp": "fp"},
    {"ts": 4.0, "session": "s2", "role": "assistant", "text": "答二", "anchors": None, "analysis_fp": "fp"},
]
ROW_S2_EXTRA = {"ts": 5.0, "session": "s2", "role": "user", "text": "追問", "anchors": None,
                "analysis_fp": "fp"}
CONC_A = {"id": "c0001", "ts": 6.0, "kind": "observation", "text": "結論", "refs": ["t1"],
          "quotes": ["引"], "provenance": {"session": "s1", "turns": [0, 1], "analysis_fp": "fp"},
          "valid_from": 6.0, "invalidated_at": None}
SETTLED = [{"session": "s1", "ts": 7.0, "ok": True, "written": 1, "errors": []},
           {"session": "s2", "ts": 7.5, "ok": False, "written": 0, "errors": ["x"]}]


def _jsonl(path, rows):
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def make_story(tmp_path, slug, analysis=True, feedback=False, transcript=(), conclusions=(),
               settled=()):
    """造 <tmp>/stories/<slug>/,回 stories 根。source.md 一定有;其餘依參數。"""
    root = tmp_path / "stories"
    base = root / slug
    base.mkdir(parents=True)
    shutil.copy(FIXTURES / "mini/source.md", base / "source.md")
    if analysis:
        shutil.copy(FIXTURES / "mini/analysis.json", base / "analysis.json")
    if feedback:
        (base / "feedback.json").write_text(json.dumps(FEEDBACK, ensure_ascii=False), encoding="utf-8")
    for name, rows in (("transcript", transcript), ("conclusions", conclusions), ("settled", settled)):
        if rows:
            _jsonl(base / f"{name}.jsonl", rows)
    return root


def _added(rep):
    return {k: v for k, v in rep.items() if k.endswith("_added")}


def test_full_story_round_trip(conn, tmp_path):
    root = make_story(tmp_path, "mini", feedback=True, transcript=TWO_SESSIONS,
                      conclusions=[CONC_A], settled=SETTLED)
    rep = importer.import_story(conn, root / "mini", 10.0)
    sid = repo.story_by_slug(conn, "mini")["id"]
    assert rep["skipped"] == []
    assert _added(rep) == {"source_versions_added": 1, "artifacts_added": 2, "utterances_added": 4,
                           "conclusions_added": 1, "settlements_added": 1}   # 失敗的收束列不進
    an = repo.current_artifact(conn, sid, "analysis")
    assert an["schema_version"] == 1 and an["provenance"]["imported_from"] == "analysis.json"
    assert repo.current_artifact(conn, sid, "feedback")["body"]["strengths"] is None
    d1 = conn.execute("SELECT * FROM discussion WHERE external_id='s1'").fetchone()
    assert (d1["started_at"], d1["ended_at"], d1["home"]) == (1.0, 2.0, "web")
    us = repo.utterances(conn, d1["id"])
    assert [u["seq"] for u in us] == [0, 1] and us[0]["anchors"] == ["t1"] and us[1]["anchors"] == []
    assert repo.conclusions(conn, sid)[0]["discussion_id"] == d1["id"]


def test_story_title_from_analysis(conn, tmp_path):
    root = make_story(tmp_path, "mini")
    importer.import_story(conn, root / "mini", 1.0)
    title = json.loads((FIXTURES / "mini/analysis.json").read_text(encoding="utf-8")).get("title")
    assert repo.story_by_slug(conn, "mini")["title"] == title


def test_rerun_is_noop(conn, tmp_path):
    root = make_story(tmp_path, "mini", feedback=True, transcript=TWO_SESSIONS,
                      conclusions=[CONC_A], settled=SETTLED)
    importer.import_story(conn, root / "mini", 1.0)
    rep = importer.import_story(conn, root / "mini", 2.0)
    assert set(_added(rep).values()) == {0} and rep["skipped"] == []


def test_rerun_picks_up_appended_rows(conn, tmp_path):
    root = make_story(tmp_path, "mini", transcript=TWO_SESSIONS)
    importer.import_story(conn, root / "mini", 1.0)
    _jsonl(root / "mini/transcript.jsonl", [ROW_S2_EXTRA])
    rep = importer.import_story(conn, root / "mini", 2.0)
    assert rep["utterances_added"] == 1
    d2 = conn.execute("SELECT * FROM discussion WHERE external_id='s2'").fetchone()
    assert d2["ended_at"] == 5.0 and repo.utterances(conn, d2["id"])[-1]["seq"] == 2


def test_partial_story_imports_what_exists(conn, tmp_path):
    root = make_story(tmp_path, "mini", analysis=False)          # 只有 source.md
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert rep["source_versions_added"] == 1 and rep["artifacts_added"] == 0 and rep["skipped"] == []
    assert repo.story_by_slug(conn, "mini")["title"] is None


def test_edited_source_adds_version(conn, tmp_path):
    root = make_story(tmp_path, "mini")
    importer.import_story(conn, root / "mini", 1.0)
    (root / "mini/source.md").write_text("改過的稿", encoding="utf-8")
    rep = importer.import_story(conn, root / "mini", 2.0)
    assert rep["source_versions_added"] == 1 and rep["artifacts_added"] == 0


def test_bad_artifact_skipped_not_fatal(conn, tmp_path, caplog):
    root = make_story(tmp_path, "mini", feedback=True)
    (root / "mini/analysis.json").write_text("{壞", encoding="utf-8")
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert [s.split(":")[0] for s in rep["skipped"]] == ["analysis"] and rep["artifacts_added"] == 1
    assert "event=import-skip" in caplog.text and "item=analysis" in caplog.text


def test_artifact_failing_v1_skipped(conn, tmp_path):
    root = make_story(tmp_path, "mini")
    (root / "mini/feedback.json").write_text(json.dumps({**FEEDBACK, "extra": 1}), encoding="utf-8")
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert [s.split(":")[0] for s in rep["skipped"]] == ["feedback"]


def test_bad_jsonl_line_skipped(conn, tmp_path, caplog):
    root = make_story(tmp_path, "mini", transcript=TWO_SESSIONS)
    p = root / "mini/transcript.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines.insert(1, "{壞")
    lines.insert(2, "")                                          # 空行不算壞行
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert rep["utterances_added"] == 4 and rep["skipped"] == ["transcript.jsonl:2: bad-json"]
    assert "reason=bad-json" in caplog.text


def test_conclusion_without_known_session(conn, tmp_path):
    orphan = {**CONC_A, "id": "c0002", "provenance": {"session": "gone"}}
    root = make_story(tmp_path, "mini", conclusions=[orphan],
                      settled=[{"session": "gone", "ts": 1, "ok": True, "written": 1, "errors": []}])
    rep = importer.import_story(conn, root / "mini", 1.0)
    sid = repo.story_by_slug(conn, "mini")["id"]
    assert repo.conclusions(conn, sid)[0]["discussion_id"] is None
    assert rep["settlements_added"] == 0                          # 沒有 discussion 可掛


def test_story_is_one_transaction(conn, tmp_path, monkeypatch, caplog):
    root = make_story(tmp_path, "mini", transcript=TWO_SESSIONS)

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(repo, "add_utterance", boom)
    reps = importer.import_all(conn, root, 1.0)
    assert reps[0]["skipped"] == ["story: RuntimeError"]
    assert repo.story_by_slug(conn, "mini") is None                # 整篇 rollback
    assert "event=import-fail" in caplog.text


def test_import_all_ignores_non_story_entries_and_sorts(conn, tmp_path):
    root = make_story(tmp_path, "zz")
    make_story(tmp_path / "x", "aa")
    shutil.move(tmp_path / "x/stories/aa", root / "aa")
    (root / "index.json").write_text("{}")
    (root / "empty").mkdir()
    assert [r["slug"] for r in importer.import_all(conn, root, 1.0)] == ["aa", "zz"]


def test_main_exit_codes(tmp_path, capsys):
    root = make_story(tmp_path, "mini")
    url = f"sqlite:///{tmp_path}/h.db"
    assert importer.main(["--stories", str(root), "--db", url]) == 0
    (root / "mini/feedback.json").write_text("{壞", encoding="utf-8")
    assert importer.main(["--stories", str(root), "--db", url]) == 1
    assert "mini" in capsys.readouterr().out


# ── final review 修正 ──

def test_wrong_shape_jsonl_rows_skipped_not_fatal(conn, tmp_path):     # I1
    root = make_story(tmp_path, "mini", feedback=True, transcript=TWO_SESSIONS)
    _jsonl(root / "mini/transcript.jsonl", [{"ts": 9, "role": "user", "text": "沒 session"}, 123])
    _jsonl(root / "mini/conclusions.jsonl", [{"id": "c9"}])
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert rep["utterances_added"] == 4 and rep["artifacts_added"] == 2
    assert rep["skipped"] == ["transcript.jsonl:5: bad-shape", "transcript.jsonl:6: bad-shape",
                              "conclusions.jsonl:1: bad-shape"]


def test_non_utf8_artifact_skipped(conn, tmp_path):                      # I1
    root = make_story(tmp_path, "mini")
    (root / "mini/analysis.json").write_bytes(b"\xff\xfe{")
    rep = importer.import_story(conn, root / "mini", 1.0)
    assert rep["skipped"] == ["analysis: bad-encoding"] and rep["source_versions_added"] == 1


def test_orphan_db_story_logged(conn, tmp_path, caplog):                 # I4
    root = make_story(tmp_path, "mini")
    importer.import_all(conn, root, 1.0)
    shutil.rmtree(root / "mini")
    importer.import_all(conn, root, 2.0)
    assert "event=import-orphan slug=mini" in caplog.text


def test_importer_rerun_keeps_den_current(conn, tmp_path):
    root = make_story(tmp_path, "mini")
    importer.import_story(conn, root / "mini", 1.0)
    s = repo.story_by_slug(conn, "mini")
    v = repo.latest_source_version(conn, s["id"])
    body = dict(repo.current_artifact(conn, s["id"], "analysis")["body"], title="den 版")
    aid, _ = repo.add_artifact(conn, s["id"], v["id"], "analysis", 1, body, {"runner": "den"}, 2.0)
    repo.set_current(conn, s["id"], "analysis", aid)          # 模擬 den 產出
    importer.import_story(conn, root / "mini", 3.0)
    assert repo.current_artifact(conn, s["id"], "analysis")["id"] == aid


# ── 結論回填 analysis_artifact_id(切片 4a)──

def _fp(root, slug="mini"):
    import hashlib
    return hashlib.sha1((root / slug / "analysis.json").read_bytes()).hexdigest()


def _conc(fp):
    return {**CONC_A, "provenance": {"session": "s1", "turns": [0, 1], "analysis_fp": fp}}


def test_importer_backfills_conclusion_artifact_when_fp_matches(conn, tmp_path):
    import hashlib
    fp = hashlib.sha1((FIXTURES / "mini/analysis.json").read_bytes()).hexdigest()
    root = make_story(tmp_path, "mini", transcript=TWO_SESSIONS, conclusions=[_conc(fp)])
    importer.import_story(conn, root / "mini", 10.0)
    sid = repo.story_by_slug(conn, "mini")["id"]
    aid = repo.current_artifact(conn, sid, "analysis")["id"]
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] == aid
    importer.import_story(conn, root / "mini", 11.0)             # 重跑冪等
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] == aid


def test_importer_leaves_null_when_fp_differs(conn, tmp_path):
    root = make_story(tmp_path, "mini", conclusions=[_conc("not-the-fp")])
    importer.import_story(conn, root / "mini", 10.0)
    sid = repo.story_by_slug(conn, "mini")["id"]
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] is None


def test_importer_backfills_existing_conclusion_on_rerun(conn, tmp_path):
    """切換現場:DB 裡已有 analysis_artifact_id 為 NULL 的結論(舊版匯入的),
    再跑 import_story、fp 對上 → 補上;已有值的不被覆蓋。"""
    import hashlib
    fp = hashlib.sha1((FIXTURES / "mini/analysis.json").read_bytes()).hexdigest()
    root = make_story(tmp_path, "mini", conclusions=[_conc(fp)])
    importer.import_story(conn, root / "mini", 10.0)
    sid = repo.story_by_slug(conn, "mini")["id"]
    aid = repo.current_artifact(conn, sid, "analysis")["id"]
    with conn:       # 還原成升級前的狀態:結論列在、artifact 欄是 NULL
        conn.execute("UPDATE conclusion SET analysis_artifact_id = NULL WHERE story_id = ?", (sid,))
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] is None
    importer.import_story(conn, root / "mini", 11.0)
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] == aid
    with conn:
        other, _ = repo.add_artifact(conn, sid, 1, "analysis", 1, {"x": 1}, {}, 0)
        repo.set_conclusion_artifact(conn, sid, "c0001", other)   # 已有值,不被覆蓋
    assert repo.conclusions(conn, sid)[0]["analysis_artifact_id"] == aid
