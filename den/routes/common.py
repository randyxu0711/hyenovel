"""路由共用:帶 code 的錯誤、slug 檢查、跨模組的 pydantic 型別、SSE 格式。"""
import json
import logging
from typing import Annotated

from fastapi import HTTPException, Path as PathParam
from pydantic import BaseModel, Field

from den.config import valid_slug

log = logging.getLogger("hyenovel")

Seq = Annotated[int, PathParam(ge=0, le=2**63 - 1)]


class ApiError(HTTPException):
    """帶機器可讀 code 的錯誤;回應 {"detail","code","params"}。"""

    def __init__(self, status: int, code: str, detail: str, params: dict | None = None):
        super().__init__(status, detail)
        self.code = code
        self.params = params or {}


def slug_ok(slug: str, where: str) -> None:
    if not valid_slug(slug):
        log.info("event=reject where=%s reason=bad-slug slug=%r", where, slug[:64])
        raise ApiError(400, "bad-slug", "bad slug")


def unknown_work(where: str) -> ApiError:
    log.info("event=reject where=%s reason=unknown-slug", where)
    return ApiError(404, "unknown-work", "這篇不在 DB")


class ClientIn(BaseModel):
    # 外部自報字串,進 DB 與 log:限長
    name: str = Field(max_length=64)
    version: str | None = Field(default=None, max_length=64)


def sse_line(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
