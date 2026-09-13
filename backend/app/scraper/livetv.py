import asyncio
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from app.scraper.team_names import canonical_team_name

CURL = shutil.which("curl") or "curl"
LIVETV_BASE = "https://livetv.sx"
LIVETV_ALT = "https://livetv903.me"

LEAGUE_MAP = {
    "КХЛ": "KHL",
}

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


def _curl_get_sync(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "-H", "Accept-Language: ru-RU,ru;q=0.9",
                "--connect-timeout", "15",
                "--max-time", "25",
                url,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            if r.stdout and len(r.stdout) > 500:
                return r.stdout.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


async def _curl_get(url: str, retries: int = 3) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _curl_get_sync, url, retries)


def _parse_matches(html: str) -> list[dict]:
    """Parse livetv.sx main/allupcoming page for KHL hockey matches."""
    matches = []
    seen_ids = set()

    icon_pattern = r'<img[^>]*alt="Хоккей\.\s*([^"]+)"[^>]*>'
    for icon_match in re.finditer(icon_pattern, html):
        pos = icon_match.start()
        league_text = icon_match.group(1).strip()

        league = None
        for key, val in LEAGUE_MAP.items():
            if key in league_text:
                league = val
                break
        if not league:
            continue

        chunk = html[max(0, pos - 300):min(len(html), pos + 1200)]

        event_match = re.search(r'href="(?:/eventinfo/)?(\d+)_([a-z0-9_]+)/"', chunk)
        if not event_match:
            event_match = re.search(r'eventinfo/(\d+)_([a-z0-9_]+)', chunk)
        if not event_match:
            continue

        eid = event_match.group(1)
        slug = event_match.group(2)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)

        teams_match = re.search(r'>([^<]*?&ndash;[^<]*?)</a>', chunk)
        if not teams_match:
            teams_match = re.search(r'>([^<]*?–[^<]*?)</a>', chunk)
        if teams_match:
            raw = teams_match.group(1).replace('&ndash;', '–').replace('&nbsp;', ' ').strip()
            parts = re.split(r'\s*–\s*', raw, maxsplit=1)
        else:
            parts = slug.replace('_', ' ').split()

        if len(parts) >= 2:
            home = parts[0].strip()
            away = parts[1].strip()
        elif len(parts) == 2:
            home, away = parts[0], parts[1]
        else:
            continue

        if not home or not away:
            continue

        time_match = re.search(r'(\d{1,2}:\d{2})\s*\(([^)]+)\)', chunk)
        time_str = time_match.group(1) if time_match else ""
        league_label = time_match.group(2) if time_match else league_text

        score_match = re.search(r'&nbsp;\s*(\d+)\s*:\s*(\d+)', chunk)
        score = f"{score_match.group(1)}:{score_match.group(2)}" if score_match else None

        is_live = 'class="live"' in chunk.lower()

        matches.append({
            "event_id": eid,
            "slug": slug,
            "league": league,
            "team_home": home,
            "team_away": away,
            "time_str": time_str,
            "league_label": league_label,
            "score": score,
            "is_live": is_live,
        })

    return matches


def _parse_event_streams(html: str) -> list[dict]:
    """Parse event page for webplayer/acestream links."""
    streams = []
    seen = set()

    def add(full_url: str, source: str) -> None:
        if full_url in seen:
            return
        seen.add(full_url)
        streams.append({"url": full_url, "quality": "auto", "source": source})

    # Any webplayer.php / webplayer2.php href with any transport (t=...),
    # including &amp;-escaped variants and other param orders.
    for raw in re.findall(r'href="([^"]*webplayer(?:2)?\.php\?t=[^"]+)"', html):
        path = raw.replace("&amp;", "&")
        if path.startswith("//"):
            path = f"https:{path}"
        elif path.startswith("/"):
            path = f"{LIVETV_BASE}{path}"
        m_t = re.search(r"[?&]t=([a-z0-9_]+)&", path)
        transport = m_t.group(1) if m_t else "ifr"
        if transport == "acestream":
            continue  # same as the direct acestream:// link, added below
        source = "livetv" if transport == "ifr" else f"livetv_{transport}"
        add(path, source)

    # Any acestream:// link (in href, onclick or data attributes).
    for ace in re.findall(r"acestream://[a-z0-9]{32,}", html):
        add(ace, "acestream")

    return streams


async def scrape_livetv_matches() -> list[dict]:
    """Scrape livetv.sx for KHL matches with stream URLs."""
    html = await _curl_get(f"{LIVETV_BASE}/")
    if not html:
        return []

    basic_matches = _parse_matches(html)

    enriched = []
    for m in basic_matches:
        streams = []
        try:
            event_url = f"{LIVETV_BASE}/eventinfo/{m['event_id']}_{m['slug']}/"
            event_html = await _curl_get(event_url)
            if event_html:
                streams = _parse_event_streams(event_html)
        except Exception:
            pass

        dt_utc = _parse_time(m["time_str"]) if m["time_str"] else None

        status = "live" if m["is_live"] else "pre_game"

        enriched.append({
            "livetv_id": m["event_id"],
            "league": m["league"],
            "team_home": canonical_team_name(_normalize_team(m["team_home"])),
            "team_away": canonical_team_name(_normalize_team(m["team_away"])),
            "datetime_utc": dt_utc,
            "status": status,
            "stream_urls": streams,
        })

    return enriched


def _parse_time(time_str: str) -> datetime | None:
    m = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now_utc.date()
    dt_msk = datetime.combine(today, datetime.min.time()).replace(hour=hour, minute=minute)
    dt_utc = dt_msk - timedelta(hours=3)
    if dt_utc > now_utc + timedelta(days=2):
        dt_utc -= timedelta(days=1)
    return dt_utc


if __name__ == "__main__":
    results = asyncio.run(scrape_livetv_matches())
    print(f"Found {len(results)} matches")
    for r in results:
        print(f"  [{r['league']}] {r['team_home']} - {r['team_away']} ({r['status']}) {len(r['stream_urls'])} streams")
