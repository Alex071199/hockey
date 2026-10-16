"""MHL schedule source — parses https://mhl.khl.ru/calendar/ (Bitrix HTML).

Groups on the page: NOW (live), FUTURE (pre_game), ENDED (finished).
All site times are Moscow time (labels on mhl.khl.ru use "мск").
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://mhl.khl.ru"
CALENDAR_URL = f"{BASE_URL}/calendar/"
MSK = timezone(timedelta(hours=3))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": BASE_URL + "/",
}

_GROUP_STATUS = {"NOW": "live", "FUTURE": "pre_game", "ENDED": "finished"}

# mhl.khl.ru uses short labels that other sources spell in full
_TEAM_ALIASES = {
    "Спутник Ал": "Спутник Альметьевск",
    "АКМ-Юниор": "АКМ-Юниор Новомосковск",
}


def normalize_team(name: str | None) -> str:
    name = (name or "").strip()
    return _TEAM_ALIASES.get(name, name)

_MONTHS_RU = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
    "ноября": 11, "декабря": 12,
}

_PERIODS = {1: "1-й период", 2: "2-й период", 3: "3-й период",
            4: "Овертайм", 5: "Буллиты"}

_TOKEN_RE = re.compile(
    r'<div class="b_calendar_items_day_date ib">(?P<day>[^<]+)</div>'
    r'|<div class="(?P<item>b_calendar_item(?: [^"]*)?)">'
)

_GROUP_SPLIT_RE = re.compile(r'<div class="b_calendar_items_group[^"]*" data-group="(\w+)">')

_KICKOFF_DOT_RE = re.compile(
    r"game_info_bottom_info[^>]*>\s*(?:[А-Яа-я]{2},\s*)?"
    r"(?P<d>\d{1,2})\.(?P<mo>\d{1,2})\.(?P<y>\d{4}),\s*(?P<h>\d{1,2}):(?P<mi>\d{2})"
)

_KICKOFF_TEXT_RE = re.compile(
    r"(?P<d>\d{1,2})\s+(?P<mon>[а-я]{3,10})\s+(?P<y>\d{4}),\s*(?P<h>\d{1,2}):(?P<mi>\d{2})"
)


def _msk_to_utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MSK).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


async def _get(client: httpx.AsyncClient, url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            r = await client.get(url)
            if r.status_code == 200 and r.text:
                return r.text
            logger.warning("MHL: GET %s -> http=%s attempt=%d", url[:120], r.status_code, attempt + 1)
        except Exception as e:
            logger.warning("MHL: GET %s failed attempt=%d: %s", url[:120], attempt + 1, e)
        await asyncio.sleep(1.5 * (attempt + 1))
    return ""


def _fallback_tid(html: str) -> str | None:
    m = re.search(r'"TID":"(\d+)","ACTIVE":true', html)
    if m:
        return m.group(1)
    tids = re.findall(r"/game/(\d+)/\d+/", html)
    if tids:
        return max(set(tids), key=tids.count)
    return None


def _score(seg: str, side: str) -> int | None:
    m = re.search(rf"b_calendar_item_game_score-item-{side}\b[^>]*>(\d+)<", seg)
    return int(m.group(1)) if m else None


def _parse_item(seg: str, status: str, fallback_tid: str | None) -> dict | None:
    teams = re.findall(r'b_calendar_item_team_name">([^<]+)</div>', seg)
    if len(teams) < 2:
        return None
    home, away = normalize_team(teams[0]), normalize_team(teams[1])
    if not home or not away:
        return None

    dt: datetime | None = None
    mt = re.search(r'b_calendar_item_game_time">(\d{1,2}):(\d{2})<', seg)
    md = re.search(
        r'b_calendar_item_game_date">\s*[^,]*,\s*(\d{1,2})\.(\d{1,2})\.(\d{4})', seg
    )
    if mt and md:
        dt = _msk_to_utc(
            int(md.group(3)), int(md.group(2)), int(md.group(1)),
            int(mt.group(1)), int(mt.group(2)),
        )

    tid: str | None = None
    gid: str | None = None
    mg = re.search(r"/game/(\d+)/(\d+)/", seg)
    if mg:
        tid, gid = mg.group(1), mg.group(2)
    else:
        mtb = re.search(r"text\.mhl\.khl\.ru/(\d+)\.html", seg)
        if mtb:
            gid = mtb.group(1)
            tid = fallback_tid

    period: str | None = None
    if status == "live":
        if "b_calendar_item_game_ots" in seg:
            period = "Овертайм"
        else:
            mp = re.search(
                r"b_calendar_item_game_score_byperiod-now[^>]*>\s*<span>(\d+)</span>",
                seg,
            )
            if mp:
                period = _PERIODS.get(int(mp.group(1)))
            elif "iia-break_period" in seg:
                period = "Перерыв"

    return {
        "league": "MHL",
        "team_home": home,
        "team_away": away,
        "datetime_utc": dt,
        "status": status,
        "home_score": _score(seg, "h"),
        "away_score": _score(seg, "v"),
        "current_period": period,
        "mhl_game_id": gid,
        "mhl_tournament_id": tid,
    }


def _parse_group(body: str, group: str, fallback_tid: str | None) -> list[dict]:
    status = _GROUP_STATUS.get(group)
    if status is None:
        return []
    out: list[dict] = []
    tokens = list(_TOKEN_RE.finditer(body))
    for i, tok in enumerate(tokens):
        if tok.group("day"):
            continue
        end = tokens[i + 1].start() if i + 1 < len(tokens) else len(body)
        item = _parse_item(body[tok.start():end], status, fallback_tid)
        if item:
            out.append(item)
    return out


def _split_groups(html: str) -> dict[str, str]:
    parts = _GROUP_SPLIT_RE.split(html)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            out[parts[i]] = parts[i + 1]
    return out


async def _fetch_page(client: httpx.AsyncClient, page: int) -> str:
    # PAGEN_2 paginates the FUTURE list, PAGEN_3 paginates ENDED
    url = CALENDAR_URL if page == 1 else f"{CALENDAR_URL}?PAGEN_2={page}"
    html = await _get(client, url)
    if html and "b_calendar_item" not in html:
        logger.warning("MHL: page %d has no calendar items", page)
        return ""
    return html


async def scrape_mhl_matches(
    *, future_pages: int = 1, known_uids: set[str] | None = None
) -> list[dict]:
    """Return MHL matches parsed from mhl.khl.ru.

    Page 1 always carries NOW/FUTURE/ENDED (today ± ~10 days). Deeper
    FUTURE pages (``?PAGEN_2=N``) seed the schedule further ahead (~9 days
    per page). As a guard, every deeper page is accepted only when it
    brings games strictly later than everything seen so far; paging stops
    as soon as a page yields nothing new.
    """
    results: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
        html = await _fetch_page(client, 1)
        if not html:
            logger.warning("MHL: calendar unavailable")
            return []

        tid = _fallback_tid(html)
        for group, body in _split_groups(html).items():
            for item in _parse_group(body, group, tid):
                key = item.get("mhl_game_id") or f'{item["team_home"]}|{item["team_away"]}'
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)

        cutoff = max(
            (it["datetime_utc"] for it in results if it["datetime_utc"]),
            default=None,
        )

        for page in range(2, future_pages + 1):
            page_html = await _fetch_page(client, page)
            if not page_html:
                break
            fresh: list[dict] = []
            for item in _parse_group(page_html, "FUTURE", tid):
                dt = item.get("datetime_utc")
                gid = item.get("mhl_game_id")
                if not dt:
                    continue
                if gid and f"MHL_{gid}" in (known_uids or set()):
                    continue
                if gid and gid in seen:
                    continue
                if cutoff is not None and dt <= cutoff:
                    continue
                fresh.append(item)
            if not fresh:
                break
            for item in fresh:
                seen.add(item["mhl_game_id"])
                results.append(item)
                if item["datetime_utc"] > (cutoff or item["datetime_utc"]):
                    cutoff = item["datetime_utc"]

    logger.info("MHL: parsed %d matches from mhl.khl.ru", len(results))
    return results


def _parse_kickoff(html: str) -> datetime | None:
    m = _KICKOFF_DOT_RE.search(html)
    if m:
        try:
            return _msk_to_utc(
                int(m.group("y")), int(m.group("mo")), int(m.group("d")),
                int(m.group("h")), int(m.group("mi")),
            )
        except ValueError:
            pass
    m = _KICKOFF_TEXT_RE.search(html)
    if m:
        month = _MONTHS_RU.get(m.group("mon"))
        if month:
            try:
                return _msk_to_utc(
                    int(m.group("y")), month, int(m.group("d")),
                    int(m.group("h")), int(m.group("mi")),
                )
            except ValueError:
                pass
    return None


async def fetch_kickoff(match: dict) -> datetime | None:
    """Kickoff (UTC) for a live/finished match whose calendar item has no time.

    Tries the game page (preview/resume/summary) first, then the text
    broadcast page. Returns None when the time cannot be determined.
    """
    gid = match.get("mhl_game_id")
    if not gid:
        return None
    tid = match.get("mhl_tournament_id")

    urls: list[str] = []
    if tid:
        urls += [
            f"{BASE_URL}/game/{tid}/{gid}/preview/",
            f"{BASE_URL}/game/{tid}/{gid}/resume/",
            f"{BASE_URL}/game/{tid}/{gid}/summary/",
        ]
    urls.append(f"https://text.mhl.khl.ru/{gid}.html")

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
        for url in urls:
            html = await _get(client, url, retries=2)
            if not html:
                continue
            dt = _parse_kickoff(html)
            if dt:
                return dt
    return None
