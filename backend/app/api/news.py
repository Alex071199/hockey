from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import desc, select

from app.database import async_session
from app.models import News

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
async def get_news(limit: int = 30):
    """Последние новости из Telegram-бота — для колокольчика на сайте."""
    async with async_session() as db:
        res = await db.execute(
            select(News).order_by(desc(News.id)).limit(min(limit, 100))
        )
        items = res.scalars().all()

    out = []
    for n in items:
        created = None
        if n.created_at is not None:
            dt = n.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            created = dt.isoformat()
        out.append({"id": n.id, "text": n.text or "", "created_at": created})
    return out
