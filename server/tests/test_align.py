"""跨篇 align 的行為契約(server/align.py)—— 零成本,不碰真實 stories/、不打真 SDK。

覆蓋率不設數字門檻(這個模組混了 ClaudeSDKClient 接線),靠下列契約守:
  ① 標籤由我們組進 prompt,不讓 LLM 自己去掃 stories/(那等於放它載入全部故事內文)
  ② prompt 不含 id —— id 是確定性層鑄的,給它看會誘導它自填
  ③ 不 stale 且沒 --force 時不花錢
  ④ 落地仍要過 label_map 的六道閘門 —— 走這條路不是免死金牌
"""
import asyncio
import json
import tempfile
from pathlib import Path

import conclusions
import label_map

from server import align, config


class _tmp_stories:
    """config / label_map / conclusions 三邊的 STORIES 都要指到同一處,
    否則測試看到的會是別的東西(甚至是真實 stories/ 底下的)。同 test_settle。"""
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._orig = (config.STORIES, label_map.STORIES, conclusions.STORIES)
        p = Path(self._t.name)
        config.STORIES = label_map.STORIES = conclusions.STORIES = p
        return p

    def __exit__(self, *a):
        config.STORIES, label_map.STORIES, conclusions.STORIES = self._orig
        self._t.cleanup()


FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "multi"


def _seed(root):
    for name in ("s01", "s02", "s03"):
        (root / name).mkdir()
        (root / name / "analysis.json").write_bytes(
            (FIXTURES / name / "analysis.json").read_bytes())


def _one_concept_json(label="等不到的人"):
    return json.dumps([{
        "canonical": "等待", "node_type": "theme",
        "members": [{"slug": "s01", "node": "t1", "label": label,
                     "why": "理由。", "evidence_index": 0}]}], ensure_ascii=False)


def test_prompt_carries_labels_not_a_directory_walk():
    with _tmp_stories() as root:
        _seed(root)
        p = align.build_prompt(label_map.collect(), None)
    assert "等不到的人" in p and "s01" in p
    # 不叫它自己去掃 —— 那等於放它載入全部故事內文
    assert "stories/" not in p


def test_prompt_never_shows_ids():
    with _tmp_stories() as root:
        _seed(root)
        prev = {"concepts": [{"id": "L042", "canonical": "等待",
                              "node_type": "theme",
                              "members": [{"slug": "s01", "node": "t1"}]}]}
        p = align.build_prompt(label_map.collect(), prev)
    assert "L042" not in p
    assert "等待" in p          # 舊族名仍給它參考(可讀性),但不給 id


def test_rebuild_skips_when_fresh(monkeypatch):
    with _tmp_stories() as root:
        _seed(root)
        label_map.build(_one_concept_json(), now=1.0)

        def _boom(*a, **k):
            raise AssertionError("不 stale 就不該花錢")

        monkeypatch.setattr(align, "_ask", _boom)
        r = align.rebuild()
        assert r["ok"] is True and r["skipped"] is True


def test_rebuild_gates_still_apply(monkeypatch):
    """走這條路不是免死金牌:label 被竄改照樣擋,且不落地。"""
    with _tmp_stories() as root:
        _seed(root)

        async def _fake(prompt):
            return _one_concept_json(label="竄改過")

        monkeypatch.setattr(align, "_ask", _fake)
        r = align.rebuild()
        # **兩個 assert 都必須在 with 裡面。** __exit__ 一還原 label_map.STORIES,
        # load() 讀的就是真實 stories/ —— 那既違反「測試絕不碰 stories/ 真實內容」,
        # 也會在 bootstrap 出 label-map.json 之後把這支測試轉紅。
        assert r["ok"] is False and r["errors"]
        assert label_map.load() is None


def test_rebuild_reports_when_there_is_nothing_to_cluster(monkeypatch):
    """一篇都沒有時不該去花錢問一個空問題。"""
    with _tmp_stories():
        def _boom(*a, **k):
            raise AssertionError("沒有標籤就不該連 SDK")

        monkeypatch.setattr(align, "_ask", _boom)
        r = align.rebuild()
        assert r["ok"] is False and r["skipped"] is False and r["errors"]


def test_rebuild_force_ignores_freshness(monkeypatch):
    with _tmp_stories() as root:
        _seed(root)
        label_map.build(_one_concept_json(), now=1.0)
        called = []

        async def _fake(prompt):
            called.append(prompt)
            return _one_concept_json()

        monkeypatch.setattr(align, "_ask", _fake)
        r = align.rebuild(force=True)
        assert r["ok"] is True and r["skipped"] is False and len(called) == 1


def test_sweep_skips_when_not_stale(monkeypatch):
    """不 stale 就不該花錢 —— 這是輪詢能成立的前提(判定只是 sha1,零成本)。"""
    with _tmp_stories() as root:
        _seed(root)
        label_map.build(_one_concept_json(), now=1.0)

        async def _boom(force=False):
            raise AssertionError("不 stale 就不該重建")

        monkeypatch.setattr(align, "rebuild_async", _boom)
        assert asyncio.run(align._sweep_once()) is False


def test_sweep_skips_while_a_run_is_active(monkeypatch):
    """有 critique 在跑就跳過。

    不只是禮貌:analysis.json 是 **analyst 交件時就寫下**的,criticizer 還要跑好幾分鐘 ——
    不擋的話 align 會在 criticizer 跑到一半時醒來,跟它搶同一個訂閱用量窗。
    """
    from server import critique

    with _tmp_stories() as root:
        _seed(root)          # 沒有 label-map.json → 一定 stale

        async def _boom(force=False):
            raise AssertionError("有 run 在跑就不該重建")

        monkeypatch.setattr(critique, "list_running", lambda: [{"slug": "s01"}])
        monkeypatch.setattr(align, "rebuild_async", _boom)
        assert asyncio.run(align._sweep_once()) is False


def test_sweep_rebuilds_when_stale(monkeypatch):
    with _tmp_stories() as root:
        _seed(root)
        called = []

        async def _fake(force=False):
            called.append(force)
            return {"ok": True, "skipped": False, "concepts": 3, "errors": []}

        monkeypatch.setattr(align, "rebuild_async", _fake)
        assert asyncio.run(align._sweep_once()) is True
        assert called == [False]


def test_sweep_reports_a_failed_rebuild_without_raising(monkeypatch, caplog):
    """重建沒過閘門 ≠ worker 出事:記一行 WARNING,這一輪照樣算跑過。"""
    with _tmp_stories() as root:
        _seed(root)

        async def _fake(force=False):
            return {"ok": False, "skipped": False, "concepts": 0, "errors": ["壞"]}

        monkeypatch.setattr(align, "rebuild_async", _fake)
        with caplog.at_level("WARNING", logger="hyenovel"):
            assert asyncio.run(align._sweep_once()) is True
    assert "event=align-fail" in caplog.text


def test_sweep_survives_a_failing_round(monkeypatch, caplog):
    """一次失敗不可以讓 worker 靜靜死掉 —— 死掉的守衛跟活著的守衛長得一樣。"""
    with _tmp_stories() as root:
        _seed(root)

        async def _boom(force=False):
            raise RuntimeError("分群掛了")

        monkeypatch.setattr(align, "rebuild_async", _boom)
        with caplog.at_level("ERROR", logger="hyenovel"):
            assert asyncio.run(align._sweep_once()) is False
    assert "event=align-sweep-fail" in caplog.text
