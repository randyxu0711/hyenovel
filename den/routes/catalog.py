"""角色與主題清單。"""
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from den import characters, themes
from den.routes.common import ApiError

log = logging.getLogger("hyenovel")
router = APIRouter()


class DefaultCharacterIn(BaseModel):
    character: str = Field(max_length=32)


@router.get("/characters")
async def list_characters(request: Request):
    conn = request.app.state.mgr.conn
    return {"characters": characters.all_(conn), "default": characters.default_id(conn)}


@router.put("/characters/default")
async def put_default_character(body: DefaultCharacterIn, request: Request):
    conn = request.app.state.mgr.conn
    try:
        with conn:
            characters.set_default(conn, body.character)
    except characters.UnknownCharacter:
        log.info("event=reject where=default-character reason=unknown-character")
        raise ApiError(422, "unknown-character", "沒有這隻角色") from None
    return {"default": body.character}


@router.get("/themes")
async def list_themes():
    return {"themes": themes.builtins(), "default": themes.DEFAULT_THEME}
