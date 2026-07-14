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


# ── 壞檔 → 友善 ValueError(不冒成 500)──────────────────────────────

def test_corrupt_pdf_becomes_friendly_valueerror():
    with pytest.raises(ValueError, match="讀不了"):
        ingest.extract_text("broken.pdf", b"not a pdf at all")


def test_corrupt_docx_becomes_friendly_valueerror():
    with pytest.raises(ValueError, match="讀不了"):
        ingest.extract_text("broken.docx", b"not a docx at all")


# ── 純文字路徑:編碼與正規化 ────────────────────────────────────────

def test_txt_is_normalized():
    raw = "他走進門。\r\n\r\n\r\n\r\n屋裡沒有人。   \n".encode("utf-8")
    text = ingest.extract_text("a.txt", raw)

    assert "\r" not in text                      # CRLF → LF
    assert "\n\n\n" not in text                  # 過多空行收成一個段落間隔
    assert "   \n" not in text                   # 行尾空白清掉
    assert text.endswith("\n")


def test_bom_is_stripped():
    """Windows 記事本的 BOM 會污染首句引用 → 必須吃掉,否則逐字閘門會誤判。"""
    text = ingest.extract_text("a.txt", "﻿他走進門。".encode("utf-8"))
    assert not text.startswith("﻿")
    assert text.startswith("他走進門。")


def test_big5_is_decoded():
    """台灣使用者的舊檔常是 big5(_decode 有 fallback 鏈)。"""
    text = ingest.extract_text("a.txt", "他走進門。".encode("big5"))
    assert "他走進門。" in text


def test_undecodable_bytes_do_not_crash():
    """全部編碼都試不出來 → errors='replace' 兜底,不得拋。"""
    text = ingest.extract_text("a.txt", b"\xff\xfe\x00\x01\x02rubbish")
    assert isinstance(text, str)


def test_extension_is_case_insensitive():
    """.PDF 也要走 pdf 路徑(不能因大小寫就當純文字解)。"""
    with pytest.raises(ValueError, match="讀不了"):
        ingest.extract_text("BROKEN.PDF", b"not a pdf")


def test_no_extension_treated_as_text():
    text = ingest.extract_text("noext", "他走進門。".encode("utf-8"))
    assert "他走進門。" in text


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


def test_utf16_with_bom_still_works():
    """有 BOM 的真 utf-16 檔仍要正確解(修 big5 bug 時不能把它弄壞)。"""
    text = ingest.extract_text("a.txt", "他走進門。".encode("utf-16"))   # encode 會加 BOM
    assert "他走進門。" in text


def test_encoding_priority_favors_big5_over_gb18030():
    """記錄一個刻意的取捨,不是 bug。

    big5 與 gb18030 互相都能「成功」解對方的 bytes(吐亂碼)——這是無 BOM
    編碼猜測的固有歧義,不引入 chardet 之類的偵測器就無解。

    fallback 鏈把 big5 排在 gb18030 前面 = 押注「使用者寫繁中/台語」。
    代價:純簡體的 gb18030 檔會被 big5 搶先解成亂碼。這是接受的。

    (真正的 bug 是 utf-16 曾排在最前面 —— 它對任何偶數 bytes 都「成功」,
     把 big5 和 gb18030 兩行都變成死碼。已修:utf-16 只在有 BOM 時試。)
    """
    text = ingest.extract_text("a.txt", "他走進門。".encode("big5"))
    assert "他走進門。" in text, "繁中 big5 必須正確解出來(這是主要使用情境)"
