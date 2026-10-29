"""ingest 契約:大小上限、壞檔轉友善錯誤、編碼、sNN 撞號進位。

不測 pypdf / python-docx 能不能讀檔 —— 那是 lib 的行為,不是我們的決策。
測的是「壞檔進來 → 我們吐 ValueError」(好讓 endpoint 回 400 而非 500)。
"""
import pytest

from server import config, ingest


@pytest.fixture
def stories(tmp_path, monkeypatch):
    d = tmp_path / "stories"
    d.mkdir()
    monkeypatch.setattr(config, "STORIES", d)
    return d


# ── 大小上限(兩條路徑都要擋)────────────────────────────────────────

def test_oversized_upload_is_rejected():
    big = b"x" * (config.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="過大"):
        ingest.extract_text("a.txt", big)


def test_oversized_direct_post_is_rejected(stories):
    """繞過 extract 直接 POST 長文 → create_story 也要擋(同一道界)。"""
    long_text = "字" * config.MAX_UPLOAD_BYTES      # UTF-8 下每字 3 bytes,必超標
    with pytest.raises(ValueError, match="過長"):
        ingest.create_story("標題", long_text)


# ── sNN 配號 ────────────────────────────────────────────────────────

def test_next_slug_from_empty(stories):
    assert ingest.next_slug() == "s01"


def test_next_slug_takes_max_not_count(stories):
    """取最大值 +1,不是數量 +1 —— 中間刪過故事也不能撞號。"""
    (stories / "s01").mkdir()
    (stories / "s07").mkdir()
    assert ingest.next_slug() == "s08"


def test_next_slug_ignores_non_snn_dirs(stories):
    (stories / "s01").mkdir()
    (stories / "changye").mkdir()               # 舊命名,不該影響配號
    (stories / "index.json").write_text("{}", encoding="utf-8")
    assert ingest.next_slug() == "s02"


def test_next_slug_without_stories_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORIES", tmp_path / "nope")
    assert ingest.next_slug() == "s01"


# ── create_story ────────────────────────────────────────────────────

def test_create_story_writes_source(stories):
    slug = ingest.create_story("標題", "他走進門。")
    assert slug == "s01"
    assert (stories / "s01" / "source.md").read_text(encoding="utf-8") == "他走進門。\n"


def test_create_story_does_not_double_newline(stories):
    ingest.create_story("標題", "他走進門。\n")
    assert (stories / "s01" / "source.md").read_text(encoding="utf-8") == "他走進門。\n"


def test_create_story_rejects_empty(stories):
    with pytest.raises(ValueError, match="空白"):
        ingest.create_story("標題", "   \n  ")


def test_create_story_survives_slug_collision(stories, monkeypatch):
    """並發/重送撞號 → mkdir(exist_ok=False) 佔位失敗就進位重試。

    不修的話 FileExistsError 會冒成 500(雙擊「新增」就中獎)。
    """
    calls = {"n": 0}
    real_next = ingest.next_slug

    def racy():
        calls["n"] += 1
        if calls["n"] == 1:
            (stories / "s01").mkdir(exist_ok=True)   # 模擬另一個請求剛搶走 s01
            return "s01"
        return real_next()

    monkeypatch.setattr(ingest, "next_slug", racy)
    slug = ingest.create_story("標題", "他走進門。")

    assert slug == "s02", "撞號後該進位,而不是拋 FileExistsError"
    assert (stories / "s02" / "source.md").exists()


def test_create_story_gives_up_after_persistent_collision(stories, monkeypatch):
    """連撞 16 次 → 代表有別的問題,乾淨拋 RuntimeError(不無限迴圈)。"""
    def always_taken():
        (stories / "s01").mkdir(exist_ok=True)
        return "s01"

    monkeypatch.setattr(ingest, "next_slug", always_taken)
    with pytest.raises(RuntimeError, match="撞號"):
        ingest.create_story("標題", "他走進門。")
