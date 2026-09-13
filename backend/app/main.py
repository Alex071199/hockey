import asyncio
from contextlib import asynccontextmanager
import json
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.scheduler.tasks import setup_scheduler, scheduler, scrape_and_update
from app.ws import manager


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%SZ")
        return super().default(o)


class UtcJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, cls=DateTimeEncoder, ensure_ascii=False).encode("utf-8")


async def startup_scrape():
    await scrape_and_update()


async def startup_standings():
    if not settings.HIGHLIGHTLY_API_KEY:
        return
    try:
        from app import highlightly

        await highlightly.refresh_standings("KHL")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    setup_scheduler()
    asyncio.create_task(startup_scrape())
    asyncio.create_task(startup_standings())
    yield
    scheduler.shutdown()


app = FastAPI(title="Hockey Schedule API", lifespan=lifespan, default_response_class=UtcJSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.schedule import router as schedule_router
from app.api.proxy import router as proxy_router
from app.api.leagues import router as leagues_router
from app.api.standings import router as standings_router
from app.api.results import router as results_router

app.include_router(schedule_router)
app.include_router(proxy_router)
app.include_router(leagues_router)
app.include_router(standings_router)
app.include_router(results_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/admin/scrape")
async def trigger_scrape():
    asyncio.create_task(scrape_and_update())
    return {"status": "scrape_started"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
