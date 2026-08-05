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

        monkeypatch.setattr(align, "_ask_session", _boom)
        r = align.rebuild()
        assert r["ok"] is True and r["skipped"] is True and r["attempts"] == 0


def test_rebuild_gates_still_apply(monkeypatch):
    """走這條路不是免死金牌:label 被竄改照樣擋,且不落地。

    這裡不 patch _ask_session —— 真的讓 label_map 的六道閘門跑,連重派一起跑完。
    """
    with _tmp_stories() as root:
        _seed(root)

        async def _always_bad(prompt):
            return _one_concept_json(label="竄改過")

        monkeypatch.setattr(align, "_ask_session",
                            lambda t, p: align._run_turns(t, p, _always_bad))
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

        monkeypatch.setattr(align, "_ask_session", _boom)
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

        monkeypatch.setattr(align, "_ask_session",
                            lambda t, p: align._run_turns(t, p, _fake))
        r = align.rebuild(force=True)
        assert r["ok"] is True and r["skipped"] is False and len(called) == 1
        assert r["attempts"] == 1


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


# ── 閘門重派 ────────────────────────────────────────────────────────
# 真實資料上三次重建有兩次被閘門擋掉(型別不符 / label 被改寫),而每次失敗
# 就是整通 ~$0.2 丟掉。critique 的閘門早就有「帶錯重派」(MAX_GATE_RETRIES),
# align 原本沒有 —— 下面四支釘住補上的那條政策。

def test_retry_prompt_carries_the_errors_not_the_answers():
    """只回饋錯誤,不回饋正解 —— 確定性層驗但不改。"""
    p = align._retry_prompt(["L027: 型別不符 —— s02/k4 是 technique,族卻標 motif"])
    assert "s02/k4" in p and "沒有通過閘門" in p
    # 不可以把「正確答案」直接餵回去(那等於偷改 LLM 的判斷)
    assert "請把 node_type 改成" not in p


def test_retry_prompt_caps_how_many_errors_it_feeds_back():
    p = align._retry_prompt([f"L{i:03d}: 錯誤" for i in range(50)])
    assert p.count("- L") <= align._MAX_ERRORS_FED_BACK
    assert "另有 30 條同類錯誤未列出" in p


def test_gate_retry_recovers_on_a_later_turn(monkeypatch):
    """第一輪被擋、第二輪修好 → 照樣落地。這就是補這條政策要買的東西。"""
    with _tmp_stories() as root:
        _seed(root)
        seen = []

        async def _bad_then_good(prompt):
            seen.append(prompt)
            return _one_concept_json(
                label="竄改過" if len(seen) == 1 else "等不到的人")

        mapping, errors, attempts = asyncio.run(
            align._run_turns(label_map.collect(), None, _bad_then_good))
        assert mapping is not None and errors == [] and attempts == 2
        assert label_map.load() is not None      # 真的寫下去了
        # 第二輪的 prompt 是重派 prompt,不是原本那份
        assert "沒有通過閘門" in seen[1]


def test_gate_retry_gives_up_at_the_limit_and_writes_nothing(monkeypatch):
    """重派有上限 —— 不可以無限燒錢。耗盡仍不落地。"""
    with _tmp_stories() as root:
        _seed(root)
        n = []

        async def _always_bad(prompt):
            n.append(1)
            return _one_concept_json(label="竄改過")

        mapping, errors, attempts = asyncio.run(
            align._run_turns(label_map.collect(), None, _always_bad))
        assert mapping is None and errors
        assert attempts == config.MAX_GATE_RETRIES + 1 == len(n)
        assert label_map.load() is None          # 全過才寫,一次都沒過就什麼都沒有
