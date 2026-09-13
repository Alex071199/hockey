"""Highlightly Hockey API client (live scores, standings).

Direct host is protected by Cloudflare bot checks, so requests must carry
a browser-like User-Agent. Responses are cached in memory with a TTL to
stay within the API quota, and persisted to disk so restarts don't re-burn it.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent / "hl_cache"


def _cache_path(name: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return _CACHE_DIR / f"{safe}.json"


def _persist(name: str, data: object) -> None:
    try:
        _cache_path(name).write_text(
            json.dumps({"saved": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Cache persist failed for %s: %s", name, e)


def _restore(name: str, ttl: int) -> object | None:
    """Return persisted payload if still within ttl, else None."""
    try:
        p = _CACHE_DIR / f"{''.join(c if c.isalnum() or c in '-_' else '_' for c in name)}.json"
        if not p.exists():
            return None
        payload = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - payload.get("saved", 0) > ttl:
            return None
        return payload.get("data")
    except Exception:
        return None

# league slug -> Highlightly league id
LEAGUE_IDS = {
    "KHL": settings.KHL_HIGHLIGHTLY_LEAGUE_ID,
}

# Highlightly (EN) -> наши названия (как в БД/календаре)
EN_RU_TEAMS = {
    "Lokomotiv Yaroslavl": "Локомотив",
    "Nizhny Novgorod": "Торпедо",
    "SKA St. Petersburg": "СКА",
    "Spartak Moscow": "Спартак",
    "Kunlun": "Шанхайские Драконы",
    "Cherepovets": "Северсталь",
    "CSKA Moscow": "ЦСКА",
    "Dynamo Moscow": "Динамо М",
    "Dinamo Minsk": "Динамо Мн",
    "Lada": "Лада",
    "Sochi": "ХК Сочи",
    "Bars Kazan": "Ак Барс",
    "Magnitogorsk": "Металлург Мг",
    "Nizhnekamsk": "Нефтехимик",
    "Barys Astana": "Барыс",
    "Salavat Ufa": "Салават Юлаев",
    "Vladivostok": "Адмирал",
    "Yekaterinburg": "Автомобилист",
    "Novosibirsk": "Сибирь",
    "Avangard Omsk": "Авангард",
    "Tractor Chelyabinsk": "Трактор",
    "Khabarovsk": "Амур",
}

FINISHED_STATES = {"Finished", "Finished after penalties", "Finished after over time"}
LIVE_STATES = {"1st period", "2nd period", "3rd period", "Over time", "Break time", "Penalties"}

_results_cache: dict[tuple[str, str], dict] = {}
RESULTS_TTL_TODAY_SECONDS = 3600
RESULTS_TTL_PAST_SECONDS = 7 * 24 * 3600

# Сырые матчи по датам (для results, коррекции времени и статистики матча)
_matches_cache: dict[tuple[str, str], dict] = {}
# Детали/форма/H2H/статистика команд: finished-данные почти не меняются
LONG_TTL_SECONDS = 7 * 24 * 3600
FORM_TTL_SECONDS = 6 * 3600
_details_cache: dict[int, dict] = {}
_lastfive_cache: dict[int, dict] = {}
_teamstats_cache: dict[tuple[int, int], dict] = {}
_h2h_cache: dict[tuple[int, int], dict] = {}

_cache: dict[str, dict] = {}

# Минимальный интервал между обращениями к API (дневная квота ~100 запросов на ключ)
MIN_REFRESH_INTERVAL_SECONDS = 1800

_key_index = 0


def _api_keys() -> list[str]:
    raw = (getattr(settings, "HIGHLIGHTLY_API_KEYS", "") or "").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys and (settings.HIGHLIGHTLY_API_KEY or "").strip():
        keys = [settings.HIGHLIGHTLY_API_KEY.strip()]
    return keys


def _current_season() -> int:
    """KHL season starts in September; season is named by its start year."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 9 else now.year - 1


def _points(row: dict) -> int:
    """KHL scoring: 2 pts for any win (incl. OT/SO), 1 pt for OT/SO loss."""
    return 2 * (row.get("wins", 0) + row.get("winsOvertime", 0)) + row.get("losesOvertime", 0)


