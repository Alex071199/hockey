from fastapi import APIRouter, HTTPException, Query

from app import highlightly

router = APIRouter(prefix="/api", tags=["standings"])


@router.get("/standings")
async def get_standings(league: str = Query(default="KHL")):
    try:
        return await highlightly.get_standings(league)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Standings upstream error: {e}")


@router.post("/admin/standings/refresh")
async def refresh_standings(league: str = Query(default="KHL")):
    try:
        return await highlightly.refresh_standings(league)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Standings upstream error: {e}")
