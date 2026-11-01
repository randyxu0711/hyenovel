"""對話文字裡的「」引文,與它在原文的位移(code point 索引,同 marrow.gate.locate)。"""
import unicodedata

from marrow import gate

MIN_QUOTE, MAX_QUOTE = 2, 400


def _blank(s: str) -> bool:
    """strip 後沒字,或全是標點/空白(如「……」):gate.locate 對這種引文不可靠。"""
    return all(ch.isspace() or unicodedata.category(ch).startswith("P") for ch in s)


def quotes_in(text: str) -> list[str]:
    """成對「」內的文字,長度 2–400,依出現順序、去重保序。巢狀或不成對的段略過。"""
    out: list[str] = []
    i = 0
    while (a := text.find("「", i)) != -1:
        b = text.find("」", a + 1)
        if b == -1:
            break
        inner = text[a + 1:b]
        i = b + 1
        if "「" in inner:   # 巢狀:整段略過
            continue
        if MIN_QUOTE <= len(inner) <= MAX_QUOTE and not _blank(inner) and inner not in out:
            out.append(inner)
    return out


def locate_all(quotes: list[str], source: str) -> list[dict]:
    out = []
    for q in quotes:
        hit = gate.locate(q, source)
        out.append({"quote": q, "start": hit[0] if hit else None, "end": hit[1] if hit else None})
    return out
