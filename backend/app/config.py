from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./hockey.db"
    ONHOCKEY_BASE_URL: str = "https://www.onhockey.tv/"
    SCRAPER_INTERVAL_MINUTES: int = 5
    SCRAPER_LIVE_INTERVAL_MINUTES: int = 5
    SCORE_UPDATE_INTERVAL_SECONDS: int = 30
    CACHE_TTL_SECONDS: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://192.168.0.147:3001", "http://192.168.0.147:3000"]
    HIGHLIGHTLY_API_KEY: str = ""
    HIGHLIGHTLY_API_KEYS: str = ""
    HIGHLIGHTLY_BASE_URL: str = "https://hockey.highlightly.net"
    HIGHLIGHTLY_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    KHL_HIGHLIGHTLY_LEAGUE_ID: int = 30569
    STANDINGS_TTL_SECONDS: int = 3600

    model_config = {"env_file": ".env"}


settings = Settings()
