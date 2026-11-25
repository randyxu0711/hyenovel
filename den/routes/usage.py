"""用量頁:帳本彙總(唯讀,不花額度)。"""
import time
from typing import Literal

from fastapi import APIRouter, Request

from den import characters
from den.views import _title
from marrow import repo, usage

router = APIRouter()

DAYS = {"7": 7, "30": 30}


def _name(conn, character_id: str | None) -> dict | None:
    if character_id is None:
        return None
    found = characters.get(conn, character_id)
    return found["name"] if found else {"zh-Hant": character_id, "en": character_id}


@router.get("/usage")
async def get_usage(request: Request, since: Literal["7", "30", "all"] = "7"):
    conn = request.app.state.mgr.conn
    now = time.time()
    all_rows = repo.calls_since(conn, 0)
    rows = all_rows if since == "all" else [r for r in all_rows if r["started_at"] >= now - DAYS[since] * 86400]
    out = usage.page(conn, rows, all_rows, now)
    for w in out["works"]:
        w["title"] = _title(conn, w["story_id"])
    for r in out["compare"]["character"]:
        r["name"] = _name(conn, r["character_id"])
    return out
