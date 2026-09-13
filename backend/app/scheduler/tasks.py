import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, delete

from app.config import settings
from app.database import async_session
from app.models import Match
from app.scraper.livetv import scrape_livetv_matches
from app.scraper.onhockey import scrape_onhockey_matches
from app.ws import manager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id,
        "match_uid": m.match_uid,
        "league": m.league,
        "team_home": m.team_home,
        "team_away": m.team_away,
        "datetime_utc": m.datetime_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if m.datetime_utc else None,
        "status": m.status,
        "added_live": bool(m.added_live),
        "stream_urls": m.stream_urls or [],
    }


async def scrape_and_update() -> None:
    logger.info("Starting scheduled scrape...")

    livetv_matches = []
    try:
        livetv_matches = await scrape_livetv_matches()
        logger.info("LiveTV: found %d matches (KHL)", len(livetv_matches))
    except Exception as e:
        logger.warning("LiveTV scrape failed: %s", e)

    onhockey_matches = []
    try:
        onhockey_matches = await scrape_onhockey_matches()
        logger.info("OnHockey: found %d matches (VHL+MHL)", len(onhockey_matches))
    except Exception as e:
        logger.warning("OnHockey scrape failed: %s", e)

    all_scraped = livetv_matches + onhockey_matches
    scraped_uids = {m.get("livetv_id") or m.get("team_home", "")[:10] for m in all_scraped}

    changed_ids: list[int] = []
    khl_finished = False

    async with async_session() as db:
        for match_data in all_scraped:
            if match_data.get("livetv_id"):
                uid = f"LT_{match_data['livetv_id']}"
            else:
                today = datetime.now(timezone.utc).replace(tzinfo=None).date()
                h = int(match_data.get("hour", 0))
                mi = int(match_data.get("minute", 0))
                uid = f"OH_{match_data['league']}_{h:02d}{mi:02d}_{match_data['team_home'][:10]}"

            result = await db.execute(
                select(Match).where(Match.match_uid == uid)
            )
            existing = result.scalar_one_or_none()

            stream_urls = match_data.get("stream_urls", [])

            if existing:
                if stream_urls:
                    existing.stream_urls = stream_urls
                if match_data.get("status"):
                    if (
                        match_data["status"] == "finished"
                        and existing.status != "finished"
                        and (match_data.get("league") or existing.league) == "KHL"
                    ):
                        khl_finished = True
                    existing.status = match_data["status"]
                if match_data.get("datetime_utc"):
                    existing.datetime_utc = match_data["datetime_utc"]
                changed_ids.append(existing.id)
            else:
                dt_utc = match_data.get("datetime_utc")
                status = match_data.get("status", "pre_game")

                if not dt_utc:
                    # onhockey schedule times are already UTC (verified
                    # against livetv KHL kickoff times) — no shift needed.
                    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                    today = now_utc.date()
                    h = int(match_data.get("hour", 0))
                    mi = int(match_data.get("minute", 0))
                    dt_utc = datetime.combine(today, datetime.min.time()).replace(hour=h, minute=mi)
                    if dt_utc > now_utc + timedelta(days=2):
                        dt_utc -= timedelta(days=1)
                    if dt_utc + timedelta(hours=3) < now_utc:
                        status = "finished"
                    elif dt_utc <= now_utc <= dt_utc + timedelta(hours=3):
                        status = "live"

                new_match = Match(
                    match_uid=uid,
                    league=match_data["league"],
                    team_home=match_data["team_home"],
                    team_away=match_data["team_away"],
                    datetime_utc=dt_utc,
                    status=status,
                    added_live=(status == "live"),
                    stream_urls=stream_urls,
                )
                if status == "pre_game" and dt_utc:
                    # Трансляции добавляем только за 5 минут до начала —
                    # будущие игры не должны заранее висеть в списке.
                    now_gate = datetime.now(timezone.utc).replace(tzinfo=None)
                    if dt_utc - now_gate > timedelta(minutes=5):
                        logger.info(
                            "Skipping early pre_game: %s - %s [%s] at %s",
                            match_data["team_home"], match_data["team_away"],
                            match_data.get("league"), dt_utc,
                        )
                        continue
                if status == "finished" and match_data.get("league") == "KHL":
                    khl_finished = True
                db.add(new_match)
                await db.flush()
                changed_ids.append(new_match.id)
                logger.info("Added match: %s - %s [%s]", match_data["team_home"], match_data["team_away"], match_data["league"])

        result = await db.execute(
            select(Match).where(Match.status.in_(["pre_game", "live"]))
        )
        active = result.scalars().all()
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        for m in active:
            if not m.datetime_utc:
                continue
            if m.datetime_utc + timedelta(hours=3) < now_utc and m.status != "finished":
                m.status = "finished"
                changed_ids.append(m.id)
                if m.league == "KHL":
                    khl_finished = True
            elif m.status == "pre_game" and m.datetime_utc <= now_utc:
                # onhockey matches never arrive with status set — flip to live
                # once the game window starts so cards show "Смотреть".
                m.status = "live"
                changed_ids.append(m.id)

        await db.commit()

    if khl_finished:
        try:
            from app import highlightly

            highlightly.invalidate_results("KHL")
            refreshed = await highlightly.refresh_standings_if_due("KHL")
            if refreshed:
                logger.info("Standings refreshed after KHL match finished")
        except Exception as e:
            logger.warning("Standings refresh after finish failed: %s", e)

    if changed_ids:
        unique_ids = list(set(changed_ids))
        async with async_session() as db:
            result = await db.execute(select(Match).where(Match.id.in_(unique_ids)))
            await manager.broadcast({
                "type": "matches_update",
                "data": [_match_to_dict(m) for m in result.scalars().all()],
            })

    logger.info("Scrape complete: %d matches total", len(all_scraped))
    await warmup_stream_cache()


