"""KHL API client (khl.api.webcaster.pro) — standings, events, stats."""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://khl.api.webcaster.pro/api/khl_mobile"
TEAMS_URL = f"{BASE_URL}/teams"
EVENTS_V2_URL = f"{BASE_URL}/events_v2.json"
EVENT_V2_URL = f"{BASE_URL}/event_v2.json"

_cache: dict[str, dict] = {}
STANDINGS_TTL = 300
EVENTS_TTL = 1800
# При live-обновлениях счёта события нельзя кэшировать надолго —
# иначе период/статус матча отстаёт на десятки минут.
EVENTS_LIVE_TTL = 60
# Полный сезонный календарь собирается один раз и живёт долго.
CALENDAR_TTL = 6 * 3600

_calendar_task: asyncio.Task | None = None
_last_build_attempt: float = 0.0


async def _get_json(url: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _current_stage_id() -> int:
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 9 else now.year - 1
    season_map = {2026: 407, 2025: 389, 2024: 371, 2023: 353, 2022: 335}
    return season_map.get(year, 407)


def _normalize_conference(raw: str) -> str:
    if "Запад" in raw:
        return "Western Conference"
    if "Восток" in raw:
        return "Eastern Conference"
    return raw


async def get_standings() -> dict:
    cache_key = "standings_khl"
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached["at"] < STANDINGS_TTL:
        return cached["data"]

    raw_teams = await _get_json(TEAMS_URL)
    teams = [item.get("team", item) for item in raw_teams]

    conf_teams: dict[str, list] = {}
    for t in teams:
        conf = _normalize_conference(t.get("conference", ""))
        conf_teams.setdefault(conf, []).append(t)

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    season = time.gmtime().tm_year if time.gmtime().tm_mon >= 9 else time.gmtime().tm_year - 1

    groups = []
    for conf_name in ["Western Conference", "Eastern Conference"]:
        rows = []
        for t in conf_teams.get(conf_name, []):
            gp = int(t.get("gp", 0) or 0)
            w = int(t.get("w", 0) or 0)
            otw = int(t.get("otw", 0) or 0)
            sow = int(t.get("sow", 0) or 0)
            sol = int(t.get("sol", 0) or 0)
            otl = int(t.get("otl", 0) or 0)
            l = int(t.get("l", 0) or 0)
            gf = int(t.get("gf", 0) or 0)
            ga = int(t.get("ga", 0) or 0)
            pts = int(t.get("pts", 0) or 0)
            rows.append({
                "position": 0,
                "team_id": t.get("id"),
                "team_name": t.get("name", ""),
                "logo": t.get("image", ""),
                "played": gp,
                "wins": w + otw + sow,
                "ot_wins": otw + sow,
                "ot_losses": otl + sol,
                "losses": l,
                "goals_for": gf,
                "goals_against": ga,
                "goal_diff": gf - ga,
                "points": pts,
                "_w": w,
                "_otw": otw,
                "_sow": sow,
            })
        # Правила классификации КХЛ: очки → победы в основное время →
        # победы в овертайме → победы по буллитам → разница шайб → забитые шайбы
        rows.sort(
            key=lambda r: (r["points"], r["_w"], r["_otw"], r["_sow"], r["goal_diff"], r["goals_for"]),
            reverse=True,
        )
        for r in rows:
            r.pop("_w", None)
            r.pop("_otw", None)
            r.pop("_sow", None)
        for i, r in enumerate(rows, 1):
            r["position"] = i
        groups.append({"name": conf_name, "rows": rows})

    data = {"league": "KHL", "season": season, "updated_at": now_iso, "groups": groups, "stale": False}
    _cache[cache_key] = {"at": time.monotonic(), "data": data}
    return data


async def _fetch_events_page(params: dict) -> list[dict]:
    raw = await _get_json(EVENTS_V2_URL, params)
    return [item.get("event", item) for item in (raw if isinstance(raw, list) else [])]


async def get_events_for_date(date_str: str, max_age: float = EVENTS_TTL) -> list[dict]:
    """Get all events for a given date (YYYY-MM-DD)."""
    cache_key = f"events_{date_str}"
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached["at"] < max_age:
        return cached["data"]

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return []

    start_ts = int(target.timestamp())
    end_ts = start_ts + 86400
    stage_id = _current_stage_id()

    all_events = []
    past_range = False
    for page in range(1, 50):
        params = {
            "stage_id": stage_id,
            "order_direction": "asc",
            "page": str(page),
        }
        try:
            events = await _fetch_events_page(params)
        except Exception as e:
            logger.warning("events_v2 page %d failed: %s", page, e)
            break
        if not events:
            break

        found_before = False
        found_after = False
        found_today = False
        for e in events:
            sa = e.get("start_at", 0)
            if isinstance(sa, (int, float)) and sa > 1e12:
                sa = sa // 1000
            if start_ts <= sa < end_ts:
                all_events.append(e)
                found_today = True
            elif sa < start_ts:
                found_before = True
            elif sa >= end_ts:
                found_after = True

        if found_after:
            break
        if found_today and not found_before and page >= 3:
            break

    _cache[cache_key] = {"at": time.monotonic(), "data": all_events}
    return all_events


def cached_calendar_events(max_age: float = CALENDAR_TTL) -> list[dict] | None:
    """Full-season events if the cache is younger than `max_age`, else None."""
    cached = _cache.get("all_events")
    if cached and time.monotonic() - cached["at"] < max_age:
        return cached["data"]
    return None


def start_calendar_build() -> bool:
    """Start a background full-season fetch. Returns True if a build started."""
    global _calendar_task, _last_build_attempt
    if _calendar_task is not None and not _calendar_task.done():
        return False
    now = time.monotonic()
    if now - _last_build_attempt < 120:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _last_build_attempt = now
    _calendar_task = loop.create_task(_build_calendar())
    return True


async def _build_calendar() -> None:
    """Page through the whole stage once and cache every event (≈2.5 min)."""
    stage_id = _current_stage_id()
    all_events: list[dict] = []
    complete = False
    for page in range(1, 70):
        events = None
        for attempt in range(4):
            try:
                events = await _fetch_events_page(
                    {"stage_id": stage_id, "order_direction": "asc", "page": str(page)}
                )
                break
            except Exception as e:
                logger.warning(
                    "calendar page %d attempt %d failed: %s", page, attempt + 1, e
                )
                await asyncio.sleep(2 * (attempt + 1))
        if events is None:
            break
        if not events:
            complete = True
            break
        all_events.extend(events)
    if complete and all_events:
        _cache["all_events"] = {"at": time.monotonic(), "data": all_events}
        logger.info("KHL calendar: cached %d events", len(all_events))
    else:
        logger.warning("KHL calendar: build incomplete (%d events)", len(all_events))


def _find_event(events: list[dict], home: str, away: str) -> dict | None:
    """Find event matching team names (case-insensitive, flexible order)."""
    want = {home.strip().lower(), away.strip().lower()}
    for e in events:
        ta = (e.get("team_a") or {}).get("name", "").strip().lower()
        tb = (e.get("team_b") or {}).get("name", "").strip().lower()
        if {ta, tb} == want:
            return e
    for e in events:
        ta = (e.get("team_a") or {}).get("name", "").strip().lower()
        tb = (e.get("team_b") or {}).get("name", "").strip().lower()
        h = home.strip().lower()
        a = away.strip().lower()
        if (h in ta or ta in h) and (a in tb or tb in a):
            return e
    return None


async def get_event_detail(event_id: int, max_age: float = 300) -> dict:
    """Get full event details from event_v2."""
    cache_key = f"event_detail_{event_id}"
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached["at"] < max_age:
        return cached["data"]

    raw = await _get_json(EVENT_V2_URL, {"id": event_id})
    data = raw.get("event", raw) if isinstance(raw, dict) else raw
    _cache[cache_key] = {"at": time.monotonic(), "data": data}
    return data


def _parse_score_str(s: str | None) -> tuple[int, int] | None:
    if not s:
        return None
    try:
        parts = s.split(":")
        return int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, IndexError):
        return None


