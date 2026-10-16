import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SITE_URL = "https://www.hockey-live.online"
LEAGUE_LABELS = {"KHL": "КХЛ", "VHL": "ВХЛ", "MHL": "МХЛ"}


def match_url(match) -> str:
    if match and match.id and match.league:
        return f"{SITE_URL}/{match.league.lower()}/match/{match.id}"
    return f"{SITE_URL}/schedule"


async def _send(chat_id: str, text: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, cannot send reminder")
        return False
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            data = resp.json()
        if not data.get("ok"):
            logger.warning("telegram send failed: %s", data)
        return bool(data.get("ok"))
    except Exception as e:
        logger.warning("telegram send error: %s", e)
        return False


async def send_reminders() -> None:
    """Send Telegram reminders: 5 minutes before start and when the match goes live."""
    from app.database import async_session
    from app.models import Match, Reminder
    from sqlalchemy import select

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with async_session() as db:
        result = await db.execute(
            select(Reminder).where(
                Reminder.chat_id.isnot(None),
                (Reminder.soon_sent == False) | (Reminder.live_sent == False),  # noqa: E712
            )
        )
        reminders = result.scalars().all()
        if not reminders:
            return

        match_ids = [r.match_id for r in reminders if r.match_id]
        matches: dict[int, Match] = {}
        if match_ids:
            mres = await db.execute(select(Match).where(Match.id.in_(match_ids)))
            matches = {m.id: m for m in mres.scalars().all()}

        for r in reminders:
            match = matches.get(r.match_id) if r.match_id else None

            # resolve match by teams if id is missing/stale
            if not match:
                h = (r.team_home or "").strip().lower()
                a = (r.team_away or "").strip().lower()
                mres = await db.execute(
                    select(Match).where(
                        Match.datetime_utc >= now - timedelta(days=1),
                        Match.datetime_utc <= now + timedelta(days=7),
                    )
                )
                for m in mres.scalars().all():
                    mh = (m.team_home or "").strip().lower()
                    ma = (m.team_away or "").strip().lower()
                    if (mh == h and ma == a) or (mh == a and ma == h):
                        match = m
                        r.match_id = m.id
                        break

            dt = r.datetime_utc or (match.datetime_utc if match else None)
            is_live = bool(match and match.status == "live")
            league = (r.league or (match.league if match else "") or "").upper()
            url = match_url(match)
            label = LEAGUE_LABELS.get(league, league)

            # 5 minutes before scheduled start
            if not r.soon_sent and dt:
                delta = (dt - now).total_seconds()
                if -60 <= delta <= 300:
                    text = (
                        f"🏒 Матч {r.team_home} — {r.team_away} начнётся через 5 минут.\n"
                        f"Лига: {label}\n"
                        f"Ссылка на трансляцию: {url}"
                    )
                    if await _send(r.chat_id, text):
                        r.soon_sent = True

            # match went live
            if not r.live_sent and (is_live or (dt and now >= dt + timedelta(minutes=3))):
                if is_live:
                    text = (
                        f"🔴 Матч {r.team_home} — {r.team_away} уже идёт!\n"
                        f"Смотреть: {url}"
                    )
                    if await _send(r.chat_id, text):
                        r.live_sent = True
                        r.soon_sent = True
                elif dt and now >= dt + timedelta(hours=3) and match and match.status == "finished":
                    r.live_sent = True
                    r.soon_sent = True
                elif dt and now >= dt + timedelta(hours=4):
                    # too late, don't spam
                    r.live_sent = True
                    r.soon_sent = True

        await db.commit()
