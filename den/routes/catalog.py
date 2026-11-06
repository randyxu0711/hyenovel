"""角色與主題清單。"""
from fastapi import APIRouter

from den import characters, themes

router = APIRouter()


@router.get("/characters")
async def list_characters():
    return {"characters": characters.builtins(), "default": characters.DEFAULT_CHARACTER}


@router.get("/themes")
async def list_themes():
    return {"themes": themes.builtins(), "default": themes.DEFAULT_THEME}
