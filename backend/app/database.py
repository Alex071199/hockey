from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings


def _create_engine():
    url = settings.DATABASE_URL
    connect_args = {}
    if url.startswith("sqlite+aiolibsql://") and settings.TURSO_AUTH_TOKEN:
        connect_args["auth_token"] = settings.TURSO_AUTH_TOKEN
    return create_async_engine(url, echo=False, connect_args=connect_args)


engine = _create_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(bind) -> None:
    """Add columns that were added after initial schema creation."""
    import sqlite3
    from sqlalchemy import inspect, text

    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "matches" not in tables:
        return

    existing = {col["name"] for col in inspector.get_columns("matches")}
    additions = []
    if "home_score" not in existing:
        additions.append("ALTER TABLE matches ADD COLUMN home_score INTEGER")
    if "away_score" not in existing:
        additions.append("ALTER TABLE matches ADD COLUMN away_score INTEGER")
    if "current_period" not in existing:
        additions.append("ALTER TABLE matches ADD COLUMN current_period VARCHAR")
    if "sp_match_id" not in existing:
        additions.append("ALTER TABLE matches ADD COLUMN sp_match_id INTEGER")

    if "donations" in tables:
        dexisting = {col["name"] for col in inspector.get_columns("donations")}
        if "tx_id" not in dexisting:
            additions.append("ALTER TABLE donations ADD COLUMN tx_id VARCHAR")
        if "message" not in dexisting:
            additions.append("ALTER TABLE donations ADD COLUMN message VARCHAR")

    for stmt in additions:
        try:
            bind.execute(text(stmt))
        except Exception:
            pass
