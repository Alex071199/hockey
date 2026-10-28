import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    TURSO_DATABASE_URL: str = ""
    TURSO_AUTH_TOKEN: str = ""
    # Публичный адрес самого API — подставляется в stream_urls, которые
    # отдаём клиенту (иначе относительные ссылки на фронте не работают).
    PUBLIC_API_URL: str = ""
    # Хост с «чистым» IP для 1win (напр. Railway EU): если задан,
    # prime-ссылки (/stream.m3u8) ведут на него, а не на PUBLIC_API_URL.
    PRIME_PUBLIC_URL: str = ""
    # False — приложение работает только как API (без фоновых джоб):
    # ставится на Render, когда синк едет на отдельном хосте (Railway).
    SCHEDULER_ENABLED: bool = True
    ONHOCKEY_BASE_URL: str = "https://www.onhockey.tv/"
    SCRAPER_INTERVAL_MINUTES: int = 5
    SCRAPER_LIVE_INTERVAL_MINUTES: int = 5
    SCORE_UPDATE_INTERVAL_SECONDS: int = 30
    CACHE_TTL_SECONDS: int = 60
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://192.168.0.147:3001",
        "http://192.168.0.147:3000",
        "https://hockey-stream-two.vercel.app",
        "https://hockey-live.online",
        "https://www.hockey-live.online",
    ]
    HIGHLIGHTLY_API_KEY: str = ""
    HIGHLIGHTLY_API_KEYS: str = ""
    HIGHLIGHTLY_BASE_URL: str = "https://hockey.highlightly.net"
    HIGHLIGHTLY_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    KHL_HIGHLIGHTLY_LEAGUE_ID: int = 30569
    STANDINGS_TTL_SECONDS: int = 3600
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = "hockeylivenotificationbot"
    TELEGRAM_ADMIN_CHAT_ID: str = ""
    YOOMONEY_SECRET: str = ""
    YOOMONEY_WALLET: str = ""
    # Cloudflare Worker прокси (EU-регион) для обхода geo-блока 1win player
    PROXY_URL: str = ""
    # Пул обычных HTTP-прокси (через запятую, http://ip:port) для PRIME:
    # 1win режет IP дата-центров (Alwaysdata, Cloudflare) — «недоступно
    # в вашем регионе». Подпись HLS привязана к IP, поэтому для каждого
    # матча закрепляется ОДИН прокси на всю цепочку (плеер+плейлист+сегменты).
    PRIME_PROXIES: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()


def _squash_ws(value: str) -> str:
    return "".join((value or "").split())


settings.TURSO_AUTH_TOKEN = _squash_ws(settings.TURSO_AUTH_TOKEN)
settings.TURSO_DATABASE_URL = _squash_ws(settings.TURSO_DATABASE_URL)
settings.PROXY_URL = (settings.PROXY_URL or "").strip()
settings.PRIME_PROXIES = (settings.PRIME_PROXIES or "").strip()


def _resolve_database_url() -> str:
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    if settings.TURSO_DATABASE_URL:
        host = settings.TURSO_DATABASE_URL
        for prefix in ("libsql://", "https://", "http://"):
            if host.startswith(prefix):
                host = host[len(prefix):]
        host = host.rstrip("/")
        return f"sqlite+hrana://{host}"
    return "sqlite+aiosqlite:///./hockey.db"


settings.DATABASE_URL = _resolve_database_url()

if not settings.PUBLIC_API_URL:
    _render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if _render_url:
        settings.PUBLIC_API_URL = _render_url.rstrip("/")
    else:
        _domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        settings.PUBLIC_API_URL = (
            f"https://{_domain}" if _domain else "http://localhost:8001"
        )
