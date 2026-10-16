from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_serializer
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Match

router = APIRouter(prefix="/api", tags=["schedule"])


class StreamUrl(BaseModel):
    url: str
    quality: str
    source: str


class MatchResponse(BaseModel):
    id: int
    match_uid: str
    league: str
    team_home: str
    team_away: str
    datetime_utc: datetime
    status: str
    added_live: bool = False
    stream_urls: list[StreamUrl]
    home_score: int | None = None
    away_score: int | None = None
    current_period: str | None = None
    updated_at: datetime | None = None
    sp_match_id: int | None = None

    model_config = {"from_attributes": True}

    @field_serializer("datetime_utc", "updated_at")
    def serialize_dt(self, v: datetime | None, _info):
        if v is None:
            return None
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/schedule", response_model=list[MatchResponse])
async def get_schedule(
    league: str | None = None,
    date: str | None = None,
    status: str | None = None,
    in_schedule: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Datetimes are stored in UTC — build the default window in UTC too,
    # otherwise matches disappear after local midnight (e.g. UTC+6).
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)
    else:
        today = now.date()
        start = datetime.combine(today, datetime.min.time())
        end = start + timedelta(days=2)

    query = select(Match).where(Match.datetime_utc >= start, Match.datetime_utc < end)

    if league:
        query = query.where(Match.league == league.upper())
    if status:
        query = query.where(Match.status == status)
    if in_schedule:
        query = query.where(Match.added_live == False)  # noqa: E712

    query = query.order_by(Match.datetime_utc.asc())
    result = await db.execute(query)
    matches = result.scalars().all()
    return matches


@router.get("/schedule/team/{team}", response_model=list[MatchResponse])
async def get_team_schedule(
    team: str,
    month: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if month:
        try:
            target = datetime.strptime(month, "%Y-%m")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM.")
        start = datetime(target.year, target.month, 1)
        end = datetime(target.year + (1 if target.month == 12 else 0), (target.month % 12) + 1, 1)
    else:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start = datetime(now.year, now.month, 1)
        end = datetime(now.year + (1 if now.month == 12 else 0), (now.month % 12) + 1, 1)

    query = (
        select(Match)
        .where(
            Match.datetime_utc >= start,
            Match.datetime_utc < end,
            or_(Match.team_home == team, Match.team_away == team),
        )
        .order_by(Match.datetime_utc.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/schedule/{match_id}", response_model=MatchResponse)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match
