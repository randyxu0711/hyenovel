"""角色與主題清單。"""
import logging
import secrets
import time
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from den import candidates, cards, characters, themes
from marrow import repo
from den.routes.common import ApiError

log = logging.getLogger("hyenovel")
router = APIRouter()


class DefaultCharacterIn(BaseModel):
    character: str = Field(max_length=32)


class CardImportIn(BaseModel):
    card: Any = None
    confirm: bool = False


class CandidatesIn(BaseModel):
    brief: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    seed: int | None = Field(default=None, ge=0, lt=2**31)


def _no_character() -> ApiError:
    log.info("event=reject where=character reason=unknown-character")
    return ApiError(404, "unknown-character", "沒有這隻角色")


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


@router.post("/characters/import")
async def import_character(body: CardImportIn, request: Request):
    scanned = cards.scan(body.card)
    if scanned["errors"]:
        log.info("event=reject where=character-import reason=%s", ",".join(scanned["errors"]))
        raise ApiError(422, "bad-card", "這張角色卡不能匯入", {"errors": scanned["errors"]})
    if scanned["warnings"] and not body.confirm:
        return {"imported": False, "warnings": scanned["warnings"]}
    conn = request.app.state.mgr.conn
    with conn:
        character = characters.import_card(conn, body.card, time.time())
    return JSONResponse({"imported": True, "character": character, "warnings": scanned["warnings"]}, status_code=201)


@router.post("/characters/candidates")
async def character_candidates(body: CandidatesIn, request: Request):
    state = request.app.state
    if state.candidates_busy:
        log.info("event=reject where=candidates reason=busy")
        raise ApiError(409, "candidates-busy", "上一批候選還在生成")
    state.candidates_busy = True
    seed = secrets.randbelow(2**31) if body.seed is None else body.seed
    try:
        return await candidates.generate(state.run_once, body.brief, seed)
    except candidates.Failed as e:
        raise ApiError(502, "candidates-failed", "候選生成失敗", {"reason": e.reason}) from None
    finally:
        state.candidates_busy = False


@router.get("/characters/{character_id}/card")
async def character_card(character_id: str, request: Request):
    row = repo.latest_character(request.app.state.mgr.conn, character_id)
    if row is None:
        raise _no_character()
    return JSONResponse(row["card"])


@router.delete("/characters/{character_id}")
async def archive_character(character_id: str, request: Request):
    conn = request.app.state.mgr.conn
    try:
        with conn:
            characters.archive(conn, character_id, time.time())
    except characters.UnknownCharacter:
        raise _no_character() from None
    except characters.BuiltinCharacter:
        log.info("event=reject where=character reason=builtin-character")
        raise ApiError(409, "builtin-character", "內建角色不能封存") from None
    return {"archived": character_id}


@router.get("/themes")
async def list_themes():
    return {"themes": themes.builtins(), "default": themes.DEFAULT_THEME}
