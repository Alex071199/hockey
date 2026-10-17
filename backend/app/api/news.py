from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, delete, select, update

from app.database import async_session
from app.models import News

router = APIRouter(prefix="/api/news", tags=["news"])

# непросмотренные живут 30 дней, просмотренные — 24 часа с момента просмотра
UNREAD_TTL_DAYS = 30
SEEN_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _cleanup(db) -> None:
    now = _utcnow()
    await db.execute(
        delete(News).where(News.created_at < now - timedelta(days=UNREAD_TTL_DAYS))
    )
    await db.execute(
        delete(News).where(
            News.last_seen_at.isnot(None),
            News.last_seen_at < now - timedelta(hours=SEEN_TTL_HOURS),
        )
    )
    await db.commit()


@router.get("")
async def get_news(limit: int = 30):
    """Последние новости из Telegram-бота — для колокольчика на сайте."""
    async with async_session() as db:
        await _cleanup(db)
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


class NewsSeen(BaseModel):
    max_id: int


@router.post("/seen")
async def mark_seen(data: NewsSeen):
    """Пользователь открыл колокольчик: пометить новости просмотренными."""
    async with async_session() as db:
        await db.execute(
            update(News)
            .where(News.id <= data.max_id, News.last_seen_at.is_(None))
            .values(last_seen_at=_utcnow())
        )
        await db.commit()
    return {"ok": True}


@router.delete("/{news_id}")
async def delete_news(news_id: int):
    """Крестик в колокольчике — удалить уведомление."""
    async with async_session() as db:
        res = await db.execute(delete(News).where(News.id == news_id))
        await db.commit()
        if not res.rowcount:
            raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
