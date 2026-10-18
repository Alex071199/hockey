import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import Match
from app.api.broadcast import (
    fetch_hockey_line,
    find_live_entry,
    live_matches,
    match_snapshots,
    _fetch_player_source,
    _get_state,
)
from app.scraper.livetv import scrape_livetv_matches, _is_jastar
from app.scraper.mhl import fetch_kickoff, normalize_team, scrape_mhl_matches
from app.scraper.sportplustv import scrape_sportplustv_matches
from app.ws import manager

logger = logging.getLogger(__name__)

KHL_NAME_ALIASES: dict[str, str] = {
    "шанхай": "шанхайские драконы",
    "драконы": "шанхайские драконы",
    "динамо м": "динамо москва",
    "динамо мск": "динамо москва",
    "локомотив": "локомотив ярославль",
    "металлург": "металлург магнитогорск",
    "тратор": "трактор челябинск",
    "авангард": "авангард кемерово",
    "салават": "салават юлаев",
    "сибирь": "сибирь новосибирск",
    "адмирал": "адмирал владивосток",
    "амур": "амур хабаровск",
    "барыс": "барыс астана",
    "волга": "волга ульяновск",
    "торпедо": "торпедо нижний новгород",
    "химик": "химик новосибирск",
    "судэк": "судэк москва",
}


def _normalize_khl_name(name: str) -> str:
    low = name.lower().strip()
    return KHL_NAME_ALIASES.get(low, low)


def _mhl_name_match(a: str | None, b: str | None) -> bool:
    """True when two sources likely mean the same MHL team."""
    x, y = normalize_team(a).casefold(), normalize_team(b).casefold()
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) > len(y):
        x, y = y, x
    if len(x) < 5:
        return False
    # word-boundary prefix: "АКМ-Юниор" == "АКМ-Юниор Новомосковск",
    # but "Локо" != "Локо-76" and "Спутник Ал" != handled by aliases
    if y.startswith(x) and y[len(x)] == " ":
        return True
    # word-boundary suffix: livetv shortens club names that mhl.khl.ru
    # prefixes — "Спартак МАХ" == "МХК Спартак МАХ", "Молот" == "МХК Молот";
    # without this the LT_-строка создавалась дублем поверх MHL_-строки
    return y.endswith(x) and y[len(y) - len(x) - 1] == " "


def _mhl_pair_match(a_home, a_away, b_home, b_away) -> bool:
    return _mhl_name_match(a_home, b_home) and _mhl_name_match(a_away, b_away)


# Источники, которые sportplustv подставляла в МХЛ — теперь МХЛ только из livetv
SP_STREAM_SOURCES = {"sportplustv", "rutube", "youtube", "vk"}


def _keep_prime(new: list[dict], old: list[dict] | None) -> list[dict]:
    """Новый список источников от скрейпера + сохранённый PRIME (1win).

    Скрейперы пишут stream_urls целиком и не знают про PRIME — без этой
    склейки джоба sync_win_extra бесконечно переписывала бы свой источник,
    а на сайте его всё не было бы.
    """
    merged = list(new)
    known = {(s.get("source"), s.get("url")) for s in merged}
    for s in old or []:
        if s.get("source") == "prime" and (s.get("source"), s.get("url")) not in known:
            merged.append(s)
    return merged

scheduler = AsyncIOScheduler()
_mhl_upsert_lock = asyncio.Lock()


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id,
        "match_uid": m.match_uid,
        "league": m.league,
        "team_home": m.team_home,
        "team_away": m.team_away,
        "datetime_utc": m.datetime_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if m.datetime_utc else None,
        "status": m.status,
        "added_live": bool(m.added_live),
        "stream_urls": m.stream_urls or [],
        "home_score": m.home_score,
        "away_score": m.away_score,
        "current_period": m.current_period,
        "sp_match_id": m.sp_match_id,
    }


async def _broadcast_matches(ids: list[int]) -> None:
    if not ids:
        return
    unique_ids = list(set(ids))
    async with async_session() as db:
        result = await db.execute(select(Match).where(Match.id.in_(unique_ids)))
        matches = result.scalars().all()
    if matches:
        await manager.broadcast({
            "type": "matches_update",
            "data": [_match_to_dict(m) for m in matches],
        })


async def upsert_mhl_matches(matches: list[dict]) -> list[int]:
    """Merge mhl.khl.ru matches into the DB (uid = MHL_<game id>).

    Live/finished calendar items carry no kickoff time; it is resolved
    through the game page once, when the row is first created.
    Returns ids of changed rows.
    """
    if not matches:
        return []

    changed_ids: list[int] = []
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    async with _mhl_upsert_lock:
        async with async_session() as db:
            for md in matches:
                gid = md.get("mhl_game_id")
                dt = md.get("datetime_utc")
                if not gid and not dt:
                    continue

                status = md.get("status", "pre_game")
                uid = (
                    f"MHL_{gid}" if gid
                    else f"MHL_{dt.strftime('%m%d%H%M')}_{md['team_home'][:8]}"
                )

                res = await db.execute(select(Match).where(Match.match_uid == uid))
                existing = res.scalar_one_or_none()

                if existing is None and dt is None:
                    dt = await fetch_kickoff(md)
                    if not dt:
                        logger.warning(
                            "MHL: kickoff unknown for %s - %s, skipping",
                            md["team_home"], md["team_away"],
                        )
                        continue

                if existing is None:
                    near = await db.execute(
                        select(Match)
                        .where(
                            Match.league == "MHL",
                            Match.datetime_utc >= dt - timedelta(minutes=90),
                            Match.datetime_utc < dt + timedelta(minutes=90),
                        )
                        .order_by(Match.id)
                    )
                    for cand in near.scalars():
                        if _mhl_pair_match(
                            md["team_home"], md["team_away"],
                            cand.team_home, cand.team_away,
                        ):
                            existing = cand
                            break

                # календарь mhl.khl.ru иногда отстаёт от часов — старт уже был
                if status == "pre_game" and dt:
                    if dt <= now_utc:
                        status = "live" if dt > now_utc - timedelta(hours=4) else "finished"

                if existing:
                    dirty = False
                    if dt and existing.datetime_utc != dt:
                        existing.datetime_utc = dt
                        dirty = True
                    if existing.status != status:
                        existing.status = status
                        dirty = True
                    if md.get("home_score") is not None and existing.home_score != md["home_score"]:
                        existing.home_score = md["home_score"]
                        dirty = True
                    if md.get("away_score") is not None and existing.away_score != md["away_score"]:
                        existing.away_score = md["away_score"]
                        dirty = True
                    if md.get("current_period") and existing.current_period != md["current_period"]:
                        existing.current_period = md["current_period"]
                        dirty = True
                    if dirty:
                        changed_ids.append(existing.id)
                    continue

                new_match = Match(
                    match_uid=uid,
                    league="MHL",
                    team_home=md["team_home"],
                    team_away=md["team_away"],
                    datetime_utc=dt,
                    status=status,
                    added_live=(status == "live"),
                    stream_urls=md.get("stream_urls") or [],
                    home_score=md.get("home_score"),
                    away_score=md.get("away_score"),
                    current_period=md.get("current_period"),
                )
                db.add(new_match)
                await db.flush()
                changed_ids.append(new_match.id)
                logger.info(
                    "Added MHL match: %s - %s [%s] at %s",
                    md["team_home"], md["team_away"], status, dt,
                )

            await db.commit()

    return changed_ids


