"""atomicio 契約:讀者永遠看到完整舊檔或完整新檔,絕不讀到半份。

下游(viz/render/index)全靠它杜絕 partial-write —— 前端讀到半份 viz.json
會炸得莫名其妙,所以這裡的失敗路徑要釘死。
"""
import pytest

import atomicio


def test_writes_content(tmp_path):
    p = tmp_path / "a.json"
    atomicio.write_text_atomic(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_replaces_existing_completely(tmp_path):
    """新內容比舊的短 → 不得殘留舊檔尾巴(這正是非原子寫的典型症狀)。"""
    p = tmp_path / "a.json"
    p.write_text("old-and-very-long", encoding="utf-8")
    atomicio.write_text_atomic(p, "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_accepts_str_path(tmp_path):
    """簽章收 str 或 Path 都要能用(呼叫端兩種都有)。"""
    p = tmp_path / "a.json"
    atomicio.write_text_atomic(str(p), "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_failure_leaves_old_file_intact_and_no_tmp(tmp_path, monkeypatch):
    """寫入中途爆炸 → 舊檔完好、且不留 .tmp 垃圾。"""
    p = tmp_path / "a.json"
    p.write_text("original", encoding="utf-8")

    class Boom(Exception):
        pass

    def boom(*a, **k):
        raise Boom("disk on fire")

    monkeypatch.setattr(atomicio.os, "replace", boom)
    with pytest.raises(Boom):
        atomicio.write_text_atomic(p, "new")

    assert p.read_text(encoding="utf-8") == "original", "舊檔被動到了"
    assert list(tmp_path.glob("*.tmp")) == [], "tmp 檔沒清掉"


def test_tmp_cleanup_survives_unlink_failure(tmp_path, monkeypatch):
    """清 tmp 時連 unlink 都失敗 → 仍要把原始例外拋出去(不得被 OSError 蓋掉)。"""
    p = tmp_path / "a.json"
    p.write_text("original", encoding="utf-8")

    class Boom(Exception):
        pass

    def boom(*a, **k):
        raise Boom("disk on fire")

    def unlink_fails(*a, **k):
        raise OSError("cannot unlink either")

    monkeypatch.setattr(atomicio.os, "replace", boom)
    monkeypatch.setattr(atomicio.os, "unlink", unlink_fails)

    with pytest.raises(Boom):        # 原始死因,不是 OSError
        atomicio.write_text_atomic(p, "new")

    assert p.read_text(encoding="utf-8") == "original"
