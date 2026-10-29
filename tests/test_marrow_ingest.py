"""marrow.ingest:原文解碼 / 正規化(從 server/ingest.py 原封搬來)。"""
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
