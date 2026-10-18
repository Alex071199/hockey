import time
import urllib.parse

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import broadcast as b
from app.main import app

PLACEHOLDER = b"#EXTM3U\n#EXT-X-TARGETDURATION:3\n#EXTINF:3.000,\nplaceholders/timeout.ts\n"
REAL_PLAYLIST = b"#EXTM3U\n#EXT-X-TARGETDURATION:3\n#EXTINF:3.000,\nseg1.ts\n"
REAL_MASTER = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000\nmulty_hd.m3u8\n"


def _url(ts: int, host="edg02.host", path="abc_hd/playlist.m3u8", key="OLDKEY", another="OLDA"):
    return (f"https://{host}/{path}?match_id=1&timestamp={ts}"
            f"&key={key}&another_key={another}")


def _state(m3u8_ts=None, host="edg04.host", path="abc/multy.m3u8",
           key="NEWKEY", another="NEWAKEY"):
    ts = m3u8_ts if m3u8_ts is not None else int(time.time())
    return {"m3u8": f"https://{host}/{path}?match_id=1&timestamp={ts}"
                    f"&key={key}&another_key={another}"}


def test_sign_age():
    assert b._sign_age(_url(int(time.time()) - 300)) == pytest.approx(300, abs=5)
    assert b._sign_age(_url(int(time.time()))) < 5
    # нет timestamp — считаем подпись свежей и не трогаем
    assert b._sign_age("https://x/host/playlist.m3u8?match_id=1") == 0
    assert b._sign_age("https://x/host/playlist.m3u8?timestamp=junk") == 0


def test_is_placeholder():
    assert b._is_placeholder(PLACEHOLDER)
    assert not b._is_placeholder(REAL_MASTER)
    assert not b._is_placeholder(REAL_PLAYLIST)
    assert not b._is_placeholder(b"\x47\x40" * 5000)  # бинарный .ts


def _install(monkeypatch, upstream, state=None):
    """Вешает фейковые _upstream_get/_get_state, возвращает журналы вызовов."""
    fetched: list[str] = []
    state_calls: list[bool] = []

    async def fake_up(url):
        fetched.append(url)
        return upstream(url)

    async def fake_state(win_id, force=False):
        state_calls.append(force)
        if state is None:
            return _state()
        return state(win_id, force)

    monkeypatch.setattr(b, "_upstream_get", fake_up)
    monkeypatch.setattr(b, "_get_state", fake_state)
    return fetched, state_calls


async def _get_part(u: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(
            f"/api/broadcast/1/part?u={urllib.parse.quote(u, safe='')}")


@pytest.mark.asyncio
async def test_stale_url_is_rekeyed_before_fetch(monkeypatch):
    stale = _url(int(time.time()) - 600)

    def upstream(url):
        # origin отвечает только на свежую подпись
        return REAL_PLAYLIST, 200

    fetched, state_calls = _install(monkeypatch, upstream)
    r = await _get_part(stale)
    assert r.status_code == 200
    assert len(fetched) == 1
    got = urllib.parse.parse_qs(urllib.parse.urlparse(fetched[0]).query)
    assert time.time() - int(got["timestamp"][0]) < 5
    assert got["key"] == ["NEWKEY"]
    assert got["another_key"] == ["NEWAKEY"]
    assert got["match_id"] == ["1"]           # чужие параметры сохраняем
    assert fetched[0].split("?")[0] == stale.split("?")[0]  # путь/хост не трогаем
    assert state_calls == [False]             # кэшированное состояние, без WS
    assert f"/api/broadcast/1/part?u=" in r.text  # сегменты отрёрнуты


@pytest.mark.asyncio
async def test_fresh_url_is_passed_through(monkeypatch):
    fresh = _url(int(time.time()) - 10)

    def upstream(url):
        return REAL_PLAYLIST, 200

    fetched, state_calls = _install(monkeypatch, upstream)
    r = await _get_part(fresh)
    assert r.status_code == 200
    assert fetched == [fresh]          # свежую подпись не подменяем
    assert state_calls == []           # и состояние не трогаем


@pytest.mark.asyncio
async def test_placeholder_triggers_state_refresh_and_recovers(monkeypatch):
    fresh = _url(int(time.time()) - 10)
    calls = {"n": 0}

    def upstream(url):
        calls["n"] += 1
        return (PLACEHOLDER, 200) if calls["n"] == 1 else (REAL_PLAYLIST, 200)

    fetched, state_calls = _install(monkeypatch, upstream)
    r = await _get_part(fresh)
    assert r.status_code == 200
    assert calls["n"] == 2
    assert state_calls == [True]                       # принудительное обновление
    got = urllib.parse.parse_qs(urllib.parse.urlparse(fetched[1]).query)
    assert got["key"] == ["NEWKEY"]                    # повтор с новой подписью
    assert "placeholders/" not in r.text


@pytest.mark.asyncio
async def test_placeholder_persistent_returns_502(monkeypatch):
    fresh = _url(int(time.time()) - 10)

    def upstream(url):
        return PLACEHOLDER, 200

    fetched, state_calls = _install(monkeypatch, upstream)
    r = await _get_part(fresh)
    assert r.status_code == 502        # заглушка клиенту не отдаётся
    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_non_200_keeps_old_fallback(monkeypatch):
    stale = _url(int(time.time()) - 600)
    calls = {"n": 0}

    def upstream(url):
        calls["n"] += 1
        return (b"", 403) if calls["n"] == 1 else (REAL_PLAYLIST, 200)

    fetched, state_calls = _install(monkeypatch, upstream)
    r = await _get_part(stale)
    assert r.status_code == 200
    assert calls["n"] == 2
    assert state_calls == [False, True]   # pre-rekey (кэш) + force при не-200
    assert "seg1.ts" in r.text


@pytest.mark.asyncio
async def test_stream_manifest_refreshes_on_placeholder(monkeypatch):
    def upstream(url):
        # состояние с NEWKEY отвечает заглушкой, с M2KEY — настоящим мастером
        if "key=M2KEY" in url:
            return REAL_MASTER, 200
        return PLACEHOLDER, 200

    def state_factory(win_id, force=False):
        return _state(key="NEWKEY") if not force else _state(key="M2KEY")

    fetched, state_calls = _install(monkeypatch, upstream, state_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/broadcast/1/stream.m3u8")
    assert r.status_code == 200
    assert state_calls[0] is False      # обычный путь
    assert True in state_calls          # placeholder вызвал force
    assert "key=M2KEY" in fetched[1]    # повтор уже со свежей подписью
    assert "multy_hd.m3u8" in r.text
    assert "placeholders/" not in r.text
