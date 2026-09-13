import asyncio
import httpx
from app.scraper.onhockey import scrape_schedule
from app.database import init_db, async_session
from app.models import Match
from sqlalchemy import select


async def main():
    await init_db()

    async with httpx.AsyncClient(timeout=30.0) as client:
        matches = await scrape_schedule(client)

    async with async_session() as db:
        for match_data in matches:
            result = await db.execute(
                select(Match).where(Match.onhockey_id == match_data["onhockey_id"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                db.add(Match(**match_data))
                print(f"Added: {match_data['league']} {match_data['team_home']} vs {match_data['team_away']}")
            else:
                print(f"Exists: {match_data['league']} {match_data['team_home']} vs {match_data['team_away']}")
        await db.commit()

    # Verify
    async with async_session() as db:
        result = await db.execute(select(Match))
        all_matches = result.scalars().all()
        print(f"\nTotal matches in DB: {len(all_matches)}")
        for m in all_matches:
            print(f"  [{m.league}] {m.team_home} vs {m.team_away} | {m.status} | streams: {len(m.stream_urls or [])}")


asyncio.run(main())
