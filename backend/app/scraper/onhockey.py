import asyncio
import re
import shutil
import subprocess
from html import unescape

from app.scraper.team_names import translate_team_name, KHL_TEAMS_RU, canonical_team_name

CURL = shutil.which("curl") or "curl"

ONHOCKEY_BASE = "https://onhockey.tv"
ONHOCKEY_SCHEDULE = f"{ONHOCKEY_BASE}/schedule_table.php"

LEAGUE_MAP = {
    "RU": "VHL",
    "KHL": "KHL",
    "MHL": "MHL",
}

LEAGUE_KEYWORDS = {
    "MHL": "MHL",
    "KHL": "KHL",
}


def _league_by_teams(home_ru: str, away_ru: str) -> str | None:
    """Both teams are known KHL clubs -> KHL, regardless of section label."""
    if home_ru in KHL_TEAMS_RU and away_ru in KHL_TEAMS_RU:
        return "KHL"
    return None

TEAM_RENAME = {
    "Куньлунь РС": "Шанхайские Драконы",
    "Куньлунь Ред Стар": "Шанхайские Драконы",
    "Куньлунь": "Шанхайские Драконы",
    "Kunlun RS": "Шанхайские Драконы",
    "Kunlun Red Star": "Шанхайские Драконы",
    "Kunlun": "Шанхайские Драконы",
}


def _normalize_team(name: str) -> str:
    for old, new in TEAM_RENAME.items():
        if old.lower() in name.lower():
            return new
    return name


def _curl_get_sync(url: str, retries: int = 5) -> str:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L",
                "-H", "User-Agent: Mozilla/5.0",
                "-H", "X-Requested-With: XMLHttpRequest",
                "-H", f"Referer: {ONHOCKEY_BASE}/",
                "--connect-timeout", "20",
                "--max-time", "30",
                url,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=35)
            if r.stdout and len(r.stdout) > 100:
                return r.stdout.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


async def _curl_get(url: str, retries: int = 5) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _curl_get_sync, url, retries)


def _clean(text: str) -> str:
    text = unescape(text)
    text = re.sub(r'&#?\w+;', '', text)
    return text.strip()


def _parse_schedule(html: str) -> list[dict]:
    """Parse schedule_table.php HTML into matches with stream URLs."""
    matches = []

    tbodies = re.findall(
        r"<tbody class='(\w+)'.*?<b>([^<]+)</b>.*?</tr>(.*?)</tbody>",
        html, re.DOTALL,
    )

    for league_class, league_name, content in tbodies:
        league_upper = _clean(league_name).upper()

        # Strict label match: only VHL/MHL sections are taken.
        # Other leagues sharing class='RU' (Jas/Pro Hokei Ligasy,
        # Extraleague, KHL, NHL, ...) are skipped.
        if "MHL" in league_upper or "МХЛ" in league_upper:
            detected_league = "MHL"
        elif "VHL" in league_upper or "ВХЛ" in league_upper:
            detected_league = "VHL"
        else:
            continue

        game_matches = re.findall(
            r"<text class='game_hour'[^>]*>(\d+)</text>:(\d+)</td><td>([^<]+)",
            content,
        )
        gamelinks = re.findall(
            r"<div class='gamelinks'[^>]*>(.*?)</div>",
            content, re.DOTALL,
        )

        for i, (hour, minute, teams_raw) in enumerate(game_matches):
            teams = _clean(teams_raw)
            # Split on dash surrounded by whitespace first, so hyphenated
            # club names like "Dinamo-Shinnik" stay intact.
            parts = re.split(r'\s+-\s+', teams, maxsplit=1)
            if len(parts) != 2:
                parts = re.split(r'\s*-\s*', teams, maxsplit=1)
            if len(parts) != 2:
                continue
            home = parts[0].strip()
            away = parts[1].strip()
            if not home or not away:
                continue

            links_html = gamelinks[i] if i < len(gamelinks) else ""
            stream_urls = _extract_streams(links_html)

            home_ru = canonical_team_name(translate_team_name(_normalize_team(home)))
            away_ru = canonical_team_name(translate_team_name(_normalize_team(away)))
            team_league = _league_by_teams(home_ru, away_ru)

            league = team_league or detected_league
            # Only VHL/MHL are taken from onhockey — KHL comes from
            # livetv, everything else (NHL, etc.) is ignored.
            if league not in ("VHL", "MHL"):
                continue

            matches.append({
                "team_home": home_ru,
                "team_away": away_ru,
                "league": league,
                "hour": hour,
                "minute": minute,
                "stream_urls": stream_urls,
            })

    return matches


