import asyncio
import logging
from contextlib import asynccontextmanager
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, init_db
from app.scheduler.tasks import setup_scheduler, scheduler, scrape_and_update, cleanup_jastar_rows
from app.ws import manager
from app import telegram

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%SZ")
        return super().default(o)


class UtcJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, cls=DateTimeEncoder, ensure_ascii=False).encode("utf-8")


async def startup_scrape():
    try:
        await cleanup_jastar_rows()
    except Exception as e:
        logger.warning("Jastar cleanup failed: %s", e)
    await scrape_and_update()


async def _notify_restart() -> None:
    """Пишет админу в бота при каждом старте — чтобы не держать ПК включённым
    в ожидании рестарта: бот сам сообщит, что сервер перезапустился."""
    admin = (settings.TELEGRAM_ADMIN_CHAT_ID or "").strip()
    if not admin:
        return
    try:
        await asyncio.sleep(3)  # даём поллеру подняться
        await telegram.send_message(
            admin,
            f"🔄 Сервер перезапущен: {datetime.utcnow().strftime('%d.%m %H:%M')} UTC\n\n"
            "Если это после деплоя — новый код уже активен.",
        )
    except Exception as e:
        logger.warning("restart notification failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from app.api.tv_auth import migrate_legacy_store

    await migrate_legacy_store()
    asyncio.create_task(_notify_restart())
    if settings.SCHEDULER_ENABLED:
        setup_scheduler()
        asyncio.create_task(startup_scrape())
    else:
        logger.info("SCHEDULER_ENABLED=false — только API, без фоновых джоб")
    poll_task = asyncio.create_task(telegram.polling_task())
    yield
    poll_task.cancel()
    if settings.SCHEDULER_ENABLED:
        scheduler.shutdown()


app = FastAPI(title="Hockey Schedule API", lifespan=lifespan, default_response_class=UtcJSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=500)

from app.api.schedule import router as schedule_router
from app.api.proxy import router as proxy_router
from app.api.leagues import router as leagues_router
from app.api.standings import router as standings_router
from app.api.results import router as results_router
from app.api.reminders import router as reminders_router
from app.api.khl_times import router as khl_times_router
from app.api.donations import router as donations_router
from app.api.broadcast import router as broadcast_router
from app.api.app_version import router as app_version_router
from app.api.news import router as news_router
from app.api.tv_auth import router as tv_auth_router

app.include_router(schedule_router)
app.include_router(proxy_router)
app.include_router(leagues_router)
app.include_router(standings_router)
app.include_router(results_router)
app.include_router(reminders_router)
app.include_router(khl_times_router)
app.include_router(donations_router)
app.include_router(broadcast_router)
app.include_router(app_version_router)
app.include_router(news_router)
app.include_router(tv_auth_router)


@app.get("/api/health")
async def health():
    from app.api.broadcast import _prime_proxies
    return {"status": "ok", "prime_proxies": len(_prime_proxies)}


@app.post("/api/admin/scrape")
async def trigger_scrape():
    asyncio.create_task(scrape_and_update())
    return {"status": "scrape_started"}


@app.get("/api/admin/reminders")
async def list_reminders(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.models import Reminder

    rows = (
        (await db.execute(select(Reminder).order_by(Reminder.id))).scalars().all()
    )
    return [
        {
            "id": r.id,
            "code": r.code,
            "team_home": r.team_home,
            "team_away": r.team_away,
            "league": r.league,
            "chat_id": r.chat_id,
            "datetime_utc": r.datetime_utc.isoformat() if r.datetime_utc else None,
            "match_id": r.match_id,
            "soon_sent": r.soon_sent,
            "live_sent": r.live_sent,
        }
        for r in rows
    ]


@app.delete("/api/admin/reminders/{reminder_id}")
async def delete_reminder_admin(reminder_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete

    from app.models import Reminder

    await db.execute(delete(Reminder).where(Reminder.id == reminder_id))
    await db.commit()
    return {"deleted": reminder_id}


@app.get("/api/admin/subscribers")
async def list_subscribers(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.models import Subscriber

    rows = (await db.execute(select(Subscriber).order_by(Subscriber.id))).scalars().all()
    return [
        {"id": r.id, "chat_id": r.chat_id, "username": r.username, "active": r.active}
        for r in rows
    ]


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