async def update_mhl_scores() -> None:
    """Fast MHL score/status refresh — only while MHL games are on."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with async_session() as db:
            res = await db.execute(
                select(Match.id)
                .where(
                    Match.league == "MHL",
                    or_(
                        Match.status == "live",
                        and_(
                            Match.status == "pre_game",
                            Match.datetime_utc >= now,
                            Match.datetime_utc <= now + timedelta(minutes=7),
                        ),
                    ),
                )
                .limit(1)
            )
            if res.scalar_one_or_none() is None:
                return
    except Exception as e:
        logger.warning("MHL live check failed: %s", e)
        return

    try:
        matches = await scrape_mhl_matches()
    except Exception as e:
        logger.warning("MHL live scrape failed: %s", e)
        return
    if not matches:
        return

    try:
        changed = await upsert_mhl_matches(matches)
    except Exception as e:
        logger.warning("MHL live upsert failed: %s", e)
        return
    if changed:
        await _broadcast_matches(changed)
        logger.info("MHL: updated %d matches", len(changed))


# --- НХЛ из линии 1win -------------------------------------------------------
# Трансляции НХЛ идут только через 1win, поэтому расписание этой лиги
# собираем из её линии: live/прематч + счёт и broadcast.url из WS-снапшотов.
def _is_regular_nhl(item: dict) -> bool:
    """Игры регулярного чемпионата НХЛ.

    Под турниром nhl в линии лежат и реплеи (category=replays), и
    киберспорт (турнир nhl-esportsbattle-*), и долгосрочные ставки вроде
    «Обладатель Кубка Стэнли» — их в расписание не берём.
    """
    tour = (item.get("tournament") or {}).get("slug") or ""
    cat = (item.get("category") or {}).get("slug") or ""
    if tour != "nhl" or cat == "replays":
        return False
    return bool(
        (item.get("homeTeam") or {}).get("name")
        and (item.get("awayTeam") or {}).get("name")
    )


_NICK_RE = re.compile(r"\([A-Za-z0-9]{2,}\)")


def _is_regular_nhl_row(home: str, away: str) -> bool:
    """Та же проверка, но по уже сохранённой строке расписания.

    Нужна для строк, чей 1win-id уже вышел из линии (реплей/киберспорт
    отыгрался и пропал) — их нельзя вычислить по текущей линии.
    """
    names = f"{home} {away}"
    if "(replays)" in names.lower():
        return False
    return _NICK_RE.search(names) is None


def _pair_key(home: str | None, away: str | None) -> tuple[str, str]:
    return ((home or "").casefold().strip(), (away or "").casefold().strip())


def _win_id_of(row: Match) -> int:
    """WIN-id строки 1win; у строк официального API (NHL_) id — не её."""
    uid = row.match_uid or ""
    if not uid.startswith("WIN_"):
        return -1
    try:
        return int(uid.split("_", 1)[1])
    except (ValueError, IndexError):
        return -1


def _find_nhl_twin(rows: list[Match], dt: datetime | None) -> Match | None:
    """Строка того же матча, если игра перевыпустилась в линии под новым
    WIN-id: та же пара команд и близкое время старта (±6 часов)."""
    if not dt:
        return None
    best: Match | None = None
    for r in rows:
        if not r.datetime_utc:
            continue
        if abs((r.datetime_utc - dt).total_seconds()) > 6 * 3600:
            continue
        if best is None or (bool(r.stream_urls), r.updated_at or datetime.min) > (
            bool(best.stream_urls),
            best.updated_at or datetime.min,
        ):
            best = r
    return best


# одиночные попытки дозапроса broadcast, когда WS в цикле не дал ссылки
_bc_fallback_at: dict[int, float] = {}


async def _win_stream(
    win_id: int, broadcast_url: str | None = None
) -> list[dict]:
    """Источник трансляции: HLS играем через свой прокси (свежая подпись),
    iframe-плееры (Twitch) отдаём как есть — фронт подставит свой parent.

    `broadcast_url=None` — взять из кэшированного состояния (_get_state),
    чтобы не долбить WS и плеер на каждом цикле джобы.
    """
    if broadcast_url:
        m3u8, embed, _status, _len, _prev = await _fetch_player_source(broadcast_url)
    else:
        st = await _get_state(win_id) or {}
        m3u8, embed = st.get("m3u8"), st.get("embed")
    if m3u8:
        base = (settings.PRIME_PUBLIC_URL or settings.PUBLIC_API_URL).rstrip("/")
        url = f"{base}/api/broadcast/{win_id}/stream.m3u8"
    elif embed:
        url = embed
    else:
        return []
    # iframe не всегда наш HLS: youtube/vk/rutube-embed — это не «прайм»,
    # иначе приложение поднимает его первым и висит на заблокированном плеере
    source = "prime"
    if "youtube" in url or "youtu.be" in url:
        source = "youtube"
    elif "rutube" in url:
        source = "rutube"
    elif "vk.com" in url or "vkvideo" in url:
        source = "vk"
    return [{"url": url, "quality": "auto", "source": source}]


def _win_status(item: dict, snap: dict) -> str:
    """Статус строки: авторитетен serviceV2 из линии, WS добивает «Закончен»."""
    if "Закончен" in (snap.get("status") or ""):
        return "finished"
    service = item.get("serviceV2")
    if service == "live":
        return "live"
    if service == "prematch":
        return "pre_game"
    if not service:
        return "live" if snap.get("broadcast") else "pre_game"
    return "finished"


def _win_period(snap: dict) -> str | None:
    """Период из статуса WS; до начала матча — None, чтобы не тащить
    служебные значения вида «Еще не началось» / «Created»."""
    ru = snap.get("status") or ""
    if "Закончен" in ru:
        return "Завершён"
    if "Перерыв" in ru or "Пауза" in ru:
        return "Перерыв"
    if "Овертайм" in ru:
        return "Овертайм"
    if "Буллит" in ru:
        return "Буллиты"
    if "Основное" in ru:
        played = len(snap.get("periods") or [])
        return f"{min(played + 1, 3)}-й период"
    return None


async def sync_win_nhl() -> None:
    """Матчи НХЛ в расписании: линия 1win + счёт и трансляция из WS."""
    try:
        line = await fetch_hockey_line()
    except Exception as e:
        logger.warning("1win line fetch failed: %s", e)
        return
    nhl = [i for i in line if _is_regular_nhl(i)]
    # реплеи/киберспорт/долгосрочные ставки под турниром nhl: если раньше
    # успели попасть в расписание — убираем
    rejected = [f"WIN_{i['id']}" for i in line if not _is_regular_nhl(i)]
    if not nhl:
        return

    ids = [i["id"] for i in nhl]
    try:
        snaps = await match_snapshots(ids)
    except Exception as e:
        logger.warning("1win snapshots failed: %s", e)
        snaps = {}

    changed_ids: list[int] = []
    fallback_budget = 1
    async with async_session() as db:
        # Мусор (реплеи/киберспорт) убираем двумя способами: по id из линии
        # (rejected) и по содержимому самой строки — id мог уже выйти из линии.
        nhl_rows = (
            (await db.execute(select(Match).where(Match.league == "NHL")))
            .scalars()
            .all()
        )
        junk_ids: set[int] = set()
        for row in nhl_rows:
            junk = row.match_uid in rejected or not _is_regular_nhl_row(
                row.team_home or "", row.team_away or ""
            )
            if junk:
                await db.delete(row)
                junk_ids.add(row.id)
                logger.info(
                    "NHL: dropped %s - %s (не регулярный чемпионат)",
                    row.team_home, row.team_away,
                )
        # пары команд -> строки: для поиска «того же матча» при перевыпуске id
        pair_index: dict[tuple[str, str], list[Match]] = {}
        for row in nhl_rows:
            if row.id in junk_ids:
                continue
            pair_index.setdefault(_pair_key(row.team_home, row.team_away), []).append(row)
        # flush: следующий SELECT (слияние дублей) не должен вернуть мусор
        await db.flush()

        for item in nhl:
            win_id = item["id"]
            snap = snaps.get(win_id) or {}
            status = _win_status(item, snap)
            uid = f"WIN_{win_id}"

            ts = item.get("startAt") or 0
            dt = (
                datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
                if ts
                else None
            )

            res = await db.execute(select(Match).where(Match.match_uid == uid))
            existing = res.scalar_one_or_none()
            home = (item.get("homeTeam") or {}).get("name", "")
            away = (item.get("awayTeam") or {}).get("name", "")

            if existing is None:
                # игра могла перевыпуститься в линии под новым WIN-id — тогда
                # обновляем старую строку, а не создаём вторую (будет дубль)
                twin = _find_nhl_twin(pair_index.get(_pair_key(home, away), []), dt)
                if twin is not None:
                    if (twin.match_uid or "").startswith("NHL_"):
                        # строку ведёт официальный API: uid не переименовываем,
                        # 1win дописывает в неё только стрим
                        logger.info(
                            "NHL: %s - %s уже в расписании от API (%s), "
                            "1win дописывает стрим",
                            twin.team_home, twin.team_away, twin.match_uid,
                        )
                        existing = twin
                    else:
                        logger.info(
                            "NHL: %s - %s перевыпущен в линии: %s -> %s, сливаем",
                            twin.team_home, twin.team_away, twin.match_uid, uid,
                        )
                        twin.match_uid = uid
                        existing = twin

            # у строки API авторитетны её uid/счёт/статус — сюда дописываем
            # только трансляцию из 1win
            api_row = existing is not None and (
                existing.match_uid or ""
            ).startswith("NHL_")

            home_score = snap.get("home_score")
            away_score = snap.get("away_score")
            period = _win_period(snap)
            # Стрим ставим только когда WS подтвердил broadcast.url и плеер
            # отдал источник — иначе карточка ведёт в пустой плеер.
            stream: list[dict] | None = None
            if status == "live":
                if snap.get("broadcast"):
                    stream = await _win_stream(win_id, snap["broadcast"])
                elif (
                    fallback_budget > 0
                    and not (existing and existing.stream_urls)
                    and time.time() - _bc_fallback_at.get(win_id, 0.0) > 300.0
                ):
                    # WS в этом цикле не дал broadcast — одна одиночная попытка
                    # (кэш _get_state не даёт долбить плеер чаще5 минут)
                    _bc_fallback_at[win_id] = time.time()
                    fallback_budget -= 1
                    stream = await _win_stream(win_id)

            if existing is None:
                new_match = Match(
                    match_uid=uid,
                    league="NHL",
                    team_home=home,
                    team_away=away,
                    datetime_utc=dt,
                    status=status,
                    added_live=(status == "live"),
                    stream_urls=stream or [],
                    home_score=home_score,
                    away_score=away_score,
                    current_period=period,
                )
                db.add(new_match)
                await db.flush()
                changed_ids.append(new_match.id)
                pair_index.setdefault(_pair_key(home, away), []).append(new_match)
                logger.info(
                    "NHL: added %s - %s [%s]",
                    new_match.team_home, new_match.team_away, status,
                )
                continue

            dirty = False
            if not api_row and existing.status != status:
                existing.status = status
                dirty = True
            if not api_row and dt and existing.datetime_utc != dt:
                existing.datetime_utc = dt
                dirty = True
            if stream and existing.stream_urls != stream:
                existing.stream_urls = stream
                dirty = True
            # миграция: раньше источник назывался "1win", теперь "prime"
            if any(s.get("source") == "1win" for s in (existing.stream_urls or [])):
                existing.stream_urls = [
                    {**s, "source": "prime"} if s.get("source") == "1win" else s
                    for s in existing.stream_urls
                ]
                dirty = True
            if not api_row and home_score is not None and existing.home_score != home_score:
                existing.home_score = home_score
                dirty = True
            if not api_row and away_score is not None and existing.away_score != away_score:
                existing.away_score = away_score
                dirty = True
            if not api_row and period and existing.current_period != period:
                existing.current_period = period
                dirty = True
            if dirty:
                changed_ids.append(existing.id)

        # дубли, накопленные до фикса (одна игра под разными WIN-id)
        await _merge_nhl_duplicates(db, set(ids), changed_ids)

        await db.commit()

    if changed_ids:
        await _broadcast_matches(changed_ids)
        logger.info("NHL: updated %d matches", len(set(changed_ids)))


async def _merge_nhl_duplicates(
    db: AsyncSession, line_ids: set[int], changed_ids: list[int]
) -> int:
    """Сливает накопившиеся дубли строк НХЛ одной игры.

    Одна игра могла быть в линии под разными WIN-id (переиздание карточки):
    на один id пришла строка со стримом, на другой — без. Канон — строка
    официального API (NHL_), иначе строка из текущей линии (она продолжает
    получать обновления), её и оставляем.
    """
    rows = (
        (await db.execute(select(Match).where(Match.league == "NHL")))
        .scalars()
        .all()
    )
    groups: dict[tuple[str, str], list[Match]] = {}
    for r in rows:
        if not r.datetime_utc:
            continue
        groups.setdefault(_pair_key(r.team_home, r.team_away), []).append(r)

    merged = 0
    for arr in groups.values():
        if len(arr) < 2:
            continue
        arr.sort(key=lambda r: r.datetime_utc)
        cluster = [arr[0]]
        for r in arr[1:]:
            if (r.datetime_utc - cluster[-1].datetime_utc) <= timedelta(hours=6):
                cluster.append(r)
                continue
            merged += await _merge_nhl_cluster(db, cluster, line_ids, changed_ids)
            cluster = [r]
        merged += await _merge_nhl_cluster(db, cluster, line_ids, changed_ids)
    return merged


async def _merge_nhl_cluster(
    db: AsyncSession, arr: list[Match], line_ids: set[int], changed_ids: list[int]
) -> int:
    if len(arr) < 2:
        return 0

    def rank(r: Match) -> tuple:
        return (
            # официальный API главнее строки из линии — счёт/статус в ней
            # авторитетны, стримы с дубля всё равно сольются выше
            (r.match_uid or "").startswith("NHL_"),
            _win_id_of(r) in line_ids,
            bool(r.stream_urls),
            r.updated_at or datetime.min,
        )

    arr.sort(key=rank, reverse=True)
    main, dups = arr[0], arr[1:]
    main_win = _win_id_of(main)
    merged = 0
    for d in dups:
        d_win = _win_id_of(d)
        have = {s.get("url") for s in (main.stream_urls or [])}
        fresh: list[dict] = []
        for s in d.stream_urls or []:
            url = s.get("url") or ""
            # HLS-адрес привязан к WIN-id старой карточки — переписываем
            # на id канонической строки, иначе прокси его не разрешит
            if d_win >= 0 and main_win >= 0 and d_win != main_win:
                url = url.replace(
                    f"/api/broadcast/{d_win}/stream.m3u8",
                    f"/api/broadcast/{main_win}/stream.m3u8",
                )
            if url not in have:
                have.add(url)
                fresh.append({**s, "url": url})
        if fresh:
            main.stream_urls = list(main.stream_urls or []) + fresh
            if main.id not in changed_ids:
                changed_ids.append(main.id)
        logger.info(
            "NHL: merged dup %s -> %s (%s - %s)",
            d.match_uid, main.match_uid, d.team_home, d.team_away,
        )
        await db.delete(d)
        merged += 1
    return merged


# --- PRIME как дополнительный источник для КХЛ/МХЛ/ВХЛ ------------------------
# Расписание этих лиг наше (лайвтв/спортплюс), а трансляция 1win дописывается
# в stream_urls отдельной записью source=prime — просто ещё один источник.
EXTRA_PRIME_LEAGUES = ("KHL", "MHL", "VHL")


async def sync_win_extra() -> None:
    """Дописывает PRIME к live-матчам КХЛ/МХЛ/ВХЛ, если 1win их показывает."""
    # дешёвая проверка: без live-строк этих лиг сеть не трогаем
    try:
        async with async_session() as db:
            res = await db.execute(
                select(Match.id)
                .where(
                    Match.league.in_(EXTRA_PRIME_LEAGUES),
                    Match.status == "live",
                )
                .limit(1)
            )
            if res.scalar_one_or_none() is None:
                return
    except Exception as e:
        logger.warning("PRIME live check failed: %s", e)
        return

    try:
        win_live = await live_matches()
    except Exception as e:
        logger.warning("1win live fetch failed: %s", e)
        return
    if not win_live:
        return

    changed_ids: list[int] = []
    async with async_session() as db:
        rows = (
            (
                await db.execute(
                    select(Match).where(
                        Match.league.in_(EXTRA_PRIME_LEAGUES),
                        Match.status == "live",
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            date = row.datetime_utc.strftime("%Y-%m-%d") if row.datetime_utc else None
            entry = find_live_entry(row.team_home, row.team_away, date, win_live)
            if not entry:
                continue
            stream = await _win_stream(entry["id"])
            if not stream:
                continue

            existing = list(row.stream_urls or [])
            prime_urls = {
                s.get("url") for s in existing if s.get("source") == "prime"
            }
            new_urls = {s["url"] for s in stream}
            if prime_urls == new_urls:
                continue
            # убираем устаревший PRIME, остальные источники не трогаем;
            # известность проверяем по (source, url): embed 1win часто
            # совпадает с URL livetv_youtube, но это разные источники
            merged = [
                s
                for s in existing
                if not (s.get("source") == "prime" and s.get("url") not in new_urls)
            ]
            known = {(s.get("source"), s.get("url")) for s in merged}
            merged.extend(
                s for s in stream if (s.get("source"), s.get("url")) not in known
            )
            row.stream_urls = merged
            changed_ids.append(row.id)
            logger.info(
                "PRIME: %s - %s <- %s [row id=%s]",
                row.team_home, row.team_away, stream[0]["url"], row.id,
            )

        await db.commit()

    if changed_ids:
        await _broadcast_matches(changed_ids)


async def dedupe_sp_matches() -> int:
    """Collapse duplicate sportplustv rows (VHL/MHL).

    Rows with the same (fuzzy-matched) team pair whose kickoff times are
    within 90 minutes of each other are the same game — real doubleheaders
    are at least a full game apart. The row with a sportplustv id (streams)
    wins, then finished rows, then rows carrying a non-zero score.
    """

    async with _mhl_upsert_lock:
        async with async_session() as db:
            rows = (
                (
                    await db.execute(
                        select(Match).where(Match.league.in_(["MHL", "VHL"]))
                    )
                )
                .scalars()
                .all()
            )
            rows.sort(key=lambda m: m.datetime_utc or datetime.min)

            clusters: list[list[Match]] = []
            for m in rows:
                target: list[Match] | None = None
                for cl in clusters:
                    ref = cl[-1]
                    if (
                        m.datetime_utc is not None
                        and ref.datetime_utc is not None
                        and abs(m.datetime_utc - ref.datetime_utc) > timedelta(minutes=90)
                    ):
                        continue
                    if _mhl_pair_match(
                        m.team_home, m.team_away, ref.team_home, ref.team_away
                    ):
                        target = cl
                        break
                if target is None:
                    clusters.append([m])
                else:
                    target.append(m)

            removed = 0
            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                finished_scores = {
                    (m.home_score, m.away_score)
                    for m in cluster
                    if m.status == "finished"
                    and m.home_score is not None
                    and m.away_score is not None
                    and (m.home_score or m.away_score)
                }
                if len(finished_scores) > 1:
                    continue
                best = max(
                    cluster,
                    key=lambda m: (
                        m.sp_match_id is not None,
                        m.status == "finished",
                        bool(m.home_score or m.away_score),
                        m.home_score is not None,
                        len(m.current_period or ""),
                        m.updated_at or datetime.min,
                        -(m.id or 0),
                    ),
                )
                for m in cluster:
                    if m.id != best.id:
                        # стримы/счёт удаляемой строки переливаем в выжившую —
                        # иначе дедуп молча терял livetv_-ссылки матча
                        have = {s.get("url") for s in (best.stream_urls or [])}
                        fresh = [
                            s for s in (m.stream_urls or [])
                            if (s.get("url") or "") not in have
                        ]
                        if fresh:
                            best.stream_urls = list(best.stream_urls or []) + fresh
                        if best.home_score is None and m.home_score is not None:
                            best.home_score = m.home_score
                        if best.away_score is None and m.away_score is not None:
                            best.away_score = m.away_score
                        if not best.current_period and m.current_period:
                            best.current_period = m.current_period
                        await db.delete(m)
                        removed += 1
            if removed:
                await db.commit()
                logger.info("MHL: removed %d duplicate rows", removed)
            return removed


async def strip_mhl_sp_streams() -> None:
    """МХЛ-стримы теперь только из livetv — убираем остатки sportplustv."""
    try:
        async with async_session() as db:
            rows = (
                (await db.execute(select(Match).where(Match.league == "MHL")))
                .scalars()
                .all()
            )
            changed = 0
            for m in rows:
                cur = m.stream_urls or []
                kept = [s for s in cur if s.get("source") not in SP_STREAM_SOURCES]
                if len(kept) != len(cur):
                    m.stream_urls = kept
                    changed += 1
            if changed:
                await db.commit()
                logger.info("MHL: stripped sportplustv streams from %d matches", changed)
    except Exception as e:
        logger.warning("MHL stream strip failed: %s", e)


async def seed_mhl_schedule() -> None:
    """Load the distant MHL calendar (beyond the ~10 days of page 1)."""
    try:
        await dedupe_sp_matches()
    except Exception as e:
        logger.warning("MHL dedupe failed: %s", e)

    known: set[str] = set()
    try:
        async with async_session() as db:
            res = await db.execute(select(Match.match_uid).where(Match.league == "MHL"))
            known = set(res.scalars().all())
    except Exception as e:
        logger.warning("MHL seed: db read failed: %s", e)

    try:
        matches = await scrape_mhl_matches(future_pages=20, known_uids=known)
    except Exception as e:
        logger.warning("MHL seed scrape failed: %s", e)
        return
    if not matches:
        return

    try:
        changed = await upsert_mhl_matches(matches)
    except Exception as e:
        logger.warning("MHL seed upsert failed: %s", e)
        return
    if changed:
        await _broadcast_matches(changed)
        logger.info("MHL: seeded %d matches", len(changed))


async def cleanup_jastar_rows() -> int:
    """Jastar Hokei Ligasy (казахская лига) не входит в МХЛ.

    livetv раньше заводил её матчи как LT_-строки МХЛ — удаляем такие
    строки из расписания (идемпотентно, вызывается при старте).
    """
    async with async_session() as db:
        result = await db.execute(select(Match).where(Match.match_uid.like("LT_%")))
        rows = result.scalars().all()
        bad_ids = [
            m.id for m in rows
            if _is_jastar(m.league, "", m.team_home, m.team_away)
        ]
        if bad_ids:
            await db.execute(delete(Match).where(Match.id.in_(bad_ids)))
            await db.commit()
            logger.info("Jastar cleanup: removed %d non-MHL rows", len(bad_ids))
        return len(bad_ids)


# время (epoch) последнего полного скрейпа — чтобы принудительная проверка
# не запускала его дважды подряд
_last_scrape_at: float = 0.0


async def scrape_and_update() -> None:
    global _last_scrape_at
    _last_scrape_at = time.time()
    logger.info("Starting scheduled scrape...")

    livetv_matches = []
    try:
        livetv_matches = await scrape_livetv_matches()
        logger.info("LiveTV: found %d matches (KHL)", len(livetv_matches))
    except Exception as e:
        logger.warning("LiveTV scrape failed: %s", e)

    sportplustv_matches = []
    try:
        sportplustv_matches = await scrape_sportplustv_matches()
        logger.info("SportPlusTV: found %d matches (VHL)", len(sportplustv_matches))
    except Exception as e:
        logger.warning("SportPlusTV scrape failed: %s", e)

    mhl_matches: list[dict] = []
    try:
        mhl_matches = await scrape_mhl_matches()
        logger.info("MHL: found %d matches (mhl.khl.ru)", len(mhl_matches))
    except Exception as e:
        logger.warning("MHL scrape failed: %s", e)

    all_scraped = livetv_matches + sportplustv_matches
    scraped_uids = {m.get("livetv_id") or m.get("team_home", "")[:10] for m in all_scraped}

    changed_ids: list[int] = []

    async with async_session() as db:
        for match_data in all_scraped:
            if match_data.get("livetv_id"):
                uid = f"LT_{match_data['livetv_id']}"
            elif match_data.get("sp_match_id"):
                uid = f"SP_{match_data.get('league', 'XX')}_{match_data['sp_match_id']}"
            else:
                league = match_data.get("league", "XX")
                home = match_data.get("team_home", "")[:10]
                dt = match_data.get("datetime_utc")
                if dt:
                    uid = f"SP_{league}_{dt.strftime('%m%d%H%M')}_{home}"
                else:
                    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                    h = int(match_data.get("hour", 0))
                    mi = int(match_data.get("minute", 0))
                    uid = f"SP_{league}_{now_utc.strftime('%m%d')}{h:02d}{mi:02d}_{home}"

            sp_id = match_data.get("sp_match_id")
            if sp_id:
                result = await db.execute(
                    select(Match).where(
                        or_(
                            Match.match_uid == uid,
                            and_(
                                Match.league == match_data.get("league", "XX"),
                                Match.sp_match_id == sp_id,
                            ),
                        )
                    )
                )
            else:
                result = await db.execute(
                    select(Match).where(Match.match_uid == uid)
                )
            existing = result.scalars().first()

            stream_urls = match_data.get("stream_urls", [])
            # МХЛ-страницы livetv привязываем к строкам календаря mhl.khl.ru,
            # иначе по uid LT_ создались бы дубли.
            is_livetv_mhl = match_data.get("league") == "MHL" and match_data.get("livetv_id")
            if existing is None and is_livetv_mhl:
                dt_md = match_data.get("datetime_utc")
                if dt_md:
                    near = await db.execute(
                        select(Match)
                        .where(
                            Match.league == "MHL",
                            Match.datetime_utc >= dt_md - timedelta(minutes=90),
                            Match.datetime_utc < dt_md + timedelta(minutes=90),
                        )
                        .order_by(Match.id)
                    )
                    for cand in near.scalars():
                        if _mhl_pair_match(
                            match_data["team_home"], match_data["team_away"],
                            cand.team_home, cand.team_away,
                        ):
                            existing = cand
                            break

            if existing:
                if is_livetv_mhl:
                    # МХЛ: стримы теперь только из livetv, старые ссылки
                    # sportplustv подчищаем
                    if stream_urls:
                        existing.stream_urls = _keep_prime(
                            stream_urls, existing.stream_urls
                        )
                    else:
                        cur = existing.stream_urls or []
                        kept = [s for s in cur if s.get("source") not in SP_STREAM_SOURCES]
                        if len(kept) != len(cur):
                            existing.stream_urls = kept
                elif stream_urls:
                    existing.stream_urls = _keep_prime(
                        stream_urls, existing.stream_urls
                    )
                if match_data.get("status") == "live":
                    existing.status = "live"
                # время МХЛ-строки из mhl.khl.ru авторитетнее: у livetv
                # эвристика «сегодня» может ошибиться днём
                if match_data.get("datetime_utc") and (
                    not is_livetv_mhl or existing.match_uid == uid
                ):
                    existing.datetime_utc = match_data["datetime_utc"]
                if match_data.get("home_score") is not None:
                    existing.home_score = match_data["home_score"]
                if match_data.get("away_score") is not None:
                    existing.away_score = match_data["away_score"]
                if match_data.get("sp_match_id") is not None:
                    existing.sp_match_id = match_data["sp_match_id"]
                changed_ids.append(existing.id)
            else:
                dt_utc = match_data.get("datetime_utc")
                status = match_data.get("status", "pre_game")

                if not dt_utc:
                    # onhockey schedule times are already UTC (verified
                    # against livetv KHL kickoff times) — no shift needed.
                    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                    today = now_utc.date()
                    h = int(match_data.get("hour", 0))
                    mi = int(match_data.get("minute", 0))
                    dt_utc = datetime.combine(today, datetime.min.time()).replace(hour=h, minute=mi)
                    if dt_utc > now_utc + timedelta(days=2):
                        dt_utc -= timedelta(days=1)
                    if dt_utc + timedelta(hours=3) < now_utc:
                        status = "finished"
                    elif dt_utc <= now_utc <= dt_utc + timedelta(hours=3):
                        status = "live"

                new_match = Match(
                    match_uid=uid,
                    league=match_data["league"],
                    team_home=match_data["team_home"],
                    team_away=match_data["team_away"],
                    datetime_utc=dt_utc,
                    status=status,
                    added_live=(status == "live"),
                    stream_urls=stream_urls,
                    home_score=match_data.get("home_score"),
                    away_score=match_data.get("away_score"),
                    sp_match_id=match_data.get("sp_match_id"),
                )
                if status == "pre_game" and dt_utc:
                    now_gate = datetime.now(timezone.utc).replace(tzinfo=None)
                    if dt_utc - now_gate > timedelta(minutes=5):
                        logger.info(
                            "Skipping early pre_game: %s - %s [%s] at %s",
                            match_data["team_home"], match_data["team_away"],
                            match_data.get("league"), dt_utc,
                        )
                        continue
                db.add(new_match)
                await db.flush()
                changed_ids.append(new_match.id)
                logger.info("Added match: %s - %s [%s]", match_data["team_home"], match_data["team_away"], match_data["league"])

        result = await db.execute(
            select(Match).where(Match.status.in_(["pre_game", "live"]))
        )
        active = result.scalars().all()
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        for m in active:
            if not m.datetime_utc:
                continue
            if m.datetime_utc + timedelta(hours=3) < now_utc and m.status != "finished":
                m.status = "finished"
                changed_ids.append(m.id)
            elif m.status == "pre_game" and m.datetime_utc <= now_utc:
                m.status = "live"
                changed_ids.append(m.id)

        await db.commit()

    if mhl_matches:
        try:
            changed_ids.extend(await upsert_mhl_matches(mhl_matches))
        except Exception as e:
            logger.warning("MHL upsert failed: %s", e)

    await _broadcast_matches(changed_ids)

    try:
        await dedupe_sp_matches()
    except Exception as e:
        logger.warning("MHL dedupe failed: %s", e)

    await strip_mhl_sp_streams()

    logger.info("Scrape complete: %d matches total", len(all_scraped))
    await warmup_stream_cache()


# Окно принудительной проверки: от 5 минут до начала матча
# до 20 минут после — стримы часто появляются на источниках уже после
# начального свистка, а регулярный скрейп идёт раз в 5 минут.
FORCE_WINDOW_BEFORE = timedelta(minutes=5)
FORCE_WINDOW_AFTER = timedelta(minutes=20)


async def warm_prime_states() -> None:
    """Держит state 1win-источников (PRIME) тёплым.

    Без прогрева первый зритель ждал, пока бэк прогреет WS + HTML плеера,
    и первые секунды трансляции заикались.
    """
    try:
        async with async_session() as db:
            res = await db.execute(select(Match).where(Match.status == "live"))
            matches = res.scalars().all()
    except Exception as e:
        logger.warning("PRIME warmup: db failed: %s", e)
        return

    win_ids: list[int] = []
    for m in matches:
        for s in m.stream_urls or []:
            if s.get("source") != "prime":
                continue
            mt = re.search(r"/api/broadcast/(\d+)/stream\.m3u8", s.get("url") or "")
            if mt:
                win_ids.append(int(mt.group(1)))

    for win_id in dict.fromkeys(win_ids):
        try:
            await _get_state(win_id)
        except Exception as e:
            logger.warning("PRIME warmup %s failed: %s", win_id, e)


async def refresh_live_stream_urls() -> None:
    """Подписанные sportplustv-ссылки (VHL, sportvideodata.com) протухают
    за считанные минуты — обновляем detail live-матчей каждые 60 секунд,
    иначе веб и приложение получают 404."""
    from app.scraper.sportplustv import _fetch_match_detail

    async with async_session() as db:
        res = await db.execute(
            select(Match.id, Match.sp_match_id, Match.stream_urls)
            .where(Match.status == "live", Match.sp_match_id.is_not(None))
        )
        rows = res.all()
    if not rows:
        return

    sem = asyncio.Semaphore(4)

    async def _fetch(match_id: int, sp_id: int):
        async with sem:
            try:
                return match_id, await _fetch_match_detail(sp_id)
            except Exception as e:
                logger.warning("SportPlusTV refresh %s failed: %s", sp_id, e)
                return match_id, None

    results = await asyncio.gather(
        *(_fetch(r.id, r.sp_match_id) for r in rows)
    )

    updates: list[tuple[int, list[dict], int | None, int | None]] = []
    for row, detail in results:
        if not detail or not detail.get("streams"):
            continue
        kept = [
            s for s in (row.stream_urls or [])
            if s.get("source") not in SP_STREAM_SOURCES
        ]
        updates.append((
            row.id,
            list(detail["streams"]) + kept,
            detail.get("home_score"),
            detail.get("away_score"),
        ))
    if not updates:
        return

    async with async_session() as db:
        for mid, urls, hs, aws in updates:
            m = await db.get(Match, mid)
            if not m:
                continue
            m.stream_urls = urls
            if hs is not None:
                m.home_score = hs
            if aws is not None:
                m.away_score = aws
        await db.commit()
    logger.info("SportPlusTV refresh: updated %d live match(es)", len(updates))


async def force_upcoming_sources() -> None:
    """Если матч скоро начаться/уже начался, а источников нет — скрейп немедленно."""
    if time.time() - _last_scrape_at < 45:
        return  # свежий скрейп уже был — не дёргаем источники повторно
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as db:
        res = await db.execute(
            select(Match).where(Match.status.in_(["pre_game", "live"]))
        )
        matches = res.scalars().all()
    pending = [
        m
        for m in matches
        if m.datetime_utc
        and now - FORCE_WINDOW_AFTER <= m.datetime_utc <= now + FORCE_WINDOW_BEFORE
        and not (m.stream_urls or [])
    ]
    if not pending:
        return
    logger.info(
        "Forced source check: %d match(es) without sources near start: %s",
        len(pending),
        ", ".join(f"{m.team_home} - {m.team_away}" for m in pending),
    )
    await scrape_and_update()


async def warmup_stream_cache() -> None:
    """Pre-resolve livetv player pages in the background, so that opening
    a stream is served from cache instead of cold-fetching the whole
    iframe chain (webplayer -> abisnews -> player)."""
    try:
        from app.api.proxy import _resolve_livetv_player
    except Exception as e:
        logger.warning("Stream warmup import failed: %s", e)
        return

    async with async_session() as db:
        result = await db.execute(select(Match).where(Match.status == "live"))
        matches = result.scalars().all()

    urls: list[str] = []
    for m in matches:
        for s in (m.stream_urls or []):
            url = s.get("url", "")
            if "livetv903.me" in url or "livetv.sx" in url:
                urls.append(url)
    urls = list(dict.fromkeys(urls))
    if not urls:
        return

    sem = asyncio.Semaphore(4)

    async def _warm(url: str) -> None:
        async with sem:
            try:
                await _resolve_livetv_player(url)
            except Exception as e:
                logger.warning("Stream warmup failed for %s: %s", url[:80], e)

    await asyncio.gather(*(_warm(u) for u in urls))
    logger.info("Stream cache warmup done: %d livetv players", len(urls))


async def cleanup_old_matches() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    nhl_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with async_session() as db:
        await db.execute(
            delete(Match).where(
                Match.datetime_utc < cutoff,
                Match.status.in_(["pre_game", "live"]),
            )
        )
        # НХЛ из 1win плодит реплеи — держим только последнюю неделю
        await db.execute(
            delete(Match).where(
                Match.league == "NHL",
                Match.status == "finished",
                Match.datetime_utc < nhl_cutoff,
            )
        )
        from app.models import Reminder

        # reminders for matches that already passed (or were never sent)
        await db.execute(
            delete(Reminder).where(
                Reminder.datetime_utc < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
            )
        )
        await db.commit()
    logger.info("Cleaned up old pre_game/live matches")


async def sync_khl_start_times() -> None:
    """Sync KHL match start times with official API for upcoming matches (within 72h)."""
    try:
        from app import khl_api
    except Exception as e:
        logger.warning("KHL API import failed for start times: %s", e)
        return

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=72)

    all_events: list[dict] = []
    for i in range(3):
        date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            events = await khl_api.get_events_for_date(date_str)
            if events:
                all_events.extend(events)
        except Exception:
            pass

    if not all_events:
        return

    changed_ids: list[int] = []

    async with async_session() as db:
        result = await db.execute(
            select(Match).where(
                Match.league == "KHL",
                Match.datetime_utc >= now - timedelta(hours=1),
                Match.datetime_utc <= cutoff,
            )
        )
        matches = result.scalars().all()

        for m in matches:
            if not m.datetime_utc:
                continue
            event = khl_api._find_event(all_events, m.team_home, m.team_away)
            if not event:
                continue
            ts = event.get("start_at", 0)
            if isinstance(ts, (int, float)) and ts > 1e12:
                ts = ts // 1000
            if not ts:
                continue
            api_dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            diff = abs((api_dt - m.datetime_utc).total_seconds())
            if diff > 300:
                m.datetime_utc = api_dt
                changed_ids.append(m.id)

        if changed_ids:
            await db.commit()

    if changed_ids:
        async with async_session() as db:
            result = await db.execute(select(Match).where(Match.id.in_(changed_ids)))
            updated = result.scalars().all()
        await manager.broadcast({
            "type": "matches_update",
            "data": [_match_to_dict(m) for m in updated],
        })
        logger.info("Synced KHL start times for %d matches", len(changed_ids))

    await sync_reminder_start_times(all_events)


async def sync_reminder_start_times(all_events: list[dict]) -> None:
    """Fix stored reminder kickoff times from the official KHL API (72h window)."""
    from app import khl_api
    from app.models import Reminder

    if not all_events:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    changed = 0

    async with async_session() as db:
        result = await db.execute(
            select(Reminder).where(
                Reminder.datetime_utc >= now - timedelta(hours=2),
                Reminder.datetime_utc <= now + timedelta(hours=72),
                Reminder.soon_sent == False,  # noqa: E712
            )
        )
        reminders = result.scalars().all()
        for r in reminders:
            if not r.datetime_utc:
                continue
            event = khl_api._find_event(all_events, r.team_home, r.team_away)
            if not event:
                continue
            ts = event.get("start_at", 0)
            if isinstance(ts, (int, float)) and ts > 1e12:
                ts = ts // 1000
            if not ts:
                continue
            api_dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            if abs((api_dt - r.datetime_utc).total_seconds()) > 300:
                r.datetime_utc = api_dt
                changed += 1

        if changed:
            await db.commit()

    if changed:
        logger.info("Synced KHL start times for %d reminders", changed)


async def update_khl_scores() -> None:
    """Update live scores for KHL matches from the official KHL API."""
    try:
        from app import khl_api
    except Exception as e:
        logger.warning("KHL API import failed: %s", e)
        return

    now = datetime.now(timezone.utc)
    all_events: list[dict] = []
    for i in range(2):
        date_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            # Живые обновления: короткий TTL, иначе период/статус отстаёт.
            events = await khl_api.get_events_for_date(date_str, max_age=khl_api.EVENTS_LIVE_TTL)
            if events:
                all_events.extend(events)
        except Exception:
            pass

    if not all_events:
        logger.info("KHL update: no events found")
        return

    changed_ids: list[int] = []

    async with async_session() as db:
        result = await db.execute(
            select(Match).where(
                Match.league == "KHL",
                Match.status.in_(["live", "pre_game", "finished"]),
                Match.datetime_utc >= now - timedelta(days=2),
            )
        )
        matches = result.scalars().all()

        for m in matches:
            event = khl_api._find_event(all_events, m.team_home, m.team_away)
            if not event:
                logger.info("KHL update: no event for %s - %s (events=%d)", m.team_home, m.team_away, len(all_events))
                continue

            score = khl_api._parse_score_str(event.get("score"))
            game_state = event.get("game_state_key", "")

            break_states = {"halftime", "break", "rest", "timeout", "paused"}

            if game_state == "finished" or game_state in break_states:
                if game_state in break_states:
                    new_status = "break"
                    new_period = "Перерыв"
                else:
                    new_status = "finished"
                    new_period = "Завершён"
                if m.status != new_status:
                    m.status = new_status
                    changed_ids.append(m.id)
                if m.current_period != new_period:
                    m.current_period = new_period
                    changed_ids.append(m.id)
            elif game_state in ("live", "in_progress"):
                if m.status != "live":
                    m.status = "live"
                    changed_ids.append(m.id)

            if score and (m.home_score != score[0] or m.away_score != score[1]):
                m.home_score = score[0]
                m.away_score = score[1]
                changed_ids.append(m.id)

            period_val = event.get("period")
            if period_val is not None and game_state not in break_states:
                period_map = {-1: "Завершён", 0: "1-й период", 1: "1-й период", 2: "2-й период",
                              3: "3-й период", 4: "Овертайм", 5: "Буллиты", 10: "Перерыв"}
                new_period = period_map.get(period_val, str(period_val))
                if m.current_period != new_period:
                    m.current_period = new_period
                    changed_ids.append(m.id)
            elif game_state in ("live", "in_progress") and period_val is None:
                if m.current_period != "live":
                    m.current_period = "live"
                    changed_ids.append(m.id)

        if changed_ids:
            await db.commit()

    if changed_ids:
        unique_ids = list(set(changed_ids))
        async with async_session() as db:
            result = await db.execute(select(Match).where(Match.id.in_(unique_ids)))
            updated = result.scalars().all()
        await manager.broadcast({
            "type": "matches_update",
            "data": [_match_to_dict(m) for m in updated],
        })
        logger.info("Updated KHL scores for %d matches", len(unique_ids))


async def warm_khl_calendar() -> None:
    """Fetch the full KHL season calendar in the background (once per TTL)."""
    try:
        from app import khl_api
    except Exception as e:
        logger.warning("KHL calendar warm: import failed: %s", e)
        return
    if khl_api.cached_calendar_events() is not None:
        return
    if khl_api.start_calendar_build():
        logger.info("KHL calendar: background build started")


async def sync_nhl_schedule() -> None:
    """Расписание НХЛ из официального API: игра найдена — сохранена в БД.

    Окно -1..+7 дней по UTC: score фильтрует игры по местной дате игры,
    поэтому вчерашний день ловит игры, стартующие сегодня после полуночи UTC.
    Строки с uid NHL_<game id>; существующая строка той же пары (1win)
    переименовывается, а не дублируется — её стримы сохраняются.
    Счёт/период/статус строки пишет update_nhl_scores (каждые 30 секунд).
    """
    try:
        from app import nhl_api
    except Exception as e:
        logger.warning("NHL API import failed: %s", e)
        return
    try:
        games = await nhl_api.get_games_window(
            days_back=1, days_fwd=7, max_age=nhl_api.SCORE_TTL
        )
    except Exception as e:
        logger.warning("NHL schedule fetch failed: %s", e)
        return
    if not games:
        return

    changed_ids: list[int] = []
    async with async_session() as db:
        rows = (
            (await db.execute(select(Match).where(Match.league == "NHL")))
            .scalars()
            .all()
        )
        by_uid: dict[str, Match] = {r.match_uid: r for r in rows if r.match_uid}
        pair_index: dict[tuple[str, str], list[Match]] = {}
        for r in rows:
            pair_index.setdefault(_pair_key(r.team_home, r.team_away), []).append(r)

        for g in games.values():
            try:
                gid = int(g["id"])
            except (TypeError, ValueError):
                continue
            uid = f"NHL_{gid}"
            home = nhl_api.team_ru(g.get("homeTeam"))
            away = nhl_api.team_ru(g.get("awayTeam"))
            if not home or not away:
                continue
            dt = nhl_api.game_datetime(g)
            status = nhl_api.game_status(g)
            score_h, score_a = nhl_api.game_scores(g)
            period = nhl_api.period_label(g)

            existing = by_uid.get(uid)
            if existing is None:
                twin = _find_nhl_twin(
                    pair_index.get(_pair_key(home, away), []), dt
                )
                if twin is not None:
                    logger.info(
                        "NHL: %s - %s найден в API: %s -> %s, переименовываем",
                        twin.team_home, twin.team_away, twin.match_uid, uid,
                    )
                    by_uid.pop(twin.match_uid, None)
                    twin.match_uid = uid
                    existing = twin
                    by_uid[uid] = twin

            if existing is None:
                new_match = Match(
                    match_uid=uid,
                    league="NHL",
                    team_home=home,
                    team_away=away,
                    datetime_utc=dt,
                    status=status or "pre_game",
                    added_live=(status == "live"),
                    home_score=score_h,
                    away_score=score_a,
                    current_period=period,
                )
                db.add(new_match)
                await db.flush()
                by_uid[uid] = new_match
                pair_index.setdefault(_pair_key(home, away), []).append(new_match)
                changed_ids.append(new_match.id)
                logger.info("NHL: added %s - %s [%s]", home, away, status)
                continue

            dirty = False
            if dt and existing.datetime_utc != dt:
                existing.datetime_utc = dt
                dirty = True
            if status and existing.status != status:
                existing.status = status
                dirty = True
            if score_h is not None and existing.home_score != score_h:
                existing.home_score = score_h
                dirty = True
            if score_a is not None and existing.away_score != score_a:
                existing.away_score = score_a
                dirty = True
            if period and existing.current_period != period:
                existing.current_period = period
                dirty = True
            if dirty:
                changed_ids.append(existing.id)

        await db.commit()

    if changed_ids:
        await _broadcast_matches(changed_ids)
        logger.info("NHL schedule: updated %d matches", len(changed_ids))


async def update_nhl_scores() -> None:
    """Счёт/период/перерыв НХЛ из официального API (каждые 30 секунд).

    Как update_khl_scores: LIVE+clock.inIntermission -> break/«Перерыв»,
    OFF/FINAL -> finished/«Завершён»; строки WIN_ (ещё не переименованные
    в NHL_) матчатся по паре команд +-6 часов.
    """
    try:
        from app import nhl_api
    except Exception as e:
        logger.warning("NHL API import failed: %s", e)
        return
    games = await nhl_api.get_games_window(
        days_back=1, days_fwd=1, max_age=nhl_api.SCORE_LIVE_TTL
    )
    if not games:
        logger.info("NHL update: no games found")
        return

    changed_ids: list[int] = []
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        rows = (
            (await db.execute(
                select(Match).where(
                    Match.league == "NHL",
                    Match.status.in_(["live", "break", "pre_game", "finished"]),
                    Match.datetime_utc >= now - timedelta(days=2),
                )
            ))
            .scalars()
            .all()
        )
        for m in rows:
            g = None
            uid = m.match_uid or ""
            if uid.startswith("NHL_"):
                try:
                    g = games.get(int(uid.split("_", 1)[1]))
                except ValueError:
                    g = None
            if g is None:
                g = nhl_api.find_game_by_pair(
                    games.values(), m.team_home, m.team_away, m.datetime_utc
                )
            if g is None:
                continue
            status = nhl_api.game_status(g)
            score_h, score_a = nhl_api.game_scores(g)
            period = nhl_api.period_label(g)
            dirty = False
            if status and m.status != status:
                m.status = status
                dirty = True
            if score_h is not None and m.home_score != score_h:
                m.home_score = score_h
                dirty = True
            if score_a is not None and m.away_score != score_a:
                m.away_score = score_a
                dirty = True
            if period and m.current_period != period:
                m.current_period = period
                dirty = True
            if dirty:
                changed_ids.append(m.id)
        if changed_ids:
            await db.commit()

    if changed_ids:
        unique_ids = list(set(changed_ids))
        async with async_session() as db:
            result = await db.execute(select(Match).where(Match.id.in_(unique_ids)))
            updated = result.scalars().all()
        await manager.broadcast({
            "type": "matches_update",
            "data": [_match_to_dict(m) for m in updated],
        })
        logger.info("Updated NHL scores for %d matches", len(unique_ids))


def setup_scheduler() -> None:
    scheduler.add_job(
        scrape_and_update,
        "interval",
        minutes=settings.SCRAPER_INTERVAL_MINUTES,
        id="scrape_and_update",
        replace_existing=True,
    )
    scheduler.add_job(
        warm_prime_states,
        "interval",
        seconds=60,
        id="warm_prime_states",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        refresh_live_stream_urls,
        "interval",
        seconds=60,
        id="refresh_live_stream_urls",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        force_upcoming_sources,
        "interval",
        seconds=60,
        id="force_upcoming_sources",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        cleanup_old_matches,
        "interval",
        hours=6,
        id="cleanup_old_matches",
        replace_existing=True,
    )
    scheduler.add_job(
        update_khl_scores,
        "interval",
        seconds=settings.SCORE_UPDATE_INTERVAL_SECONDS,
        id="update_khl_scores",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_khl_start_times,
        "interval",
        minutes=5,
        id="sync_khl_start_times",
        replace_existing=True,
    )
    scheduler.add_job(
        update_mhl_scores,
        "interval",
        seconds=60,
        id="update_mhl_scores",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        sync_win_nhl,
        "interval",
        seconds=60,
        id="sync_win_nhl",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=15),
    )
    scheduler.add_job(
        sync_nhl_schedule,
        "interval",
        minutes=5,
        id="sync_nhl_schedule",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=25),
    )
    scheduler.add_job(
        update_nhl_scores,
        "interval",
        seconds=settings.SCORE_UPDATE_INTERVAL_SECONDS,
        id="update_nhl_scores",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=40),
    )
    scheduler.add_job(
        sync_win_extra,
        "interval",
        seconds=60,
        id="sync_win_extra",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=35),
    )
    scheduler.add_job(
        seed_mhl_schedule,
        "interval",
        hours=6,
        id="seed_mhl_schedule",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=45),
    )
    scheduler.add_job(
        warm_khl_calendar,
        "interval",
        hours=6,
        id="warm_khl_calendar",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=30),
    )
    from app.sender import send_reminders

    scheduler.add_job(
        send_reminders,
        "interval",
        seconds=30,
        id="send_reminders",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Scheduler started")

