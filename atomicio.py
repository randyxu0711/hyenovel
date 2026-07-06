"""原子寫檔:temp 檔寫滿 → os.replace 改名。讀者永遠看到完整舊檔或完整新檔,
絕不讀到半份。給下游渲染(viz/render/index)用,杜絕 partial-write。"""
import os
import tempfile
from pathlib import Path


def write_text_atomic(path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.replace(tmp, path)          # 同一檔系內原子改名
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
