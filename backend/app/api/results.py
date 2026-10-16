from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app import khl_api

router = APIRouter(prefix="/api", tags=["results"])


def _default_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _validate_date(v: str) -> str:
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    return v


@router.get("/results")
async def get_results(
    league: str = Query(default="KHL"),
    date: str | None = Query(default=None),
):
    date_str = _validate_date(date) if date else _default_date()
    try:
        return await khl_api.get_results(date_str)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Results upstream error: {e}")


@router.post("/admin/results/refresh")
async def refresh_results(
    league: str = Query(default="KHL"),
    date: str | None = Query(default=None),
):
    date_str = _validate_date(date) if date else _default_date()
    try:
        from app.khl_api import _cache
        _cache.pop(f"events_{date_str}", None)
        return await khl_api.get_results(date_str)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Results refresh error: {e}")


@router.get("/match-stats")
async def get_match_stats(
    league: str = Query(default="KHL"),
    date: str | None = Query(default=None),
    home: str = Query(default=""),
    away: str = Query(default=""),
    event_id: int | None = Query(default=None),
    live: bool = Query(default=False),
):
    if event_id:
        try:
            return await khl_api.get_match_stats_by_id(event_id, live=live)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Match stats error: {e}")
    if not home or not away:
        raise HTTPException(status_code=400, detail="home and away query params are required (or event_id)")
    date_str = _validate_date(date) if date else _default_date()
    try:
        return await khl_api.get_match_stats(home, away, date_str, live=live)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Match stats upstream error: {e}")
