"""角色與主題清單。"""
import logging
import secrets
import time
from typing import Annotated, Any, Awaitable, Callable, Literal, TypedDict

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


class AnswersIn(BaseModel):
    form: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""
    wish: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


class PreviousIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=cards.MAX_NAME)]
    line: Annotated[str, StringConstraints(strip_whitespace=True, max_length=cards.MAX_LINE)] = ""


class CandidatesIn(BaseModel):
    answers: AnswersIn = AnswersIn()
    lang: Literal["zh-Hant", "en"] = "zh-Hant"
    seed: int | None = Field(default=None, ge=0, lt=2**31)
    reaction: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    previous: list[PreviousIn] = Field(default=[], max_length=candidates.COUNT)


class ReviseIn(BaseModel):
    candidate: Any = None
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    lang: Literal["zh-Hant", "en"] = "zh-Hant"


class CandidateSaveIn(BaseModel):
    candidate: Any = None
    confirm: bool = False


_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=cards.MAX_NAME)]
_Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=cards.MAX_LINE)]
NameIn = TypedDict("NameIn", {"zh-Hant": _Name, "en": _Name})
LineIn = TypedDict("LineIn", {"zh-Hant": _Line, "en": _Line})


class CardEditIn(BaseModel):
    name: NameIn
    line: LineIn
    reading: str
    confirm: bool = False


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


def _bad_card(where: str, errors: list[str]) -> ApiError:
    log.info("event=reject where=%s reason=%s", where, ",".join(errors))
    return ApiError(422, "bad-card", "這張角色卡不能存", {"errors": errors})


def _builtin() -> ApiError:
    log.info("event=reject where=character reason=builtin-character")
    return ApiError(409, "builtin-character", "內建角色不能封存或編輯")


async def _spending(state, work: Callable[[], Awaitable[dict]]) -> dict:
    if state.candidates_busy:
        log.info("event=reject where=candidates reason=busy")
        raise ApiError(409, "candidates-busy", "上一批候選還在生成")
    state.candidates_busy = True
    try:
        return await work()
    except candidates.Failed as e:
        raise ApiError(502, "candidates-failed", "候選生成失敗", {"reason": e.reason}) from None
    finally:
        state.candidates_busy = False


@router.post("/characters/candidates")
async def character_candidates(body: CandidatesIn, request: Request):
    state = request.app.state
    seed = secrets.randbelow(2**31) if body.seed is None else body.seed
    passage = candidates.opening(repo.works(state.mgr.conn))
    again = {"reaction": body.reaction, "previous": [p.model_dump() for p in body.previous]}
    return await _spending(state, lambda: candidates.generate(state.run_once, body.answers.model_dump(), passage,
                                                              body.lang, seed, again))


@router.post("/characters/candidates/revise")
async def revise_candidate(body: ReviseIn, request: Request):
    if candidates.core(body.candidate) is None:
        raise _bad_card("candidate-revise", ["bad-schema"])
    state = request.app.state
    passage = candidates.opening(repo.works(state.mgr.conn))
    return await _spending(state, lambda: candidates.revise(state.run_once, body.candidate, body.feedback, passage, body.lang))


def _name_taken(conn, name: dict) -> bool:
    mine = {v.strip().casefold() for v in name.values()}
    return any(v.strip().casefold() in mine
               for c in characters.all_(conn) if not c["archived"] for v in c["name"].values())


@router.post("/characters")
async def create_character(body: CandidateSaveIn, request: Request):
    candidate = candidates.core(body.candidate)
    if candidate is None:
        raise _bad_card("character-create", ["bad-schema"])
    card = candidates.to_card(candidate)
    scanned = cards.scan(card)
    if scanned["errors"]:
        raise _bad_card("character-create", scanned["errors"])
    conn = request.app.state.mgr.conn
    warnings = scanned["warnings"] + (["name-taken"] if _name_taken(conn, candidate["name"]) else [])
    if warnings and not body.confirm:
        return {"created": False, "warnings": warnings}
    with conn:
        character = characters.create(conn, card, time.time())
    return JSONResponse({"created": True, "character": character}, status_code=201)


@router.post("/characters/{character_id}/copy")
async def copy_character(character_id: str, request: Request):
    conn = request.app.state.mgr.conn
    try:
        with conn:
            character = characters.copy(conn, character_id, time.time())
    except characters.UnknownCharacter:
        raise _no_character() from None
    return JSONResponse({"character": character}, status_code=201)


@router.patch("/characters/{character_id}")
async def edit_character(character_id: str, body: CardEditIn, request: Request):
    conn = request.app.state.mgr.conn
    name, line = dict(body.name), dict(body.line)
    try:
        scanned = cards.scan(characters.edited_card(conn, character_id, name, line, body.reading))
        if scanned["errors"]:
            raise _bad_card("character-edit", scanned["errors"])
        if scanned["warnings"] and not body.confirm:
            return {"edited": False, "warnings": scanned["warnings"]}
        with conn:
            character = characters.edit(conn, character_id, name, line, body.reading, time.time())
    except characters.UnknownCharacter:
        raise _no_character() from None
    except characters.BuiltinCharacter:
        raise _builtin() from None
    return {"edited": True, "character": character}


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
        raise _builtin() from None
    return {"archived": character_id}


@router.get("/themes")
async def list_themes():
    return {"themes": themes.builtins(), "default": themes.DEFAULT_THEME}
