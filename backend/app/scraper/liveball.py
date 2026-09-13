import httpx
import re
from datetime import datetime, timezone, timedelta


LIVEBALL_COOKIES = "lang=ru; uid=3e4b0acc-25e4-f1dc-31f9-62e5cd753750; lb_sess=397343088.NAhRW2CQbsycB8ChyZjI2g.1796389724.FV_axs6lrY1AXc6cfBPcbDjuFHY_H3KNKGCoX0LcvBY; lb_tz=Asia/Omsk"
LIVEBALL_HEADERS = {
    "Cookie": LIVEBALL_COOKIES,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

LIVEBALL_API_HEADERS = {
    "Cookie": LIVEBALL_COOKIES,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://liveball.im/hockey",
    "X-Requested-With": "XMLHttpRequest",
}

LEAGUE_MAP = {
    "КХЛ": "KHL",
    "ВХЛ": "VHL",
    "МХЛ": "MHL",
}

ALLOWED_LEAGUES = {"KHL", "VHL", "MHL"}

STATUS_MAP = {
    "live": "live",
    "up": "pre_game",
    "fin": "finished",
}


async def fetch_live_scores() -> dict:
    """Fetch live scores from /api/live?sport=hockey"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://liveball.im/api/live?sport=hockey",
                headers=LIVEBALL_API_HEADERS,
            )
            if r.status_code != 200:
                return {}
            data = r.json()
            return {m["id"]: m for m in data.get("m", [])}
    except Exception:
        return {}


async def scrape_liveball_schedule(date_str: str = None) -> list[dict]:
    """Scrape hockey schedule from liveball.im for a given date."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    url = "https://liveball.im/hockey"
    if date_str != datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        url += f"?date={date_str}"

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=LIVEBALL_HEADERS)
            if r.status_code != 200:
                print(f"[liveball] HTTP {r.status_code}")
                return []
            text = r.text
    except Exception as e:
        print(f"[liveball] Error fetching schedule: {e}")
        return []

    fixture_pattern = re.compile(
        r'<a\s+class="lb-fixture"\s+href="/hockey/match/(\d+)"\s+data-st="([^"]+)"\s+data-ts="(\d+)">(.*?)</a>',
        re.DOTALL,
    )
    league_pattern = re.compile(r'href="/hockey/league/(\d+)"[^>]*>([^<]+)</a>')

    leagues = list(league_pattern.finditer(text))
    fixtures = list(fixture_pattern.finditer(text))

    matches = []
    for f in fixtures:
        match_id = int(f.group(1))
        status_raw = f.group(2)
        timestamp = int(f.group(3))
        content = f.group(4)

        home_match = re.search(r'lb-fixture__home.*?<span>([^<]*)</span>', content, re.DOTALL)
        away_match = re.search(r'lb-fixture__away.*?<span>([^<]*)</span>', content, re.DOTALL)
        score_match = re.search(r'data-score>([^<]*)<', content, re.DOTALL)

        home = home_match.group(1).strip() if home_match else ""
        away = away_match.group(1).strip() if away_match else ""
        score_raw = score_match.group(1).strip() if score_match else ""

        league_name = "unknown"
        league_id = "0"
        fixture_pos = f.start()
        for l in reversed(leagues):
            if l.start() < fixture_pos:
                league_name = l.group(2).strip()
                league_id = l.group(1)
                break

        league = LEAGUE_MAP.get(league_name, league_name)

        status = STATUS_MAP.get(status_raw, status_raw)

        dt_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        score = None
        if score_raw and ":" in score_raw and "–" not in score_raw:
            score = score_raw.replace(" ", "")

        matches.append({
            "liveball_id": match_id,
            "league": league,
            "team_home": home,
            "team_away": away,
            "datetime_utc": dt_utc.replace(tzinfo=None),
            "status": status,
            "score": score,
            "stream_url": f"https://liveball.im/hockey/match/{match_id}",
        })

    matches = [m for m in matches if m["league"] in ALLOWED_LEAGUES]

    live_scores = await fetch_live_scores()
    for m in matches:
        lb_match = live_scores.get(m["liveball_id"])
        if lb_match:
            if lb_match.get("sf") == "live":
                m["status"] = "live"
            elif lb_match.get("sf") == "fin":
                m["status"] = "finished"

            g = lb_match.get("g")
            if g and len(g) == 2:
                m["score"] = f"{g[0]}:{g[1]}"

            st = lb_match.get("st", "")
            period_map = {
                "P1": "1-й период",
                "P2": "2-й период",
                "P3": "3-й период",
                "OT": "ОТ",
                "AOT": "ОТ",
                "BT": "Перерыв",
                "FT": "Завершен",
                "G1": "1-й период",
                "G2": "2-й период",
                "G3": "3-й период",
            }
            m["period"] = period_map.get(st, st)

    return matches
