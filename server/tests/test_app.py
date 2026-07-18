"""app 的 HTTP 契約:錯誤要分流成對的狀態碼(不是一律 500)。完全不碰 LLM。

module-level TestClient(app) 不會觸發 lifespan/startup(那需要 with 區塊),
所以不會起 sweep 背景 task —— 正是我們要的。
"""
import pytest
from fastapi.testclient import TestClient

from server import config, ingest
from server.app import app

client = TestClient(app)


@pytest.fixture
def stories(tmp_path, monkeypatch):
    d = tmp_path / "stories"
    d.mkdir()
    monkeypatch.setattr(config, "STORIES", d)
    return d


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


# ── 上傳:大小與壞檔要分流 ───────────────────────────────────────────

def test_oversized_upload_returns_413():
    """先讀 MAX+1 bytes 就擋 → 巨檔不會整個進記憶體。"""
    big = b"x" * (config.MAX_UPLOAD_BYTES + 1)
    r = client.post("/api/stories/extract", files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 413


def test_corrupt_pdf_returns_400_not_500():
    """壞檔是使用者的問題(400),不是伺服器爆炸(500)。"""
    r = client.post("/api/stories/extract",
                    files={"file": ("broken.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 400
    assert "讀不了" in r.json()["detail"]


def test_extract_returns_text_and_count():
    r = client.post("/api/stories/extract",
                    files={"file": ("a.txt", "他走進門。".encode("utf-8"), "text/plain")})
    assert r.status_code == 200
    body = r.json()
    assert body["text"].startswith("他走進門。")
    assert body["chars"] > 0


# ── 建故事 ──────────────────────────────────────────────────────────

def test_create_story_returns_slug(stories):
    r = client.post("/api/stories", json={"title": "標題", "text": "他走進門。"})
    assert r.status_code == 200
    assert r.json()["slug"] == "s01"
    assert (stories / "s01" / "source.md").exists()


def test_create_empty_story_returns_400(stories):
    r = client.post("/api/stories", json={"title": "空", "text": "   \n "})
    assert r.status_code == 400
    assert "空白" in r.json()["error"]


def test_create_oversized_story_returns_400(stories):
    """繞過 extract 直接 POST 長文 → 同一道界要擋(不能只在上傳那邊擋)。"""
    r = client.post("/api/stories", json={"title": "長", "text": "字" * config.MAX_UPLOAD_BYTES})
    assert r.status_code == 400


# ── slug 白名單:路徑穿越與 argv 注入 ────────────────────────────────

@pytest.mark.parametrize("bad", ["-evil", "a.b", "a/b", "x" * 65, "..", "%2e%2e"])
def test_invalid_slug_is_rejected(bad, stories):
    """slug 會拼路徑、也會當 argv 位置參數餵子行程。

    首字限英數/底線(擋開頭 '-' 的 flag 注入);字元集不含 '/' 與 '.'
    (連帶擋掉 ../ 與絕對路徑);長度上限 64。

    (空 slug 不在此列:`/api/usage/` 在 URL 層就 match 到 `/api/usage`
     那條「列全部」的 route,根本走不到 {slug}。)
    """
    r = client.get(f"/api/usage/{bad}")
    assert r.status_code in (400, 404), f"非法 slug {bad!r} 沒被擋下"


def test_valid_slug_passes(stories):
    (stories / "s01").mkdir()
    r = client.get("/api/usage/s01")
    assert r.status_code == 200


def test_usage_all_is_callable(stories):
    r = client.get("/api/usage")
    assert r.status_code == 200


def test_critique_running_is_callable():
    r = client.get("/api/critique/running")
    assert r.status_code == 200
    assert "running" in r.json()


def test_cancel_unknown_run_returns_false(stories):
    r = client.delete("/api/critique/s99")
    assert r.status_code == 200
    assert r.json() == {"cancelled": False}


def test_reanalyze_incomplete_story_returns_409(stories):
    """mode=reanalyze 對『未完成』故事(缺 feedback/viz)守門失敗 → 409,不是憑空 500。

    守門在 critique.reanalyze() 內用 ValueError 擋,app 層接住轉 409;
    走不到 orchestrator,純路由測試不碰真的 LLM。
    """
    d = stories / "s01"
    d.mkdir()
    (d / "source.md").write_text("他走進門。\n", encoding="utf-8")
    r = client.post("/api/critique/s01", json={"mode": "reanalyze", "title": "標題"})
    assert r.status_code == 409
