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
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError(f"檔案過大(> {config.MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    try:
        if ext == "pdf":
            text = _pdf(data)
        elif ext == "docx":
            text = _docx(data)
        else:                   # txt / md / 其餘:當純文字解(_decode 有 fallback,不會拋)
            text = _decode(data)
    except Exception as e:      # pypdf / docx 解析失敗(壞檔 / 加密)→ 友善訊息,不冒成 500
        raise ValueError(f"讀不了這個檔(可能損壞或加密):{type(e).__name__}")
    return _normalize(text)


def _decode(data: bytes) -> str:
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
    if len(text.encode("utf-8")) > config.MAX_UPLOAD_BYTES:   # 與 extract 一致的界,擋直接 POST 繞過
        raise ValueError(f"故事過長(> {config.MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    # mkdir(exist_ok=False) 當 slug 的原子佔位:並發/重送撞號就進位重試(next_slug 會看到
    # 剛被搶走的目錄、回更大的號),避免 FileExistsError 冒成 500。撞幾次都收斂,給個保險上限。
    for _ in range(16):
        slug = next_slug()
        d = config.STORIES / slug
        try:
            d.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        (d / "source.md").write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return slug
    raise RuntimeError("slug 配號連續撞號,異常")   # 幾乎不可能:16 次都撞代表有別的問題
