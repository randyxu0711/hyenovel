"""新故事 ingestion:抽文字(txt/pdf/docx)→ 預覽 → 落 source.md。

兩步(human-in-the-loop):extract 只抽不寫(讓使用者在前端掃一眼、能改),
create 才配 slug 落檔。理由:PDF/docx 抽出的髒字會毒死 analyst 的逐字引用閘門,
所以「預覽改字」不是可選的。slug 走既有 sNN 慣例自動遞增。

title 目前不落檔:analyst 讀完故事會自己定 title(進 analysis.json → index)。
"""
import io
import re

from . import config


def extract_text(filename: str, data: bytes) -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext == "pdf":
        text = _pdf(data)
    elif ext == "docx":
        text = _docx(data)
    else:                       # txt / md / 其餘:當純文字解
        text = _decode(data)
    return _normalize(text)


def _decode(data: bytes) -> str:
    # utf-8-sig 先試:吃掉 Windows 記事本常加的 BOM(否則 ﻿ 會污染首句引用)。
    for enc in ("utf-8-sig", "utf-16", "big5", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def _docx(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n\n".join(p.text for p in doc.paragraphs)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)     # 行尾空白
    text = re.sub(r"\n{3,}", "\n\n", text)     # 過多空行收成一個段落間隔
    return text.strip() + "\n"


def next_slug() -> str:
    """掃 stories/ 找 sNN 最大值 +1,格式 s%02d。"""
    nums = []
    if config.STORIES.exists():
        for d in config.STORIES.iterdir():
            m = re.fullmatch(r"s(\d+)", d.name)
            if d.is_dir() and m:
                nums.append(int(m.group(1)))
    return f"s{(max(nums) + 1) if nums else 1:02d}"


def create_story(title: str, text: str) -> str:
    if not text.strip():
        raise ValueError("空白故事,不建立。")
    slug = next_slug()
    d = config.STORIES / slug
    d.mkdir(parents=True, exist_ok=False)
    (d / "source.md").write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return slug