async def warmup_stream_cache() -> None:
    """Pre-resolve livetv player pages in the background, so that opening
    a stream is served from cache instead of cold-fetching the whole
    iframe chain (webplayer -> abisnews -> player)."""
    try:
        from app.api.proxy import _resolve_livetv_player
    except Exception as e:
        logger.warning("Stream warmup import failed: %s", e)
        return

    async with async_session() as db:
        result = await db.execute(select(Match).where(Match.status == "live"))
        matches = result.scalars().all()

    urls: list[str] = []
    for m in matches:
        for s in (m.stream_urls or []):
            url = s.get("url", "")
            if "livetv903.me" in url or "livetv.sx" in url:
                urls.append(url)
    urls = list(dict.fromkeys(urls))
    if not urls:
        return

    sem = asyncio.Semaphore(4)

    async def _warm(url: str) -> None:
        async with sem:
            try:
                await _resolve_livetv_player(url)
            except Exception as e:
                logger.warning("Stream warmup failed for %s: %s", url[:80], e)

    await asyncio.gather(*(_warm(u) for u in urls))
    logger.info("Stream cache warmup done: %d livetv players", len(urls))


async def refresh_standings_job() -> None:
    """Hourly standings refresh (Highlightly updates within ~1h after games)."""
    try:
        from app import highlightly
    except Exception as e:
        logger.warning("Standings refresh import failed: %s", e)
        return
    if not settings.HIGHLIGHTLY_API_KEY:
        return
    try:
        await highlightly.refresh_standings("KHL")
    except Exception as e:
        logger.warning("Standings refresh failed: %s", e)


async def cleanup_old_matches() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    async with async_session() as db:
        await db.execute(
            delete(Match).where(
                Match.datetime_utc < cutoff,
                Match.status.in_(["pre_game", "live"]),
            )
        )
        await db.commit()
    logger.info("Cleaned up old pre_game/live matches")


def setup_scheduler() -> None:
    scheduler.add_job(
        scrape_and_update,
        "interval",
        minutes=settings.SCRAPER_INTERVAL_MINUTES,
        id="scrape_and_update",
        replace_existing=True,
    )
    scheduler.add_job(
        cleanup_old_matches,
        "interval",
        hours=6,
        id="cleanup_old_matches",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_standings_job,
        "interval",
        hours=1,
        id="refresh_standings_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")
