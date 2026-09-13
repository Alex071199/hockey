from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["leagues"])


@router.get("/leagues")
async def get_leagues():
    return [
        {"id": "KHL", "name": "КХЛ"},
        {"id": "VHL", "name": "ВХЛ"},
        {"id": "MHL", "name": "МХЛ"},
    ]