def _determine_finish(event: dict) -> str:
    """Determine finish type: reg, ot, so."""
    scores = event.get("scores", {})
    if scores.get("bullitt"):
        return "so"
    if scores.get("overtime"):
        return "ot"
    return "reg"


def _format_period_scores(event: dict) -> dict:
    """Format period scores for frontend."""
    scores = event.get("scores", {})
    return {
        "first": scores.get("first_period"),
        "second": scores.get("second_period"),
        "third": scores.get("third_period"),
        "overtime": scores.get("overtime"),
        "penalties": scores.get("bullitt"),
    }


async def get_results(date_str: str) -> dict:
    """Get results for a date — replaces highlightly.get_results."""
    events = await get_events_for_date(date_str)
    results = []
    for e in events:
        if e.get("game_state_key") != "finished":
            continue
        score = _parse_score_str(e.get("score"))
        if not score:
            continue
        home = (e.get("team_a") or {}).get("name", "")
        away = (e.get("team_b") or {}).get("name", "")
        ts = e.get("start_at", 0)
        if ts > 1e12:
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append({
            "id": e.get("id"),
            "khl_event_id": e.get("id"),
            "date": dt,
            "home": home,
            "away": away,
            "status": "Finished",
            "finished": True,
            "score_home": score[0],
            "score_away": score[1],
            "finish": _determine_finish(e),
        })
    return {
        "league": "KHL",
        "date": date_str,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
        "stale": False,
    }


