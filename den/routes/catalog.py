"""角色與主題清單。"""
from fastapi import APIRouter, Request

from den import characters, themes

router = APIRouter()


@router.get("/characters")
async def list_characters(request: Request):
    return {"characters": characters.all_(request.app.state.mgr.conn), "default": characters.DEFAULT_CHARACTER}


@router.get("/themes")
async def list_themes():
    return {"themes": themes.builtins(), "default": themes.DEFAULT_THEME}
