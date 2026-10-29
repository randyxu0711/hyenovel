"""marrow.ingest:原文解碼 / 正規化(從 server/ingest.py 原封搬來)。"""
import io
import logging

import pytest

from marrow import ingest
from server import ingest as server_ingest


def test_decode_moved_unchanged():
    assert server_ingest._decode is ingest.decode
    assert server_ingest._normalize is ingest.normalize


def test_decode_big5():
    assert ingest.decode("他走進門。".encode("big5")) == "他走進門。"


def test_decode_utf8_bom_stripped():
    assert ingest.decode(b"\xef\xbb\xbf" + "他".encode("utf-8")) == "他"


def test_decode_utf16_bom():
    assert ingest.decode("他走".encode("utf-16")) == "他走"


def test_decode_utf16_bad_bom_falls_through():
    # BOM 開頭但不是合法 utf-16(奇數長度)→ 不拋,落到後面的 fallback
    assert isinstance(ingest.decode(b"\xff\xfe\xff"), str)


def test_decode_garbage_falls_back():
    assert isinstance(ingest.decode(b"\x81"), str)


def test_normalize():
    assert ingest.normalize("a  \r\n\r\n\r\n\r\nb\r") == "a\n\nb\n"


# ── extract_text(搬自 server/ingest.py;大小上限是呼叫端的職責)──────────

def test_extract_txt_normalized():
    assert ingest.extract_text("a.txt", b"a  \r\n\r\n\r\n\r\nb") == "a\n\nb\n"


def test_extract_md_and_no_extension_as_text():
    assert "他走進門。" in ingest.extract_text("a.md", "他走進門。".encode("utf-8"))
    assert "他走進門。" in ingest.extract_text("noext", "他走進門。".encode("utf-8"))
    assert "他走進門。" in ingest.extract_text("", "他走進門。".encode("utf-8"))


def test_extract_corrupt_pdf_friendly_error_and_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="hyenovel"):
        with pytest.raises(ValueError, match="讀不了這個檔"):
            ingest.extract_text("BROKEN.PDF", b"not a pdf")
    assert "event=extract-fail" in caplog.text


def test_extract_corrupt_docx_friendly_error():
    with pytest.raises(ValueError, match="讀不了"):
        ingest.extract_text("broken.docx", b"not a docx")


def test_extract_pdf_pages_joined():
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    assert isinstance(ingest.extract_text("a.pdf", buf.getvalue()), str)


def test_extract_docx_paragraphs_joined():
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("他走進門。")
    d.add_paragraph("屋裡沒有人。")
    buf = io.BytesIO()
    d.save(buf)
    text = ingest.extract_text("a.docx", buf.getvalue())
    assert "他走進門。" in text and "屋裡沒有人。" in text


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
