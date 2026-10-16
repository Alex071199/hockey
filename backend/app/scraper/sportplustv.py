import asyncio
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from app.scraper.team_names import canonical_team_name

logger = logging.getLogger(__name__)

CURL = shutil.which("curl") or "curl"
SPORTPLUSTV_HOCKEY = "https://ru.sportplustv.live/hockey/"
SPORTPLUSTV_MATCH_API = "https://api.sportplustv.live/v5/matches/view"

VHL_TOURNAMENT_ID = 101763
# МХЛ больше не берём: трансляции МХЛ идут через livetv.
TARGET_TOURNAMENTS = {VHL_TOURNAMENT_ID}

TOURNAMENT_ID_TO_LEAGUE = {
    VHL_TOURNAMENT_ID: "VHL",
}

MSK = timezone(timedelta(hours=3))


def _curl_get_sync(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L", "-w", "\n%{http_code}",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "-H", "Referer: https://ru.sportplustv.live/",
                "--connect-timeout", "15",
                "--max-time", "30",
                url,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=35)
            if r.stdout:
                out = r.stdout.decode("utf-8", errors="ignore")
                body, _, code = out.rpartition("\n")
                if body and len(body) > 100:
                    return body
                logger.warning(
                    "SportPlusTV: GET %s -> http=%s len=%d attempt=%d",
                    url[:120], code.strip(), len(body), attempt + 1,
                )
        except Exception as e:
            logger.warning("SportPlusTV: GET %s failed: %s", url[:120], e)
    return ""


async def _curl_get(url: str, retries: int = 3) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _curl_get_sync, url, retries)


def _extract_ng_state(html: str) -> dict | None:
    m = re.search(
        r'<script\s+id="ng-state"\s+type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_score_array(
    score_list: list[dict] | None, home_pk: int, away_pk: int
) -> tuple[int | None, int | None]:
    if not score_list:
        return None, None
    home_total = 0
    away_total = 0
    for period_score in score_list:
        if period_score.get("p", 0) == 0:
            continue
        home_total += int(period_score.get(str(home_pk), 0))
        away_total += int(period_score.get(str(away_pk), 0))
    return home_total, away_total


def _status_from_sportplustv(sp_status: str, match_status, start_dt: datetime | None) -> str:
    if sp_status == "live":
        return "live"
    if sp_status == "finished":
        return "finished"
    if sp_status == "not_started":
        return "pre_game"
    if match_status is not None:
        return "live"
    return "pre_game"


def _parse_matches_from_ng_state(ng_state: dict) -> list[dict]:
    matches_key = 'sp-matches:{"sport_id":"hockey"}'
    if matches_key not in ng_state:
        return []
    matches_data = ng_state[matches_key]
    items = matches_data.get("items", [])

    results = []
    for item in items:
        tid = item.get("tournament_id")
        if tid not in TARGET_TOURNAMENTS:
            continue

        league = TOURNAMENT_ID_TO_LEAGUE[tid]

        home_name = item.get("home", {}).get("name", "").strip()
        away_name = item.get("away", {}).get("name", "").strip()
        if not home_name or not away_name:
            continue

        home_name = canonical_team_name(home_name)
        away_name = canonical_team_name(away_name)

        start_str = item.get("start")
        start_dt = None
        if start_str:
            try:
                start_dt = datetime.fromisoformat(start_str)
            except (ValueError, TypeError):
                pass

        sp_status = item.get("status", "not_started")
        match_status = item.get("match_status")
        status = _status_from_sportplustv(sp_status, match_status, start_dt)

        home_pk = item.get("home", {}).get("pk_id", 0)
        away_pk = item.get("away", {}).get("pk_id", 0)
        home_score, away_score = _parse_score_array(item.get("score"), home_pk, away_pk)

        results.append({
            "team_home": home_name,
            "team_away": away_name,
            "league": league,
            "datetime_utc": start_dt.astimezone(timezone.utc).replace(tzinfo=None) if start_dt else None,
            "status": status,
            "home_score": home_score,
            "away_score": away_score,
            "sp_match_id": item.get("id"),
            "sp_tournament_id": tid,
        })

    return results


