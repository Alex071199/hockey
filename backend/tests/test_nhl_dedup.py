"""Дедупликация матчей НХЛ при разном написании клубов.

Регрессия: 1win и официальный API пишут клубы по-своему и меняют
транслитерацию от линии к линии («Баффало Сейбрс» против «Баффало Сейбрз»),
а поиск «того же матча» шёл по точному ключу пары — матч попадал в
календарь дважды (прод: WIN_42617569 рядом с NHL_2026020262).
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

import app.models  # noqa: F401  — init_db строит метаданные по моделям
from app.database import async_session, init_db
from app.models import Match
from app.scheduler.tasks import (
    _merge_nhl_duplicates,
    _find_nhl_twin_fuzzy,
    _nhl_name_match,
    _nhl_pair_match,
)

# Август — межсезонье: кластер не зацепит реальные строки локальной БД
GAME_DT = datetime(2005, 8, 15, 12, 0)

UID_API = "__test_nhl_dup_api__"
UID_WIN = "__test_nhl_dup_win__"
_UIDS = (UID_API, UID_WIN)


def test_pair_match_spelling_variants():
    # три реальных дубля с продa (1win писал иначе, чем API)
    assert _nhl_pair_match(
        "Баффало Сейбрз", "Коламбус Блю Джекетс",
        "Баффало Сейбрс", "Коламбус Блю Джекетс",
    )
    assert _nhl_pair_match(
        "Калгари Флэймз", "Анахайм Дакс",
        "Калгари Флеймс", "Анахайм Дакс",
    )
    assert _nhl_pair_match(
        "Миннесота Уайлд", "Сан-Хосе Шаркс",
        "Миннесота Вайлд", "Сан-Хосе Шаркс",
    )
    # дефис в названии города — это тот же клуб
    assert _nhl_pair_match(
        "Сан-Хосе Шаркс", "Даллас Старз",
        "Сан Хосе Шаркс", "Даллас Старз",
    )


def test_pair_match_not_a_twin():
    # другой соперник — не близнец, даже если город тот же
    assert not _nhl_pair_match(
        "Миннесота Уайлд", "Сан-Хосе Шаркс",
        "Миннесота Уайлд", "Анахайм Дакс",
    )
    # близкие по написанию, но РАЗНЫЕ клубы (0.83 при пороге 0.86)
    assert not _nhl_name_match("Нью-Йорк Айлендерс", "Нью-Йорк Рейнджерс")
    # порядок home/away другой — не склеиваем
    assert not _nhl_pair_match(
        "Баффало Сейбрз", "Коламбус Блю Джекетс",
        "Коламбус Блю Джекетс", "Баффало Сейбрз",
    )


def test_fuzzy_twin_found_by_variant_name():
    rows = [
        Match(
            match_uid="NHL_1", league="NHL",
            team_home="Баффало Сейбрз", team_away="Коламбус Блю Джекетс",
            datetime_utc=GAME_DT,
        ),
        Match(
            match_uid="NHL_2", league="NHL",
            team_home="Миннесота Уайлд", team_away="Сан-Хосе Шаркс",
            datetime_utc=GAME_DT + timedelta(hours=1),
        ),
    ]
    # другое написание того же клуба — близнец находится
    twin = _find_nhl_twin_fuzzy(
        rows, "Баффало Сейбрс", "Коламбус Блю Джекетс",
        GAME_DT + timedelta(minutes=30),
    )
    assert twin is not None
    assert twin.match_uid == "NHL_1"
    # чужой матч в том же окне времени — не совпадает
    assert _find_nhl_twin_fuzzy(
        rows, "Миннесота Вайлд", "Анахайм Дакс", GAME_DT + timedelta(hours=1)
    ) is None
    # окно старта ±6 часов сохраняется
    assert _find_nhl_twin_fuzzy(
        rows, "Баффало Сейбрс", "Коламбус Блю Джекетс",
        GAME_DT + timedelta(days=1),
    ) is None


@pytest.mark.asyncio
async def test_merge_rows_with_variant_names():
    """Накопленный дубль с другим написанием клуба сливается в канон API."""
    await init_db()
    try:
        async with async_session() as session:
            session.add_all(
                [
                    Match(
                        match_uid=UID_API, league="NHL",
                        team_home="Баффало Сейбрз",
                        team_away="Коламбус Блю Джекетс",
                        datetime_utc=GAME_DT, status="finished",
                        home_score=5, away_score=2,
                        stream_urls=[
                            {
                                "url": "http://api/stream.m3u8",
                                "quality": "auto",
                                "source": "prime",
                            }
                        ],
                    ),
                    Match(
                        match_uid=UID_WIN, league="NHL",
                        team_home="Баффало Сейбрс",
                        team_away="Коламбус Блю Джекетс",
                        datetime_utc=GAME_DT, status="finished",
                        stream_urls=[
                            {
                                "url": "http://win/embed",
                                "quality": "auto",
                                "source": "prime",
                            }
                        ],
                    ),
                ]
            )
            await session.flush()

            changed: list[int] = []
            merged = await _merge_nhl_duplicates(session, set(), changed)
            assert merged >= 1, "дубль должен быть слит"

            left = (
                (
                    await session.execute(
                        select(Match).where(Match.match_uid.in_(_UIDS))
                    )
                )
                .scalars()
                .all()
            )
            assert len(left) == 1, "строки одного матча должны слиться в одну"
            assert left[0].match_uid == UID_API, "канон — строка официального API"
            assert left[0].home_score == 5, "счёт канона сохраняется"
            urls = {s.get("url") for s in (left[0].stream_urls or [])}
            assert "http://api/stream.m3u8" in urls, "свой стрим канона остаётся"
            assert "http://win/embed" in urls, "стрим дубля переходит канону"
            # ничего не коммитим: тест не должен менять локальную БД
            await session.rollback()
    finally:
        async with async_session() as session:
            await session.execute(
                delete(Match).where(Match.match_uid.in_(_UIDS))
            )
            await session.commit()
