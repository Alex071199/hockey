"""KHL API start times for upcoming matches (72h window).

Used by the frontend to correct times of the static calendar: for games
starting within the next 72 hours the official API time wins.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app import khl_api
from app.scraper.team_names import canonical_team_name

router = APIRouter(prefix="/api", tags=["khl"])

MSK = timezone(timedelta(hours=3))

# API name variants that differ from the calendar/team_names spellings.
_API_ALIASES = {
    "драконы": "Шанхайские Драконы",
    "куньлунь": "Шанхайские Драконы",
    "куньлунь ред стар": "Шанхайские Драконы",
    "куньлунь рс": "Шанхайские Драконы",
    "куньлунь ред стар (пекин)": "Шанхайские Драконы",
}


def _calendar_name(raw: str) -> str:
    name = (raw or "").strip()
    alias = _API_ALIASES.get(name.lower())
    if alias:
        return alias
    return canonical_team_name(name)


@router.get("/khl/upcoming")
async def khl_upcoming(hours: int = 72):
    """Official KHL start times for matches starting within `hours` from now."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    lookback = now - timedelta(hours=12)

    out: list[dict] = []
    seen: set[tuple] = set()

    for i in range(4):
        date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            events = await khl_api.get_events_for_date(date_str)
        except Exception:
            continue

        for e in events:
            ts = e.get("start_at", 0)
            if isinstance(ts, (int, float)) and ts > 1e12:
                ts = ts // 1000
            if not ts:
                continue
            try:
                start = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                continue
            if not (lookback <= start <= cutoff):
                continue

            home = _calendar_name((e.get("team_a") or {}).get("name", ""))
            away = _calendar_name((e.get("team_b") or {}).get("name", ""))
            if not home or not away:
                continue

            local = start.astimezone(MSK)
            key = (home, away, local.strftime("%Y-%m-%d %H:%M"))
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "home": home,
                "away": away,
                "date": local.strftime("%Y-%m-%d"),
                "time": local.strftime("%H:%M"),
                "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

    out.sort(key=lambda m: m["start_utc"])
    return {"count": len(out), "matches": out}


@router.get("/khl/calendar")
async def khl_calendar():
    """Full-season KHL calendar from the official API.

    The season is paged through once in the background and cached for
    hours; while the first build is running `ready` is false and the
    frontend keeps retrying.
    """
    events = khl_api.cached_calendar_events()
    ready = events is not None
    if events is None:
        khl_api.start_calendar_build()
        events = khl_api.cached_calendar_events(max_age=10**12)

    out: list[dict] = []
    seen: set[tuple] = set()
    for e in events or []:
        ts = e.get("start_at", 0)
        if isinstance(ts, (int, float)) and ts > 1e12:
            ts = ts // 1000
        if not ts:
            continue
        try:
            start = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            continue
        home = _calendar_name((e.get("team_a") or {}).get("name", ""))
        away = _calendar_name((e.get("team_b") or {}).get("name", ""))
        if not home or not away:
            continue
        local = start.astimezone(MSK)
        key = (home, away, local.strftime("%Y-%m-%d %H:%M"))
        if key in seen:
            continue
        seen.add(key)
        score = khl_api._parse_score_str(e.get("score"))
        out.append({
            "id": e.get("id"),
            "date": local.strftime("%Y-%m-%d"),
            "time": local.strftime("%H:%M"),
            "home": home,
            "away": away,
            "status": e.get("game_state_key", ""),
            "score_home": score[0] if score else None,
            "score_away": score[1] if score else None,
            "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    out.sort(key=lambda m: m["start_utc"])
    return {"count": len(out), "matches": out, "ready": ready}