def _extract_streams(html: str) -> list[dict]:
    """Extract stream URLs from gamelinks div content."""
    streams = []
    links = re.findall(r"href=['\"]([^'\"]+)['\"][^>]*>([^<]*)</a>", html)
    for href, label in links:
        label = label.strip()
        if not label:
            continue

        url = href
        if href.startswith("//"):
            url = f"https:{href}"
        elif href.startswith("/"):
            url = f"{ONHOCKEY_BASE}{href}"

        source = "onhockey"
        if "np_stream400.php" in url:
            channel_match = re.search(r'channel=([^&"\']+)', url)
            if channel_match:
                channel = channel_match.group(1)
                if channel.startswith("//"):
                    channel = f"https:{channel}"
                url = channel
                source = _detect_source(url)
        elif "np_youtube.php" in url:
            ch = re.search(r'channel=([^&"\']+)', url)
            if ch:
                url = f"https://www.youtube.com/embed/{ch.group(1)}"
                source = "youtube"
        elif "np_vk.php" in url:
            ch = re.search(r'channel=([^&"\']+)', url)
            if ch:
                vk_id = ch.group(1).replace("%26", "&")
                url = f"https://vk.com/video_ext.php?{vk_id}"
                source = "vk"
        elif "np_fluidtv.php" in url:
            ch = re.search(r'channel=([^&"\']+)', url)
            if ch:
                url = ch.group(1)
                source = "fluidtv"
        elif "sportplus.watch" in url or "sportplustv" in url:
            source = "sportplus"
        elif "hockeyslovakia.sk" in url:
            source = "vimeo"

        if url and url.startswith("http"):
            streams.append({"url": url, "quality": "auto", "source": source})

    return streams


def _detect_source(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "vk.com" in url or "vkvideo" in url:
        return "vk"
    if "rutube.ru" in url:
        return "rutube"
    if "sportplus.watch" in url:
        return "sportplus"
    if "embedded.slevel.ru" in url:
        return "slevel"
    if "vdocity.com" in url:
        return "vdocity"
    if "videocdn" in url:
        return "videocdn"
    if "wideiptv.top" in url:
        return "lovecdn"
    if "red.sport" in url:
        return "redsport"
    if "ngenix.net" in url or "m3u8" in url:
        return "hls"
    if ".m3u8" in url:
        return "hls"
    return "onhockey"


async def scrape_onhockey_streams() -> dict[str, list[dict]]:
    """
    Scrape onhockey.tv schedule_table.php for stream URLs.
    Returns dict: {"LEAGUE|HH:MM": [{"url": ..., "source": ...}]}
    """
    html = await _curl_get(ONHOCKEY_SCHEDULE)
    if not html:
        return {}

    parsed = _parse_schedule(html)
    result = {}

    for m in parsed:
        if not m["stream_urls"]:
            continue
        key = f"{m['league']}|{m['hour']}:{m['minute']}"
        existing = result.get(key, [])
        existing.extend(m["stream_urls"])
        result[key] = existing

    return result


async def scrape_onhockey_matches() -> list[dict]:
    """
    Scrape onhockey.tv and return full match info (teams, time, streams).
    """
    html = await _curl_get(ONHOCKEY_SCHEDULE)
    if not html:
        return []
    return _parse_schedule(html)


if __name__ == "__main__":
    streams = asyncio.run(scrape_onhockey_streams())
    for key, urls in streams.items():
        print(f"{key}: {len(urls)} streams")
        for s in urls:
            print(f"  [{s['source']}] {s['url'][:100]}")
