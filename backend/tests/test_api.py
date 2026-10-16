import pytest
from httpx import ASGITransport, AsyncClient

from app.api.broadcast import find_live_entry
from app.main import app
from app.scheduler.tasks import (
    _is_regular_nhl,
    _is_regular_nhl_row,
    _keep_prime,
    _win_period,
    _win_status,
)


def _line_item(tournament="nhl", category="usa", home="Монреаль", away="Каролина"):
    return {
        "id": 1,
        "tournament": {"slug": tournament},
        "category": {"slug": category},
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "serviceV2": "prematch",
    }


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_schedule():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/schedule")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert {"id", "league", "team_home", "team_away", "status"} <= set(data[0])


@pytest.mark.asyncio
async def test_leagues_include_nhl():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/leagues")
    assert response.status_code == 200
    ids = [l["id"] for l in response.json()]
    assert {"KHL", "VHL", "MHL", "NHL"} <= set(ids)


def test_win_status_prefers_line_service():
    live = {"serviceV2": "live"}
    prematch = {"serviceV2": "prematch"}
    assert _win_status(live, {}) == "live"
    assert _win_status(prematch, {}) == "pre_game"
    # WS знает, что матч кончился, раньше линии
    assert _win_status(live, {"status": "Закончен"}) == "finished"


def test_win_period_ignores_service_statuses():
    assert _win_period({}) is None
    assert _win_period({"status": "Еще не началось"}) is None
    assert _win_period({"status": "Created"}) is None
    assert _win_period({"status": "Закончен"}) == "Завершён"
    assert _win_period({"status": "Овертайм"}) == "Овертайм"
    assert _win_period({"status": "Основное время"}) == "1-й период"
    assert _win_period({"status": "Основное время",
                        "periods": [{"t1": "1", "t2": "0"}]}) == "2-й период"


def test_regular_nhl_filter():
    # настоящая игра регулярки
    assert _is_regular_nhl(_line_item())
    # реплеи, киберспорт, долгосрочные ставки — мимо
    assert not _is_regular_nhl(_line_item(category="replays"))
    assert not _is_regular_nhl(_line_item(tournament="nhl-esportsbattle-3x4-mins"))
    assert not _is_regular_nhl(_line_item(home="", away="Каролина"))


def test_regular_nhl_row_by_content():
    assert _is_regular_nhl_row("Монреаль Канадиенс", "Каролина Харрикейнз")
    # мусор, чей 1win-id уже вышел из линии, узнаём по именам
    assert not _is_regular_nhl_row("Даллас Старз (replays)", "Сент-Луис Блюз (replays)")
    assert not _is_regular_nhl_row("Нью-Йорк Айлендерс (Wryi)", "Тампа-Бэй (Xotaruu)")


def test_find_live_entry_matches_by_teams():
    def entry(home, away, name=None, start_at=1760000000):
        return {
            "id": 10, "home": home, "away": away,
            "name": name or f"{home} - {away}", "start_at": start_at,
            "tournament": "khl", "broadcast_url": "https://x/b",
        }

    live = [entry("Сибирь", "Салават Юлаев")]
    m = find_live_entry("Сибирь", "Салават Юлаев", "2025-10-09", live)
    assert m and m["id"] == 10
    # дата, отличная от даты матча, не мешает совпадению по командам
    assert find_live_entry("Сибирь", "Салават Юлаев", "2025-10-10", live)
    # чужая пара — не найдено
    assert find_live_entry("Ак Барс", "ЦСКА", "2025-10-09", live) is None
    # пустой список
    assert find_live_entry("Сибирь", "Салават Юлаев", None, []) is None


def test_keep_prime_when_url_matches_other_source():
    # embed 1win совпадает с URL livetv_youtube — PRIME всё равно сохраняем
    url = "https://www.youtube.com/embed/6PW_Z9ke-YM"
    old = [
        {"url": url, "source": "livetv_youtube"},
        {"url": url, "source": "prime"},
    ]
    new = [{"url": url, "source": "livetv_youtube"}]
    merged = _keep_prime(new, old)
    assert [s["source"] for s in merged] == ["livetv_youtube", "prime"]
    # повторная склейка не плодит дубли
    assert [s["source"] for s in _keep_prime(new, merged)] == [
        "livetv_youtube",
        "prime",
    ]
    # чужой prime-URL того же источника не дублируется
    assert _keep_prime(merged, merged) == merged
