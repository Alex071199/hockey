import html as hmod
import logging
import re

import httpx

logger = logging.getLogger(__name__)

FINISHED_STATUSES = {"ft", "apen", "aot"}

STATUS_TO_WIN_TYPE: dict[str, str | None] = {
    "ft": None,
    "aot": "ОТ",
    "apen": "Б",
}

URLS = [
    "https://www.liveresult.ru/hockey/matches",
    "https://www.liveresult.ru/hockey/matches/yesterday",
]


def _extract_matches_from_page(decoded: str) -> list[dict]:
    """Extract all finished matches from decoded liveresult page HTML.

    The page embeds a giant HTML-entity-encoded JSON blob with structure:
    "groups":{"TOURNAMENT_KEY":{"cup_name_default":"VHL","matches":{"m_123":{...}}}}
    We find all "m_NNNNN":{ blocks, parse each one, and determine its tournament.
    """
    all_cup_positions = [
        (m.start(), m.group(1))
        for m in re.finditer(r'"cup_name_default":"([^"]+)"', decoded)
    ]
    all_match_positions = [
        (m.start(), m.group(1))
        for m in re.finditer(r'"m_(\d+)":\{', decoded)
    ]

    results: list[dict] = []
    for match_pos, mid in all_match_positions:
        cup_name = None
        for cup_pos, cup in reversed(all_cup_positions):
            if cup_pos < match_pos:
                cup_name = cup
                break

        start = match_pos + len(f'"m_{mid}":{{')
        brace_count = 1
        i = start
        while i < len(decoded) and brace_count > 0:
            if decoded[i] == "{":
                brace_count += 1
            elif decoded[i] == "}":
                brace_count -= 1
            i += 1
        obj_str = decoded[start : i - 1]

        t1 = re.search(r'"team1_name":"([^"]+)"', obj_str)
        t2 = re.search(r'"team2_name":"([^"]+)"', obj_str)
        score = re.search(r'"score":"([^"]+)"', obj_str)
        status = re.search(r'"status":"([^"]+)"', obj_str)

        if t1 and t2 and score and status and status.group(1) in FINISHED_STATUSES:
            st = status.group(1)
            results.append(
                {
                    "team_home": t1.group(1),
                    "team_away": t2.group(1),
                    "score": score.group(1),
                    "win_type": STATUS_TO_WIN_TYPE.get(st),
                    "cup": cup_name or "",
                }
            )

    return results


async def fetch_liveresult_scores(client: httpx.AsyncClient) -> list[dict]:
    """Fetch finished hockey match scores from liveresult.ru (today + yesterday)."""
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for url in URLS:
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "ru-RU,ru;q=0.9",
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            decoded = hmod.unescape(response.text)
            page_matches = _extract_matches_from_page(decoded)
            for m in page_matches:
                key = (m["team_home"], m["team_away"])
                if key not in seen:
                    seen.add(key)
                    results.append(m)
        except Exception as e:
            logger.error("Error fetching liveresult.ru %s: %s", url, e)

    logger.info("Fetched %d finished scores from liveresult.ru", len(results))
    return results


ALIAS_MAP: dict[str, str] = {
    "югра": "угра",
    "горняк-угмк верхняя пышма": "горняк",
}


def teams_match(db_name: str, lr_name: str) -> bool:
    """Check if two team names refer to the same team (fuzzy matching)."""
    db = db_name.strip().lower()
    lr = lr_name.strip().lower()
    if db == lr:
        return True
    # Check alias mapping
    lr_canonical = ALIAS_MAP.get(lr, lr)
    db_canonical = ALIAS_MAP.get(db, db)
    if lr_canonical == db_canonical:
        return True
    if db_canonical in lr_canonical or lr_canonical in db_canonical:
        return True
    if db in lr or lr in db:
        return True
    for prefix in ("хк ", "фк "):
        db_clean = db.replace(prefix, "", 1)
        lr_clean = lr.replace(prefix, "", 1)
        if db_clean == lr_clean or db_clean in lr_clean or lr_clean in db_clean:
            return True
    return False
