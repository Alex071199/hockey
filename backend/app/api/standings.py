from fastapi import APIRouter, HTTPException, Query

from app import khl_api

router = APIRouter(prefix="/api", tags=["standings"])


@router.get("/standings")
async def get_standings(league: str = Query(default="KHL")):
    try:
        return await khl_api.get_standings()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Standings upstream error: {e}")


@router.post("/admin/standings/refresh")
async def refresh_standings(league: str = Query(default="KHL")):
    try:
        from app.khl_api import _cache
        _cache.pop("standings_khl", None)
        return await khl_api.get_standings()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Standings refresh error: {e}")
