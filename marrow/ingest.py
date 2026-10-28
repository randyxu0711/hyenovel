"""原文解碼 / 正規化(從 server/ingest.py 搬來,行為不變)。

放在確定性層是因為 den(MCP 路徑)與舊 server 都要用同一份:編碼陷阱的教訓只該有一處。
"""
import re


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