def _normalize(payload: dict, league: str, season: int) -> dict:
    groups = []
    for group in payload.get("groups", []):
        rows = []
        for entry in group.get("standings", []):
            team = entry.get("team", {})
            gf = entry.get("scoredGoals", 0)
            ga = entry.get("receivedGoals", 0)
            wins = entry.get("wins", 0)
            otw = entry.get("winsOvertime", 0)
            otl = entry.get("losesOvertime", 0)
            rows.append(
                {
                    "position": entry.get("position", 0),
                    "team_id": team.get("id"),
                    "team_name": team.get("name", ""),
                    "logo": team.get("logo", ""),
                    "played": entry.get("gamesPlayed", 0),
                    "wins": wins,
                    "ot_wins": otw,
                    "ot_losses": otl,
                    "losses": entry.get("loses", 0),
                    "goals_for": gf,
                    "goals_against": ga,
                    "goal_diff": gf - ga,
                    "points": 2 * (wins + otw) + otl,
                }
            )
        # KHL tie-breakers (simplified): points -> total wins -> goal diff -> goals for
        rows.sort(key=lambda r: (r["points"], r["wins"] + r["ot_wins"], r["goal_diff"], r["goals_for"]), reverse=True)
        for i, r in enumerate(rows, start=1):
            r["position"] = i
        groups.append({"name": group.get("name", ""), "rows": rows})
    return {
        "league": league,
        "league_id": LEAGUE_IDS[league],
        "season": season,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": groups,
        "stale": False,
    }


async def _fetch_standings(league_id: int, season: int) -> dict:
    return await _hl_get("/standings", {"leagueId": league_id, "season": season})


async def refresh_standings(league: str = "KHL") -> dict:
    """Force-refresh standings from Highlightly (raises on failure)."""
    league = league.upper()
    if league not in LEAGUE_IDS:
        raise ValueError(f"Unsupported league: {league}")
    if not settings.HIGHLIGHTLY_API_KEY:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")

    season = _current_season()
    payload = await _fetch_standings(LEAGUE_IDS[league], season)
    groups = payload.get("groups", [])
    if not groups or all(not g.get("standings") for g in groups):
        logger.info("Standings empty for season %d, falling back to %d", season, season - 1)
        season -= 1
        payload = await _fetch_standings(LEAGUE_IDS[league], season)

    data = _normalize(payload, league, season)
    _cache[league] = {"at": time.monotonic(), "data": data}
    _persist(f"standings_{league}", data)
    logger.info("Standings refreshed: %s season %d", league, season)
    return data


async def refresh_standings_if_due(league: str = "KHL", min_interval: int = MIN_REFRESH_INTERVAL_SECONDS) -> dict | None:
    """Refresh only if the last successful refresh is older than min_interval.

    Returns fresh data, or None when skipped (quota guard).
    """
    cached = _cache.get(league.upper())
    if cached and time.monotonic() - cached["at"] < min_interval:
        return None
    return await refresh_standings(league)


async def get_standings(league: str = "KHL") -> dict:
    """Return cached standings, refreshing when stale.

    Serves stale cache if the upstream refresh fails.
    """
    league = league.upper()
    cached = _cache.get(league)
    if cached and time.monotonic() - cached["at"] < settings.STANDINGS_TTL_SECONDS:
        return cached["data"]
    restored = _restore(f"standings_{league}", settings.STANDINGS_TTL_SECONDS)
    if restored is not None:
        _cache[league] = {"at": time.monotonic(), "data": restored}
        return restored
    try:
        return await refresh_standings(league)
    except Exception as e:
        if cached:
            logger.warning("Standings refresh failed, serving stale cache: %s", e)
            data = dict(cached["data"])
            data["stale"] = True
            return data
        raise


def _parse_score(current: str) -> tuple[int | None, int | None]:
    """'4 - 4' (home first) -> (4, 4)."""
    try:
        left, right = current.split("-", 1)
        return int(left.strip()), int(right.strip())
    except (ValueError, AttributeError):
        return None, None