async def get_match_stats(home: str, away: str, date_str: str, live: bool = False) -> dict:
    """Get match statistics — fast: only 2 API calls (events list + event detail)."""
    events = await get_events_for_date(date_str)
    event = _find_event(events, home, away)
    if not event:
        raise LookupError(f"Match {home} - {away} not found on {date_str}")
    return await _build_match_stats(event["id"], max_age=15 if live else 300)


async def get_match_stats_by_id(event_id: int, live: bool = False) -> dict:
    """Get match statistics by KHL event ID — 1 API call."""
    return await _build_match_stats(event_id, max_age=15 if live else 300)


async def _build_match_stats(event_id: int, max_age: float = 300) -> dict:
    detail = await get_event_detail(event_id, max_age=max_age)

    home_name = (detail.get("team_a") or {}).get("name", "")
    away_name = (detail.get("team_b") or {}).get("name", "")
    score = _parse_score_str(detail.get("score"))
    sh = score[0] if score else 0
    sa = score[1] if score else 0

    period_scores = _format_period_scores(detail)
    finish = _determine_finish(detail)

    goals = detail.get("goals", [])
    violations = detail.get("violations", [])
    team_a = detail.get("team_a", {})
    team_b = detail.get("team_b", {})

    # Индекс игрок -> команда: у часть нарушений violator приходит без team,
    # и штраф уезжал в чужую колонку home/away. Составы есть в тех же данных.
    _player_team: dict[int, int] = {}
    for _t, _tid in ((team_a, team_a.get("id", 0)), (team_b, team_b.get("id", 0))):
        if not _tid:
            continue
        for _p in _t.get("players") or []:
            _pid = _p.get("id")
            if _pid:
                _player_team[int(_pid)] = int(_tid)

    def _person_team_id(person: dict) -> int:
        tid = ((person.get("team") or {}).get("id")) or person.get("team_id") or 0
        if tid:
            return int(tid)
        pid = person.get("id")
        if pid:
            tid = _player_team.get(int(pid), 0)
            if tid:
                return tid
        return 0

    def _team_stats(t: dict) -> dict:
        return {
            "shots": t.get("shots", 0) or 0,
            "goals_for": t.get("gf", 0) or 0,
            "ppg": t.get("ppg", 0) or 0,
            "shg": t.get("shg", 0) or 0,
            "ppc": t.get("ppc", 0) or 0,
            "faceoffs_won": t.get("vbr", 0) or 0,
            "pim": t.get("pim", 0) or 0,
            "puck_control_pct": round(t.get("total_puck_control_time", 0) or 0, 1),
            "distance_km": round(t.get("total_distance_travelled", 0) or 0, 1),
            "zone_entries": t.get("offensive_blue_line_crossings_count", 0) or 0,
        }

    def _goals_list() -> list[dict]:
        result = []
        for g in goals:
            author = g.get("author") or {}
            result.append({
                "time": g.get("time_s") or _seconds_to_time(g.get("time", 0)),
                "score": g.get("score", ""),
                "period": g.get("period", 0),
                "team_id": int(author.get("team_id") or 0) or _person_team_id(author),
                "scorer": author.get("name", ""),
                "assistants": [
                    a.get("name", "") for a in g.get("assistants", [])
                ],
            })
        return result

    def _penalties_list() -> list[dict]:
        result = []
        for v in violations:
            violator = v.get("violator") or {}
            team_id = _person_team_id(violator) or _person_team_id(v)
            result.append({
                "time": v.get("time_s") or _seconds_to_time(v.get("time", 0)),
                "period": v.get("period", 0),
                "reason": v.get("penalty_reason", ""),
                "minutes": v.get("penalty_time", 0),
                "player": violator.get("name", ""),
                "team_id": team_id,
            })
        return result

    def _roster(t: dict) -> list[dict]:
        out = []
        for p in t.get("players") or []:
            goals = 0
            for s in p.get("match_stats") or []:
                if s.get("id") == "goals":
                    try:
                        goals = int(s.get("val") or 0)
                    except (TypeError, ValueError):
                        goals = 0
                    break
            out.append({
                "number": p.get("shirt_number"),
                "name": p.get("name", ""),
                "role": p.get("role_key") or "",
                "image": p.get("image"),
                "goals": goals,
            })
        return out

    hl = detail.get("highlight") or {}

    return {
        "league": "KHL",
        "event_id": event_id,
        "match": {
            "home": home_name,
            "away": away_name,
            "home_team_id": team_a.get("id", 0),
            "away_team_id": team_b.get("id", 0),
            "status": "Live" if detail.get("game_state_key") == "in_progress" else "Finished",
            "score_home": sh,
            "score_away": sa,
            "finish": finish,
        },
        "periods": period_scores,
        "team_stats": {
            "home": _team_stats(team_a),
            "away": _team_stats(team_b),
        },
        "goals": _goals_list(),
        "penalties": _penalties_list(),
        "rosters": {
            "home": _roster(team_a),
            "away": _roster(team_b),
        },
        # «Обзор матча» с KHL video — появляется с задержкой после финала,
        # m3u8 подписан и протухает, поэтому фронт запрашивает на лету
        "highlight": (
            {
                "m3u8_url": hl.get("m3u8_url"),
                "name": (hl.get("name") or "").strip(),
            }
            if hl.get("m3u8_url")
            else None
        ),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _seconds_to_time(secs: int) -> str:
    m = (secs or 0) // 60
    s = (secs or 0) % 60
    return f"{m}:{s:02d}"


async def get_live_scores() -> list[dict]:
    """Get currently live/just finished events for score updates."""
    stage_id = _current_stage_id()
    now = int(time.time())
    today_start = now - (now % 86400)

    live = []
    past_yesterday = False
    for page in range(1, 50):
        if past_yesterday:
            break
        params = {
            "stage_id": stage_id,
            "order_direction": "asc",
            "page": str(page),
        }
        try:
            events = await _fetch_events_page(params)
        except Exception as e:
            logger.warning("get_live_scores page %d failed: %s", page, e)
            continue
        if not events:
            break

        last_ts = 0
        for e in events:
            ts = e.get("start_at", 0)
            if ts > 1e12:
                ts = ts // 1000
            last_ts = ts
            state = e.get("game_state_key", "")
            if state not in ("live", "finished", "in_progress"):
                continue
            if state == "finished" and (now - ts) > 14400:
                continue
            if state in ("live", "in_progress") or (state == "finished" and ts >= today_start - 86400):
                score = _parse_score_str(e.get("score"))
                live.append({
                    "event_id": e.get("id"),
                    "khl_id": e.get("khl_id"),
                    "name": e.get("name", ""),
                    "home": (e.get("team_a") or {}).get("name", ""),
                    "away": (e.get("team_b") or {}).get("name", ""),
                    "score": e.get("score"),
                    "score_home": score[0] if score else None,
                    "score_away": score[1] if score else None,
                    "game_state": state,
                    "period": e.get("period"),
                    "scores": e.get("scores", {}),
                })

        if last_ts > today_start + 86400:
            past_yesterday = True

    return live
