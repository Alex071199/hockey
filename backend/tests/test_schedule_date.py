"""Окно даты /api/schedule: на прошедшую дату не подмешиваются live-матчи.

Регрессия: раньше ветка `status == "live"` применялась к ЛЮБОЙ запрошенной
дате, поэтому на прошедших датах календаря показывались сегодняшние эфиры.
"""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

import app.models  # noqa: F401  — init_db строит метаданные по моделям
from app.database import async_session, init_db
from app.main import app
from app.models import Match

UID_PAST = "__test_sched_past__"
UID_LIVE_TODAY = "__test_sched_live_today__"
UID_LIVE_FUTURE = "__test_sched_live_future__"
_UIDS = (UID_PAST, UID_LIVE_TODAY, UID_LIVE_FUTURE)


async def _insert(match_uid: str, dt: datetime, status: str) -> None:
    async with async_session() as session:
        session.add(
            Match(
                match_uid=match_uid,
                league="TEST",
                team_home=f"ТестДом {match_uid}",
                team_away=f"ТестГости {match_uid}",
                datetime_utc=dt,
                status=status,
                stream_urls=[],
            )
        )
        await session.commit()


async def _cleanup() -> None:
    async with async_session() as session:
        await session.execute(delete(Match).where(Match.match_uid.in_(_UIDS)))
        await session.commit()


@pytest.mark.asyncio
async def test_past_date_does_not_mix_live_matches():
    await init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    yesterday = (now - timedelta(days=1)).date()
    try:
        # завершённый матч прошедшего дня — должен отдаваться на свою дату
        await _insert(
            UID_PAST,
            datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=12),
            "finished",
        )
        # идущий сейчас — виден «сегодня», но НЕ на прошедшей дате
        await _insert(UID_LIVE_TODAY, now, "live")
        # live вне окна дня (дальше чем сегодня+2) — виден только из-за
        # live-ветки запроса (это её прямая задача: эфиры не пропадают)
        await _insert(UID_LIVE_FUTURE, now + timedelta(days=3), "live")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            past = await client.get(f"/api/schedule?date={yesterday}&tz_offset=0")
            today = await client.get("/api/schedule")

        assert past.status_code == 200
        past_uids = {m["match_uid"] for m in past.json()}
        assert UID_PAST in past_uids, "матчи прошедшего дня должны отдаваться"
        assert UID_LIVE_TODAY not in past_uids, (
            "сегодняшний live не должен подмешиваться на прошедшую дату"
        )

        assert today.status_code == 200
        today_uids = {m["match_uid"] for m in today.json()}
        assert UID_LIVE_TODAY in today_uids, "live должен быть виден в окне «сейчас»"
        assert UID_LIVE_FUTURE in today_uids, (
            "live вне окна дня входит только через live-ветку — она должна работать"
        )
    finally:
        await _cleanup()