def _normalize_match(m: dict) -> dict:
    home_en = (m.get("homeTeam") or {}).get("name", "")
    away_en = (m.get("awayTeam") or {}).get("name", "")
    state = m.get("state") or {}
    score = state.get("score") or {}
    sh, sa = _parse_score(score.get("current", ""))
    description = state.get("description", "")
    # reg — основное время, ot — овертайм, so — буллиты
    if description == "Finished after penalties" or score.get("penalties"):
        finish = "so"
    elif description == "Finished after over time" or score.get("overTime"):
        finish = "ot"
    else:
        finish = "reg"
    return {
        "id": m.get("id"),
        "date": m.get("date"),
        "home": EN_RU_TEAMS.get(home_en, home_en),
        "away": EN_RU_TEAMS.get(away_en, away_en),
        "status": description,
        "finished": description in FINISHED_STATES,
        "score_home": sh,
        "score_away": sa,
        "finish": finish,
    }


async def _fetch_matches(league: str, date_str: str) -> list[dict]:
    data = await _hl_get(
        "/matches",
        {
            "leagueName": league,
            "date": date_str,
            "timezone": "Europe/Moscow",
            "limit": 100,
        },
    )
    return data.get("data", []) if isinstance(data, dict) else []


def _parse_hl_datetime(v: str) -> datetime | None:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError, TypeError):
        return None


async def _correct_db_times(league: str, matches: list[dict]) -> int:
    """Heal our schedule with Highlightly timestamps (best effort).

    livetv sometimes lists wrong kickoff times; Highlightly is authoritative.
    Only touches rows matched by team pair. Transitions are conservative:
    finished always applied, pre_game -> live applied, never downgrades.
    Returns number of rows changed.
    """
    from sqlalchemy import or_, select

    from app.models import Match

    changed = 0
    try:
        async with async_session() as db:
            for m in matches:
                r = _normalize_match(m)
                dt = _parse_hl_datetime(m.get("date", ""))
                if dt is None or not r["home"] or not r["away"]:
                    continue
                q = await db.execute(
                    select(Match).where(
                        Match.league == league,
                        or_(
                            (Match.team_home == r["home"]) & (Match.team_away == r["away"]),
                            (Match.team_home == r["away"]) & (Match.team_away == r["home"]),
                        ),
                    )
                )
                for row in q.scalars().all():
                    if row.datetime_utc is None or abs((row.datetime_utc - dt).total_seconds()) >= 120:
                        row.datetime_utc = dt
                        changed += 1
                    if r["finished"] and row.status != "finished":
                        row.status = "finished"
                        changed += 1
                    elif not r["finished"] and (m.get("state") or {}).get("description") in LIVE_STATES and row.status == "pre_game":
                        row.status = "live"
                        changed += 1
            if changed:
                await db.commit()
    except Exception as e:
        logger.warning("DB time correction failed: %s", e)
        return 0
    if changed:
        logger.info("Corrected %d schedule rows from Highlightly", changed)
    return changed