async def _fetch_match_detail(sp_match_id: int) -> dict:
    url = f"{SPORTPLUSTV_MATCH_API}?id={sp_match_id}&lang=ru"
    raw = await _curl_get(url, retries=2)
    if not raw:
        logger.warning("SportPlusTV: empty detail response for match %s", sp_match_id)
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SportPlusTV: bad JSON for match %s: %s", sp_match_id, raw[:200])
        return {}

    item = data.get("item", {})
    if not item:
        logger.warning("SportPlusTV: no item for match %s: %s", sp_match_id, raw[:200])
        return {}

    streams = []

    ls = item.get("ls")
    if ls and isinstance(ls, list):
        for i, m3u8_url in enumerate(ls):
            if m3u8_url and isinstance(m3u8_url, str) and m3u8_url.startswith("http"):
                streams.append({
                    "url": m3u8_url,
                    "quality": "auto",
                    "source": f"sportplustv",
                })

    tv = item.get("tv")
    if tv and isinstance(tv, list):
        for tv_item in tv:
            tv_url = tv_item.get("url") if isinstance(tv_item, dict) else None
            if tv_url and isinstance(tv_url, str) and tv_url.startswith("http"):
                source = "sportplustv"
                if "rutube" in tv_url:
                    source = "rutube"
                elif "youtube" in tv_url:
                    source = "youtube"
                elif "vk.com" in tv_url or "vkvideo" in tv_url:
                    source = "vk"
                streams.append({
                    "url": tv_url,
                    "quality": "auto",
                    "source": source,
                })

    sp_list = item.get("sp")
    if sp_list and isinstance(sp_list, list):
        for sp_item in sp_list:
            sp_url = sp_item.get("url") if isinstance(sp_item, dict) else None
            if sp_url and isinstance(sp_url, str) and sp_url.startswith("http"):
                streams.append({
                    "url": sp_url,
                    "quality": "auto",
                    "source": "sportplustv",
                })

    result = {"streams": streams}

    if not streams:
        logger.info(
            "SportPlusTV: match %s has no streams (ls=%s tv=%s sp=%s) ls_val=%s",
            sp_match_id,
            type(item.get("ls")).__name__,
            type(item.get("tv")).__name__,
            type(item.get("sp")).__name__,
            json.dumps(item.get("ls"), ensure_ascii=False)[:300],
        )

    home_pk = item.get("home", {}).get("pk_id")
    away_pk = item.get("away", {}).get("pk_id")
    score_list = item.get("score")
    if score_list and home_pk and away_pk:
        h, a = _parse_score_array(score_list, home_pk, away_pk)
        result["home_score"] = h
        result["away_score"] = a

    return result


async def scrape_sportplustv_matches() -> list[dict]:
    # сайт иногда отдаёт «пустую» оболочку без ng-state — повторяем
    ng_state = None
    for attempt in range(4):
        html = await _curl_get(SPORTPLUSTV_HOCKEY)
        if html:
            ng_state = _extract_ng_state(html)
            if ng_state:
                break
        await asyncio.sleep(2 * (attempt + 1))
    if not ng_state:
        logger.warning("SportPlusTV: ng-state not found")
        return []

    matches = _parse_matches_from_ng_state(ng_state)
    if not matches:
        logger.info("SportPlusTV: no VHL matches found")
        return []

    sem = asyncio.Semaphore(5)

    async def _fetch_with_sem(m: dict) -> dict:
        sp_id = m.get("sp_match_id")
        if not sp_id:
            return m
        async with sem:
            detail = await _fetch_match_detail(sp_id)
        m["stream_urls"] = detail.get("streams", [])
        if detail.get("home_score") is not None:
            m["home_score"] = detail["home_score"]
        if detail.get("away_score") is not None:
            m["away_score"] = detail["away_score"]
        return m

    results = await asyncio.gather(*(_fetch_with_sem(m) for m in matches))

    logger.info(
        "SportPlusTV: found %d matches (VHL), %d with streams",
        len(results),
        sum(1 for r in results if r.get("stream_urls")),
    )
    return results


if __name__ == "__main__":
    matches = asyncio.run(scrape_sportplustv_matches())
    for m in matches:
        streams = m.get("stream_urls", [])
        score = f" ({m['home_score']}:{m['away_score']})" if m.get("home_score") is not None else ""
        print(f"[{m['league']}] {m['team_home']} - {m['team_away']} [{m['status']}]{score} streams={len(streams)}")
        for s in streams:
            print(f"  -> [{s['source']}] {s['url'][:100]}")
