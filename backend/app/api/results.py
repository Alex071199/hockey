from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app import highlightly

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
        return await highlightly.get_results(league, date_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Results upstream error: {e}")


@router.post("/admin/results/refresh")
async def refresh_results(
    league: str = Query(default="KHL"),
    date: str | None = Query(default=None),
):
    date_str = _validate_date(date) if date else _default_date()
    try:
        return await highlightly.refresh_results(league, date_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Results upstream error: {e}")


@router.get("/match-stats")
async def get_match_stats(
    league: str = Query(default="KHL"),
    date: str | None = Query(default=None),
    home: str = Query(default=""),
    away: str = Query(default=""),
):
    if not home or not away:
        raise HTTPException(status_code=400, detail="home and away query params are required")
    date_str = _validate_date(date) if date else _default_date()
    try:
        return await highlightly.get_match_stats(league, date_str, home, away)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Match stats upstream error: {e}")