def _results_ttl(date_str: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    if date_str == today:
        return RESULTS_TTL_TODAY_SECONDS
    if date_str < today:
        return RESULTS_TTL_PAST_SECONDS
    return 0  # future dates: nothing finished, don't cache empty upstream miss


def invalidate_results(league: str = "KHL", date_str: str | None = None) -> None:
    """Drop cached results so the next request refetches (e.g. after a finish)."""
    league = league.upper()
    if date_str is None:
        date_str = datetime.now(timezone.utc).date().isoformat()
    _results_cache.pop((league, date_str), None)


async def _get_matches(league: str, date_str: str) -> list[dict]:
    """Raw Highlightly matches for a date, cached (TTL like results)."""
    key = (league.upper(), date_str)
    cached = _matches_cache.get(key)
    if cached and time.monotonic() - cached["at"] < _results_ttl(date_str):
        return cached["data"]
    restored = _restore(f"matches_{league.upper()}_{date_str}", _results_ttl(date_str))
    if restored is not None:
        _matches_cache[key] = {"at": time.monotonic(), "data": restored}
        return restored
    if not settings.HIGHLIGHTLY_API_KEY:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")
    data = await _fetch_matches(league.upper(), date_str)
    if _results_ttl(date_str) > 0:
        _matches_cache[key] = {"at": time.monotonic(), "data": data}
        _persist(f"matches_{league.upper()}_{date_str}", data)
    return data


async def refresh_results(league: str = "KHL", date_str: str | None = None) -> dict:
    league = league.upper()
    if league not in LEAGUE_IDS:
        raise ValueError(f"Unsupported league: {league}")
    if not settings.HIGHLIGHTLY_API_KEY:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")
    if date_str is None:
        date_str = datetime.now(timezone.utc).date().isoformat()

    matches = await _get_matches(league, date_str)
    await _correct_db_times(league, matches)
    results = [r for r in (_normalize_match(m) for m in matches) if r["finished"] and r["score_home"] is not None]
    data = {
        "league": league,
        "date": date_str,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
        "stale": False,
    }
    if _results_ttl(date_str) > 0:
        _results_cache[(league, date_str)] = {"at": time.monotonic(), "data": data}
        _persist(f"results_{league}_{date_str}", data)
    return data


async def get_results(league: str = "KHL", date_str: str | None = None) -> dict:
    league = league.upper()
    if date_str is None:
        date_str = datetime.now(timezone.utc).date().isoformat()
    cached = _results_cache.get((league, date_str))
    if cached and time.monotonic() - cached["at"] < _results_ttl(date_str):
        return cached["data"]
    restored = _restore(f"results_{league}_{date_str}", _results_ttl(date_str))
    if restored is not None:
        _results_cache[(league, date_str)] = {"at": time.monotonic(), "data": restored}
        return restored
    try:
        return await refresh_results(league, date_str)
    except Exception as e:
        if cached:
            logger.warning("Results refresh failed, serving stale cache: %s", e)
            data = dict(cached["data"])
            data["stale"] = True
            return data
        raise


def _ru_names(m: dict) -> tuple[str, str]:
    home_en = (m.get("homeTeam") or {}).get("name", "")
    away_en = (m.get("awayTeam") or {}).get("name", "")
    return EN_RU_TEAMS.get(home_en, home_en), EN_RU_TEAMS.get(away_en, away_en)


def _find_pair(matches: list[dict], home_ru: str, away_ru: str) -> dict | None:
    want = {home_ru.strip().lower(), away_ru.strip().lower()}
    for m in matches:
        h, a = _ru_names(m)
        if {h.strip().lower(), a.strip().lower()} == want:
            return m
    return None


async def _hl_get(path: str, params: dict) -> object:
    """GET with API-key rotation: on 429 tries the next key (round-robin)."""
    global _key_index
    keys = _api_keys()
    if not keys:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")
    last_err: Exception | None = None
    for i in range(len(keys)):
        idx = (_key_index + i) % len(keys)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{settings.HIGHLIGHTLY_BASE_URL}{path}",
                    params=params,
                    headers={
                        "x-rapidapi-key": keys[idx],
                        "User-Agent": settings.HIGHLIGHTLY_USER_AGENT,
                        "Accept": "application/json",
                    },
                )
            if resp.status_code == 429:
                last_err = httpx.HTTPStatusError(
                    "quota exhausted", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            _key_index = (idx + 1) % len(keys)
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                last_err = e
                continue
            raise
    raise RuntimeError(
        f"Highlightly daily quota exhausted on all {len(keys)} key(s)"
    ) from last_err


async def get_match_details(hl_id: int) -> dict:
    cached = _details_cache.get(hl_id)
    if cached and time.monotonic() - cached["at"] < LONG_TTL_SECONDS:
        return cached["data"]
    restored = _restore(f"details_{hl_id}", LONG_TTL_SECONDS)
    if restored is not None:
        _details_cache[hl_id] = {"at": time.monotonic(), "data": restored}
        return restored
    data = await _hl_get(f"/matches/{hl_id}", {})
    match = (data if isinstance(data, list) else [data])[0] if data else {}
    if not match:
        raise LookupError(f"Match {hl_id} not found")
    _details_cache[hl_id] = {"at": time.monotonic(), "data": match}
    _persist(f"details_{hl_id}", match)
    return match


async def get_last_five(team_id: int) -> list[dict]:
    cached = _lastfive_cache.get(team_id)
    if cached and time.monotonic() - cached["at"] < FORM_TTL_SECONDS:
        return cached["data"]
    restored = _restore(f"lastfive_{team_id}", FORM_TTL_SECONDS)
    if restored is not None:
        _lastfive_cache[team_id] = {"at": time.monotonic(), "data": restored}
        return restored
    data = await _hl_get("/last-five-games", {"teamId": team_id})
    norm = [_normalize_match(m) for m in (data if isinstance(data, list) else [])]
    _lastfive_cache[team_id] = {"at": time.monotonic(), "data": norm}
    _persist(f"lastfive_{team_id}", norm)
    return norm


async def get_team_season_stats(team_id: int, season: int) -> list[dict]:
    key = (team_id, season)
    cached = _teamstats_cache.get(key)
    if cached and time.monotonic() - cached["at"] < FORM_TTL_SECONDS:
        return cached["data"]
    restored = _restore(f"teamstats_{team_id}_{season}", FORM_TTL_SECONDS)
    if restored is not None:
        _teamstats_cache[key] = {"at": time.monotonic(), "data": restored}
        return restored
    data = await _hl_get(
        f"/teams/statistics/{team_id}",
        {"fromDate": f"{season}-08-01", "timezone": "Europe/Moscow"},
    )
    stats = data if isinstance(data, list) else []
    _teamstats_cache[key] = {"at": time.monotonic(), "data": stats}
    _persist(f"teamstats_{team_id}_{season}", stats)
    return stats


async def get_h2h(team_id_one: int, team_id_two: int) -> list[dict]:
    key = tuple(sorted((team_id_one, team_id_two)))
    cached = _h2h_cache.get(key)
    if cached and time.monotonic() - cached["at"] < FORM_TTL_SECONDS:
        return cached["data"]
    restored = _restore(f"h2h_{key[0]}_{key[1]}", FORM_TTL_SECONDS)
    if restored is not None:
        _h2h_cache[key] = {"at": time.monotonic(), "data": restored}
        return restored
    data = await _hl_get("/head-2-head", {"teamIdOne": team_id_one, "teamIdTwo": team_id_two})
    norm = [_normalize_match(m) for m in (data if isinstance(data, list) else [])]
    _h2h_cache[key] = {"at": time.monotonic(), "data": norm}
    _persist(f"h2h_{key[0]}_{key[1]}", norm)
    return norm


async def get_match_stats(league: str, date_str: str, home_ru: str, away_ru: str) -> dict:
    """Aggregate stats for one finished match: details, form, H2H, season stats."""
    import asyncio

    league = league.upper()
    if league not in LEAGUE_IDS:
        raise ValueError(f"Unsupported league: {league}")
    if not settings.HIGHLIGHTLY_API_KEY:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")

    matches = await _get_matches(league, date_str)
    raw = _find_pair(matches, home_ru, away_ru)
    if raw is None:
        raise LookupError(f"Match {home_ru} - {away_ru} not found on {date_str}")

    hl_id = raw.get("id")
    home_id = (raw.get("homeTeam") or {}).get("id")
    away_id = (raw.get("awayTeam") or {}).get("id")
    if not hl_id or not home_id or not away_id:
        raise LookupError("Match teams unresolved")

    season = _current_season()

    async def _best_effort(name: str, coro):
        try:
            return await coro
        except Exception as e:
            logger.warning("Match stats section '%s' failed: %s", name, e)
            return None

    details, home_form, away_form, h2h, home_stats, away_stats = await asyncio.gather(
        _best_effort("details", get_match_details(hl_id)),
        _best_effort("form_home", get_last_five(home_id)),
        _best_effort("form_away", get_last_five(away_id)),
        _best_effort("h2h", get_h2h(home_id, away_id)),
        _best_effort("season_home", get_team_season_stats(home_id, season)),
        _best_effort("season_away", get_team_season_stats(away_id, season)),
    )
    partial = [
        name
        for name, value in (
            ("details", details),
            ("form", home_form if home_form is not None and away_form is not None else None),
            ("h2h", h2h),
            ("season", home_stats if home_stats is not None and away_stats is not None else None),
        )
        if value is None
    ]

    norm = _normalize_match(raw)
    # Периоды: из деталей, иначе из списка матчей (там тоже полный score)
    score = ((details or {}).get("state") or {}).get("score") or ((raw.get("state") or {}).get("score")) or {}
    return {
        "league": league,
        "partial": partial,
        "match": norm,
        "periods": {
            "first": score.get("firstPeriod"),
            "second": score.get("secondPeriod"),
            "third": score.get("thirdPeriod"),
            "overtime": score.get("overTime"),
            "penalties": score.get("penalties"),
        },
        "venue": (details or {}).get("venue"),
        "predictions": ((details or {}).get("predictions") or {}).get("prematch", []),
        "form": {"home": home_form or [], "away": away_form or []},
        "h2h": h2h or [],
        "season_stats": {"home": home_stats or [], "away": away_stats or []},
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
