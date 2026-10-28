"""版本指紋:den/ 與 marrow/ 原始碼(不含 tests、__pycache__)的 sha256 前 12 碼。

不用手動版號:切片 6 打包前唯一的「升級」就是 git pull,手動版號一定會忘記改。
"""
import hashlib
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOTS = (_HERE, _HERE.parent / "marrow")
_SKIP = ("tests", "__pycache__")


def fingerprint(roots: tuple[Path, ...] = _ROOTS) -> str:
    h = hashlib.sha256()
    for root in roots:
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if not p.is_file() or any(part in _SKIP for part in rel.parts):
                continue
            h.update(f"{root.name}/{rel.as_posix()}".encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]
