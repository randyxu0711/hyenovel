"""原文解碼 / 正規化(從 server/ingest.py 搬來,行為不變)。

放在確定性層是因為 den(MCP 路徑)與舊 server 都要用同一份:編碼陷阱的教訓只該有一處。
"""
import io
import logging
import re

log = logging.getLogger("hyenovel")


def decode(data: bytes) -> str:
    # utf-16 無 BOM 時,對任何偶數長度的 bytes 幾乎都會「成功」——不拋錯,只吐亂碼。
    # 純中文的 big5 檔必為偶數 bytes,會被它整個吃掉(他走進門。→ 䲥ꮨ榶寧䎡),
    # 且全程無錯:亂碼直接寫進 source.md,analyst 拿去分析。故 utf-16 只在有 BOM 時試。
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    # utf-8-sig 先試:吃掉 Windows 記事本常加的 BOM(否則 ﻿ 會污染首句引用)。
    for enc in ("utf-8-sig", "big5", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)     # 行尾空白
    text = re.sub(r"\n{3,}", "\n\n", text)     # 過多空行收成一個段落間隔
    return text.strip() + "\n"


def extract_text(filename: str, data: bytes) -> str:
    """txt/md/pdf/docx → 正規化純文字。壞檔 / 加密 → ValueError。大小上限由呼叫端檢查。"""
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    try:
        if ext == "pdf":
            text = _pdf(data)
        elif ext == "docx":
            text = _docx(data)
        else:                   # txt / md / 其餘:當純文字解(decode 有 fallback,不會拋)
            text = decode(data)
    except Exception as e:      # pypdf / docx 解析失敗(壞檔 / 加密)→ 友善訊息,不冒成 500
        # 給使用者的訊息刻意只留型別;真正的 traceback 落 log。只記檔名+例外,不記內容。
        log.exception(f"event=extract-fail file={filename!r} ext={ext}")
        raise ValueError(f"讀不了這個檔(可能損壞或加密):{type(e).__name__}")
    return normalize(text)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def _docx(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n\n".join(p.text for p in doc.paragraphs)
