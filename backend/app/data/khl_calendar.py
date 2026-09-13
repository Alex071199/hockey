from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

KHL_CALENDAR = [
    {"date": "2026-09-05", "time": "13:00", "home": "Локомотив", "away": "Трактор"},
    {"date": "2026-09-05", "time": "14:30", "home": "Автомобилист", "away": "Динамо М"},
    {"date": "2026-09-05", "time": "17:00", "home": "СКА", "away": "Лада"},
    {"date": "2026-09-05", "time": "17:00", "home": "Спартак", "away": "Торпедо"},
    {"date": "2026-09-05", "time": "17:00", "home": "Северсталь", "away": "Салават Юлаев"},
    {"date": "2026-09-05", "time": "17:00", "home": "Ак Барс", "away": "Сибирь"},
    {"date": "2026-09-06", "time": "14:30", "home": "Металлург Мг", "away": "Амур"},
    {"date": "2026-09-06", "time": "17:00", "home": "Нефтехимик", "away": "Шанхайские Драконы"},
    {"date": "2026-09-07", "time": "16:30", "home": "Авангард", "away": "Салават Юлаев"},
    {"date": "2026-09-07", "time": "17:00", "home": "Барыс", "away": "Сибирь"},
    {"date": "2026-09-07", "time": "17:00", "home": "Автомобилист", "away": "Трактор"},
    {"date": "2026-09-07", "time": "19:00", "home": "Северсталь", "away": "Лада"},
    {"date": "2026-09-07", "time": "19:10", "home": "Динамо Мн", "away": "Торпедо"},
    {"date": "2026-09-07", "time": "19:30", "home": "Ак Барс", "away": "Адмирал"},
    {"date": "2026-09-07", "time": "19:30", "home": "СКА", "away": "Динамо М"},
    {"date": "2026-09-07", "time": "19:30", "home": "ЦСКА", "away": "Спартак"},
]

_calendar_index: dict[tuple[str, str, str], dict] = {}


def _build_index():
    if _calendar_index:
        return
    for m in KHL_CALENDAR:
        key = (m["date"], m["home"], m["away"])
        _calendar_index[key] = m
        key_rev = (m["date"], m["away"], m["home"])
        _calendar_index[key_rev] = m


def get_calendar_datetime(team_home: str, team_away: str, date_str: str) -> datetime | None:
    _build_index()
    key = (date_str, team_home, team_away)
    m = _calendar_index.get(key)
    if not m:
        return None
    h, mi = m["time"].split(":")
    return datetime.strptime(f"{date_str} {m['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=MSK).astimezone(timezone.utc).replace(tzinfo=None)
