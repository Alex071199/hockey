import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Match, Reminder
from app.telegram import deep_link

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ReminderCreate(BaseModel):
    code: str
    league: str
    team_home: str
    team_away: str
    match_id: int | None = None
    datetime_utc: str | None = None


class ReminderOut(BaseModel):
    id: int
    linked: bool
    deep_link: str
    code: str


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        s = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


async def _find_match(
    db: AsyncSession,
    match_id: int | None,
    league: str,
    home: str,
    away: str,
) -> Match | None:
    if match_id:
        m = await db.get(Match, match_id)
        if m:
            return m
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        select(Match).where(
            Match.league == league.upper(),
            Match.datetime_utc >= now - timedelta(days=2),
            Match.datetime_utc <= now + timedelta(days=7),
        )
    )
    h = home.strip().lower()
    a = away.strip().lower()
    for m in result.scalars().all():
        mh = (m.team_home or "").strip().lower()
        ma = (m.team_away or "").strip().lower()
        if (mh == h and ma == a) or (mh == a and ma == h):
            return m
    return None


@router.post("", response_model=ReminderOut)
async def create_reminder(payload: ReminderCreate, db: AsyncSession = Depends(get_db)):
    if not CODE_RE.match(payload.code):
        raise HTTPException(status_code=400, detail="Invalid code")

    match = await _find_match(
        db, payload.match_id, payload.league, payload.team_home, payload.team_away
    )

    result = await db.execute(
        select(Reminder).where(
            Reminder.code == payload.code,
            Reminder.team_home == payload.team_home,
            Reminder.team_away == payload.team_away,
        )
    )
    reminder = result.scalar_one_or_none()

    dt = _parse_dt(payload.datetime_utc)
    if reminder:
        if match and not reminder.match_id:
            reminder.match_id = match.id
        if dt:
            reminder.datetime_utc = dt
    else:
        reminder = Reminder(
            code=payload.code,
            match_id=match.id if match else None,
            league=payload.league.upper(),
            team_home=payload.team_home,
            team_away=payload.team_away,
            datetime_utc=dt or (match.datetime_utc if match else None),
        )
        db.add(reminder)
    await db.commit()
    await db.refresh(reminder)

    return ReminderOut(
        id=reminder.id,
        linked=bool(reminder.chat_id),
        deep_link=deep_link(payload.code),
        code=payload.code,
    )


@router.get("")
async def reminder_status(
    code: str,
    team_home: str,
    team_away: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(
            Reminder.code == code,
            Reminder.team_home == team_home,
            Reminder.team_away == team_away,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"exists": False, "linked": False}
    return {
        "exists": True,
        "linked": bool(reminder.chat_id),
        "soon_sent": bool(reminder.soon_sent),
        "live_sent": bool(reminder.live_sent),
    }


@router.delete("")
async def delete_reminder(
    code: str,
    team_home: str,
    team_away: str,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(Reminder).where(
            Reminder.code == code,
            Reminder.team_home == team_home,
            Reminder.team_away == team_away,
        )
    )
    await db.commit()
    return {"deleted": True}
