"""Официальный API НХЛ (api-web.nhle.com/v1) — расписание, счёт, статистика.

Статистика и составы не хранятся в БД: как у КХЛ, они собираются на лету
из score/gamecenter и кэшируются в памяти. Расписание игр API пишет в БД
джоба sync_nhl_schedule (scheduler/tasks.py).
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api-web.nhle.com/v1"

# API отдаёт 403 запросам без браузерного User-Agent
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_cache: dict[str, dict] = {}
SCORE_TTL = 600        # расписание дня
SCORE_LIVE_TTL = 30    # live-обновления счёта
STATS_TTL = 300        # статистика завершённого матча
STATS_LIVE_TTL = 15    # статистика live-матча

# Обзоры игр (recap) НХЛ публикует как обычные видео на nhl.com; api-web.nhle.com
# про видео не знает, поэтому индекс строим из HTML-страниц, где перечислены
# ролики: топика game-recaps + видео-сайтмап. Slug вида 'stl-at-nsh-recap'
# несёт 13-значный id ролика — он играет во встроенном плеере Brightcove.
_RECAP_TOPIC_URL = "https://www.nhl.com/video/topic/game-recaps/"
_RECAP_SITEMAP_URL = "https://www.nhl.com/sitemap/sitemap-videos.xml"
BRIGHTCOVE_ACCOUNT = "6415718365001"
RECAP_INDEX_TTL = 1800  # перечитываем индекс не чаще раза в полчаса
# Ловим только основной путь www.nhl.com/video/... (и топик video/topic/...):
# командные копии вида /blues/video/... — отдельные ролики с чужими id.
_RECAP_RE = re.compile(
    r"(?<![a-z0-9])(?:https?://www\.nhl\.com)?/video/(?:topic/game-recaps/)?"
    r"([a-z0-9]+(?:-at-|-vs-)[a-z0-9]+-recap)-(\d{13})"
)

_recap_index: dict[str, str] = {}
_recap_index_at = 0.0

# API даёт только англ. abbrev — русские имена берём из той же карты,
# что и ключи team-logos.ts (точно совпадают с именами в БД от 1win).
ABBR_TO_RU: dict[str, str] = {
    "ANA": "Анахайм Дакс",
    "BUF": "Баффало Сейбрз",
    "BOS": "Бостон Брюинз",
    "VAN": "Ванкувер Кэнакс",
    "WSH": "Вашингтон Кэпиталз",
    "VGK": "Вегас Голден Найтс",
    "WPG": "Виннипег Джетс",
    "DAL": "Даллас Старз",
    "DET": "Детройт Ред Уингз",
    "CGY": "Калгари Флэймз",
    "CAR": "Каролина Харрикейнз",
    "CBJ": "Коламбус Блю Джекетс",
    "COL": "Колорадо Эвеланш",
    "LAK": "Лос-Анджелес Кингз",
    "MIN": "Миннесота Уайлд",
    "MTL": "Монреаль Канадиенс",
    "NJD": "Нью-Джерси Девилз",
    "NYI": "Нью-Йорк Айлендерс",
    "NYR": "Нью-Йорк Рейнджерс",
    "NSH": "Нэшвилл Предаторз",
    "OTT": "Оттава Сенаторз",
    "PIT": "Питтсбург Пингвинз",
    "SJS": "Сан-Хосе Шаркс",
    "STL": "Сент-Луис Блюз",
    "SEA": "Сиэтл Кракен",
    "TBL": "Тампа-Бэй Лайтнинг",
    "TOR": "Торонто Мейпл Лифс",
    "PHI": "Филадельфия Флайерз",
    "FLA": "Флорида Пантерз",
    "CHI": "Чикаго Блэкхокс",
    "EDM": "Эдмонтон Ойлерз",
    "UTA": "Юта Маммот",
}

# descKey штрафа -> русское название (что не вошло — показываем как есть)
_PENALTY_RU: dict[str, str] = {
    "tripping": "Подножка",
    "hooking": "Подцеп",
    "slashing": "Рубок",
    "holding": "Задержание",
    "holding-the-stick": "Задержка клюшки",
    "interference": "Вмешательство",
    "cross-checking": "Крестовый удар",
    "roughing": "Грубая игра",
    "high-sticking": "Удар высокой клюшкой",
    "illegal-check-to-head": "Удар в голову",
    "boarding": "Вышибание",
    "charging": "Разгон",
    "clipping": "Подрезание",
    "elbowing": "Удар локтем",
    "fighting": "Драка",
    "instigator": "Зачинщик",
    "unsportsmanlike-conduct": "Неспортивное поведение",
    "unsportsmanlike-conduct-starter": "Неспортивное поведение",
    "too-many-men-on-the-ice": "Лишний игрок на площадке",
    "delay-of-game": "Задержка игры",
    "puck-over-glass": "Шайба за сектор",
    "goalie-interference": "Помехи вратарю",
    "bench-minor": "Штраф скамейки",
    "misconduct": "Дисциплинарное взыскание",
    "game-misconduct": "Удаление до конца игры",
    "kicking-puck": "Удар ногой",
    "throwing-stick": "Бросок клюшки",
    "hand-pass": "Передача рукой",
    "head-butting": "Удар головой",
    "closing-hand-on-puck": "Рука на шайбе",
    "helmet-removed": "Снятие шлема",
    "playing-without-helmet": "Игра без шлема",
}


async def _get_json(url: str) -> dict | list:
    async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:
        resp = await client.get(url)
        if resp.status_code == 404:
            raise LookupError(f"NHL API: not found ({url})")
        resp.raise_for_status()
        return resp.json()


async def _cached_json(key: str, url: str, max_age: float) -> dict | list:
    cached = _cache.get(key)
    if cached and time.monotonic() - cached["at"] < max_age:
        return cached["data"]
    data = await _get_json(url)
    _cache[key] = {"at": time.monotonic(), "data": data}
    return data


def _valid_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


async def get_score(date_str: str, max_age: float = SCORE_TTL) -> dict:
    """score/{date}: расписание дня (games) + gameWeek. 404/мусор -> {}."""
    if not _valid_date(date_str):
        return {}
    key = f"nhl_score_{date_str}"
    cached = _cache.get(key)
    if cached and time.monotonic() - cached["at"] < max_age:
        return cached["data"]
    try:
        data = await _get_json(f"{BASE_URL}/score/{date_str}")
    except Exception as e:
        logger.warning("NHL score %s failed: %s", date_str, e)
        return {}
    data = data if isinstance(data, dict) else {}
    _cache[key] = {"at": time.monotonic(), "data": data}
    return data


async def get_games(date_str: str, max_age: float = SCORE_TTL) -> list[dict]:
    games = (await get_score(date_str, max_age=max_age)).get("games") or []
    return [g for g in games if isinstance(g, dict) and g.get("id")]


async def get_games_window(
    days_back: int = 1, days_fwd: int = 7, max_age: float = SCORE_TTL
) -> dict[int, dict]:
    """Игры +-окно дней, ключ — game id (дедуп между днями)."""
    now = datetime.now(timezone.utc)
    out: dict[int, dict] = {}
    for i in range(-days_back, days_fwd + 1):
        date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        for g in await get_games(date_str, max_age=max_age):
            try:
                out[int(g["id"])] = g
            except (TypeError, ValueError):
                continue
    return out


def team_ru(team: dict | None) -> str:
    """Русское название команды (точно как в БД): abbrev -> карта, иначе англ."""
    if not team:
        return ""
    abbrev = (team.get("abbrev") or "").strip()
    if abbrev in ABBR_TO_RU:
        return ABBR_TO_RU[abbrev]
    return (team.get("name") or {}).get("default") or abbrev


def _pair(home: str | None, away: str | None) -> tuple[str, str]:
    return ((home or "").casefold().strip(), (away or "").casefold().strip())


def game_status(game: dict | None) -> str | None:
    """Статус строки расписания; None — состояние неизвестно, не трогать."""
    if not game:
        return None
    state = game.get("gameState")
    if state in ("LIVE", "CRIT"):
        clock = game.get("clock") or {}
        return "break" if clock.get("inIntermission") else "live"
    if state in ("OFF", "FINAL"):
        return "finished"
    if state in ("FUT", "PRE"):
        return "pre_game"
    return None


def game_datetime(game: dict) -> datetime | None:
    """startTimeUTC -> наивный datetime UTC (как datetime_utc в БД)."""
    raw = game.get("startTimeUTC")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def game_scores(game: dict) -> tuple[int | None, int | None]:
    home = (game.get("homeTeam") or {}).get("score")
    away = (game.get("awayTeam") or {}).get("score")
    return (home, away) if home is not None and away is not None else (None, None)


def period_label(game: dict) -> str | None:
    """Подпись периода для строки расписания (как у КХЛ)."""
    status = game_status(game)
    if status == "finished":
        return "Завершён"
    if status in (None, "pre_game"):
        return None
    if status == "break":
        return "Перерыв"
    pd = game.get("periodDescriptor") or {}
    ptype = (pd.get("periodType") or "").upper()
    if ptype == "SO":
        return "Буллиты"
    if ptype == "OT":
        return "Овертайм"
    try:
        number = int(pd.get("number") or 0)
    except (TypeError, ValueError):
        return None
    return f"{number}-й период" if number > 0 else None


def finish_type(game: dict | None) -> str:
    """reg / ot / so для заголовка статистики."""
    if game:
        got = ((game.get("gameOutcome") or {}).get("lastPeriodType")) or ""
        if not got:
            got = ((game.get("periodDescriptor") or {}).get("periodType")) or ""
        upper = str(got).upper()
        if upper == "OT":
            return "ot"
        if upper == "SO":
            return "so"
    return "reg"


def find_game_by_pair(
    games, home: str, away: str, dt: datetime | None = None, window: int = 6 * 3600
) -> dict | None:
    """Игра с той же парой команд (и близким стартом, если dt дан)."""
    want = _pair(home, away)
    best: dict | None = None
    best_delta = 0.0
    for g in games or []:
        if not isinstance(g, dict):
            continue
        if _pair(team_ru(g.get("homeTeam")), team_ru(g.get("awayTeam"))) != want:
            continue
        game_dt = game_datetime(g)
        if dt and game_dt:
            delta = abs((game_dt - dt).total_seconds())
            if delta > window:
                continue
            if best is None or delta < best_delta:
                best, best_delta = g, delta
        elif best is None:
            best = g
    return best


async def _load_recap_index() -> dict[str, str]:
    """Индекс обзоров: slug игры ('stl-at-nsh-recap') -> id ролика Brightcove.

    Источники — HTML-страницы nhl.com: топик game-recaps хранит обзоры
    за последние дни, сайтмап дополняет его самыми свежими публикациями.
    """
    global _recap_index_at, _recap_index
    now = time.monotonic()
    if now - _recap_index_at < RECAP_INDEX_TTL:
        return _recap_index
    found: dict[str, str] = {}
    for url in (_RECAP_TOPIC_URL, _RECAP_SITEMAP_URL):
        try:
            async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            for m in _RECAP_RE.finditer(resp.text.replace("\\/", "/")):
                found[m.group(1)] = m.group(2)
        except Exception as e:
            logger.warning("NHL recap index: fetch %s failed: %s", url, e)
    if found:
        _recap_index = found
    _recap_index_at = now
    return _recap_index


async def get_game_recap(away_abbrev: str, home_abbrev: str) -> dict | None:
    """Видео-обзор игры: '{away}-at-{home}-recap' -> id и ссылка плеера."""
    if not (away_abbrev and home_abbrev):
        return None
    index = await _load_recap_index()
    if not index:
        return None
    away, home = away_abbrev.lower(), home_abbrev.lower()
    for slug in (f"{away}-at-{home}-recap", f"{away}-vs-{home}-recap"):
        video_id = index.get(slug)
        if video_id:
            return {
                "video_id": video_id,
                "slug": slug,
                "embed_url": (
                    f"https://players.brightcove.net/{BRIGHTCOVE_ACCOUNT}"
                    f"/default_default/index.html?videoId={video_id}&applicationId=nhl"
                ),
            }
    return None


async def get_match_stats(
    home: str, away: str, date_str: str, live: bool = False, uid: str | None = None
) -> dict:
    """Статистика матча НХЛ в формате MatchStats.tsx (на лету, с кэшем)."""
    game_id: int | None = None
    if uid and uid.startswith("NHL_"):
        try:
            game_id = int(uid.split("_", 1)[1])
        except ValueError:
            game_id = None
    if game_id is None and home and away:
        base = datetime.strptime(date_str, "%Y-%m-%d") if _valid_date(date_str) else datetime.now(timezone.utc)
        games: dict[int, dict] = {}
        for delta in (0, -1, 1):
            d = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
            for g in await get_games(d):
                try:
                    games[int(g["id"])] = g
                except (TypeError, ValueError):
                    continue
        want = _pair(home, away)
        candidates = [
            g for g in games.values()
            if _pair(team_ru(g.get("homeTeam")), team_ru(g.get("awayTeam"))) == want
        ]
        if not candidates:
            raise LookupError(f"Матч {home} - {away} не найден в API НХЛ ({date_str})")
        exact = [g for g in candidates if g.get("gameDate") == date_str]
        picked = (exact or candidates)[0]
        game_id = int(picked["id"])
    if game_id is None:
        raise LookupError("Не удалось определить игру НХЛ (нужен uid NHL_<id> или пара команд)")
    return await _build_match_stats(game_id, home, away, live=live)


async def _build_match_stats(
    game_id: int, home: str, away: str, live: bool
) -> dict:
    max_age = STATS_LIVE_TTL if live else STATS_TTL
    box = await _cached_json(
        f"nhl_box_{game_id}", f"{BASE_URL}/gamecenter/{game_id}/boxscore", max_age
    )
    land = await _cached_json(
        f"nhl_land_{game_id}", f"{BASE_URL}/gamecenter/{game_id}/landing", max_age
    )
    if not isinstance(box, dict) or not isinstance(land, dict):
        raise LookupError(f"Игра {game_id} не найдена в API НХЛ")

    season = box.get("season")
    h_box = box.get("homeTeam") or {}
    a_box = box.get("awayTeam") or {}
    abbr_to_id: dict[str, int] = {}
    for side in (h_box, a_box):
        if side.get("abbrev") and side.get("id"):
            abbr_to_id[side["abbrev"]] = int(side["id"])

    home_name = home or team_ru(h_box)
    away_name = away or team_ru(a_box)
    home_id = int(h_box.get("id") or abbr_to_id.get(h_box.get("abbrev") or "", 0) or 0)
    away_id = int(a_box.get("id") or abbr_to_id.get(a_box.get("abbrev") or "", 0) or 0)

    status = game_status(land) or game_status(box)
    score_home = int(h_box.get("score") or 0)
    score_away = int(a_box.get("score") or 0)
    finish = finish_type(land)

    pbgs = box.get("playerByGameStats") or {}
    h_pb, a_pb = pbgs.get("homeTeam") or {}, pbgs.get("awayTeam") or {}

    def _skaters(pb: dict) -> list[dict]:
        return list(pb.get("forwards") or []) + list(pb.get("defense") or [])

    # --- голы, периоды, буллиты из summary.scoring -------------------------
    scoring = ((land.get("summary") or {}).get("scoring")) or []
    counts: dict[int, list[int]] = {}
    ot_pair = [0, 0]
    so_pair = [0, 0]
    has_so_block = False
    shg_by_abbrev: dict[str, int] = {}
    goals_list: list[dict] = []

    for block in scoring:
        pdx = block.get("periodDescriptor") or {}
        try:
            pnum = int(pdx.get("number") or 0)
        except (TypeError, ValueError):
            pnum = 0
        ptype = (pdx.get("periodType") or "REG").upper()
        for g in block.get("goals") or []:
            abbrev = g.get("teamAbbrev")
            if isinstance(abbrev, dict):
                abbrev = abbrev.get("default") or ""
            abbrev = str(abbrev or "")
            is_home = abbr_to_id.get(abbrev) == home_id if abbrev else False
            side = 0 if is_home else 1
            if ptype == "SO":
                has_so_block = True
                so_pair[side] += 1
                continue
            if ptype == "OT" or pnum >= 4:
                ot_pair[side] += 1
            elif pnum in (1, 2, 3):
                counts.setdefault(pnum, [0, 0])
                counts[pnum][side] += 1
            if (g.get("strength") or "") == "sh" and abbrev:
                shg_by_abbrev[abbrev] = shg_by_abbrev.get(abbrev, 0) + 1
            name = g.get("name") or {}
            goals_list.append({
                "time": g.get("timeInPeriod") or "",
                "score": f"{g.get('homeScore', 0)}:{g.get('awayScore', 0)}",
                "period": pnum,
                "team_id": abbr_to_id.get(abbrev, 0),
                "scorer": name.get("default") or "",
                "assistants": [
                    (a.get("name") or {}).get("default") or ""
                    for a in (g.get("assists") or [])
                ],
            })

    pd_land = land.get("periodDescriptor") or {}
    try:
        cur_pnum = int(pd_land.get("number") or 0)
    except (TypeError, ValueError):
        cur_pnum = 0
    has_ot = cur_pnum >= 4 or (pd_land.get("periodType") or "").upper() in ("OT", "SO")

    if has_so_block:
        penalties_pair = f"{so_pair[0]}:{so_pair[1]}"
    elif finish == "so":
        # итоговый счёт включает решающий буллит — считаем по разнице
        reg_h = sum(v[0] for v in counts.values())
        reg_a = sum(v[1] for v in counts.values())
        penalties_pair = (
            f"{max(score_home - reg_h - ot_pair[0], 0)}:"
            f"{max(score_away - reg_a - ot_pair[1], 0)}"
        )
    else:
        penalties_pair = None

    if status == "finished":
        upto = 3
    else:
        upto = min(cur_pnum, 3) if cur_pnum else 0

    def _pair_str(idx: int) -> str | None:
        if upto < idx:
            return None
        h, a = counts.get(idx, [0, 0])
        return f"{h}:{a}"

    periods = {
        "first": _pair_str(1),
        "second": _pair_str(2),
        "third": _pair_str(3),
        "overtime": f"{ot_pair[0]}:{ot_pair[1]}" if has_ot else None,
        "penalties": penalties_pair,
    }

    # --- штрафы из summary.penalties --------------------------------------
    penalties_list: list[dict] = []
    for block in ((land.get("summary") or {}).get("penalties")) or []:
        pdx = block.get("periodDescriptor") or {}
        try:
            pnum = int(pdx.get("number") or 0)
        except (TypeError, ValueError):
            pnum = 0
        for p in block.get("penalties") or []:
            player = p.get("committedByPlayer") or {}
            pname = " ".join(
                x for x in [
                    (player.get("firstName") or {}).get("default"),
                    (player.get("lastName") or {}).get("default"),
                ] if x
            )
            abbrev = p.get("teamAbbrev")
            if isinstance(abbrev, dict):
                abbrev = abbrev.get("default") or ""
            desc = str(p.get("descKey") or "")
            penalties_list.append({
                "time": p.get("timeInPeriod") or "",
                "period": pnum,
                "reason": _PENALTY_RU.get(desc, desc),
                "minutes": int(p.get("duration") or 0),
                "player": pname,
                "team_id": abbr_to_id.get(str(abbrev or ""), 0),
            })

    # --- командная статистика ---------------------------------------------
    h_abbrev = str(h_box.get("abbrev") or "")
    a_abbrev = str(a_box.get("abbrev") or "")

    def _avg_pct(skaters: list[dict]) -> float:
        vals = [
            float(p["faceoffWinningPctg"])
            for p in skaters
            if p.get("faceoffWinningPctg") is not None
        ]
        return sum(vals) / len(vals) if vals else 0.0

    rh = _avg_pct(_skaters(h_pb))
    ra = _avg_pct(_skaters(a_pb))
    if rh + ra > 0:
        faceoff_home = round(62 * rh / (rh + ra))
        faceoff_away = 62 - faceoff_home
    else:
        faceoff_home = faceoff_away = 31

    def _team_stats(pb: dict, box_side: dict, abbrev: str) -> dict:
        sk = _skaters(pb)
        return {
            "shots": int(box_side.get("sog") or 0),
            "goals_for": int(box_side.get("score") or 0),
            "ppg": sum(int(p.get("powerPlayGoals") or 0) for p in sk),
            "shg": shg_by_abbrev.get(abbrev, 0),
            "ppc": 0,
            "faceoffs_won": faceoff_home if abbrev == h_abbrev else faceoff_away,
            "pim": sum(int(p.get("pim") or 0) for p in sk),
            "puck_control_pct": 0,
            "distance_km": 0,
            "zone_entries": 0,
        }

    def _roster(pb: dict, abbrev: str) -> list[dict]:
        out: list[dict] = []
        for group, role in (
            ("forwards", "forward"),
            ("defense", "defensemen"),
            ("goalies", "goaltender"),
        ):
            for p in pb.get(group) or []:
                pid = p.get("playerId")
                image = None
                if season and abbrev and pid:
                    image = f"https://assets.nhle.com/mugs/nhl/{season}/{abbrev}/{pid}.png"
                out.append({
                    "number": p.get("sweaterNumber"),
                    "name": (p.get("name") or {}).get("default") or "",
                    "role": role,
                    "image": image,
                    "goals": int(p.get("goals") or 0),
                })
        return out

    # Хайлайты (обзор матча) — только у завершённых игр: ролик появляется
    # на nhl.com через несколько минут после финальной сирены.
    highlights: list[dict] = []
    if not live and status not in ("live", "break", "pre_game"):
        try:
            recap = await get_game_recap(a_abbrev, h_abbrev)
            if recap:
                highlights.append(recap)
        except Exception as e:
            logger.warning("NHL recap lookup failed (%s@%s): %s", a_abbrev, h_abbrev, e)

    return {
        "league": "NHL",
        "event_id": game_id,
        "match": {
            "home": home_name,
            "away": away_name,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "status": "Live" if status in ("live", "break") else "Finished",
            "score_home": score_home,
            "score_away": score_away,
            "finish": finish,
        },
        "periods": periods,
        "team_stats": {
            "home": _team_stats(h_pb, h_box, h_abbrev),
            "away": _team_stats(a_pb, a_box, a_abbrev),
        },
        "goals": goals_list,
        "penalties": penalties_list,
        "rosters": {
            "home": _roster(h_pb, h_abbrev),
            "away": _roster(a_pb, a_abbrev),
        },
        # у КХЛ обзор идёт m3u8 из API КХЛ, у НХЛ — ролики Brightcove с nhl.com
        "highlight": None,
        "highlights": highlights,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
