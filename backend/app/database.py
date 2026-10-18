from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

from sqlalchemy.dialects import registry as _dialect_registry

_dialect_registry.register("sqlite.hrana", "app.sqlite_hrana", "SQLiteDialect_hrana")


def _create_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {"connect_args": {}}
    if url.startswith("sqlite+hrana://"):
        kwargs["connect_args"] = {
            "auth_token": settings.TURSO_AUTH_TOKEN,
            "secure": True,
        }
    return create_async_engine(url, echo=False, **kwargs)


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
        await conn.run_sync(_migrate_news_autoincrement)


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

    if "news" in tables:
        nexisting = {col["name"] for col in inspector.get_columns("news")}
        if "last_seen_at" not in nexisting:
            additions.append("ALTER TABLE news ADD COLUMN last_seen_at DATETIME")

    for stmt in additions:
        try:
            bind.execute(text(stmt))
        except Exception:
            pass


def _migrate_news_autoincrement(bind) -> None:
    """SQLite без AUTOINCREMENT переиспользует id после полной очистки таблицы
    news (новости снова получают id с 1, а колокольчик на сайте сравнивает их
    со старым seen_id) — пересоздаём таблицу с AUTOINCREMENT."""
    from sqlalchemy import inspect, text

    inspector = inspect(bind)
    if "news" not in inspector.get_table_names():
        return
    ddl = bind.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'news'")
    ).scalar()
    if not ddl or "AUTOINCREMENT" in ddl.upper():
        return
    stmts = [
        "DROP TABLE IF EXISTS news_new",
        """CREATE TABLE news_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            text VARCHAR,
            created_at DATETIME,
            last_seen_at DATETIME
        )""",
        """INSERT INTO news_new (id, text, created_at, last_seen_at)
            SELECT id, text, created_at, last_seen_at FROM news""",
        "DROP TABLE news",
        "ALTER TABLE news_new RENAME TO news",
    ]
    try:
        for stmt in stmts:
            bind.execute(text(stmt))
    except Exception:
        # DDL в SQLite транзакционен — откатываем, оставляем таблицу как была
        bind.rollback()
