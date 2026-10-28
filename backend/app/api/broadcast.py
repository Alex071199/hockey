"""Трансляции матчей из линии 1win (top-parser sportsbook).

Поток данных:
  1. WebSocket wss://api-gateway.top-parser.com/push-server-v2/  -> событие
     "subscribe-match-info" отдаёт matchInfo с полем broadcast {id, url}.
  2. broadcast.url -> HTML плеера (video-translations.top-parser.com), который
     отдаёт 200 ТОЛЬКО при Referer из белого списка 1win (иначе 401 "disabled").
  3. Внутри HTML — прямой m3u8 (master playlist), токен (timestamp+key)
     живёт ограниченное время; прокси-эндпоинт /part подменяет протухшие
     параметры на свежие, если upstream начал отдавать 400/403.
"""

import asyncio
import json
import logging
import re
import ssl
import time
import urllib.parse

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.config import settings
from app.scraper.team_names import canonical_team_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/broadcast", tags=["broadcast"])

WIN_API = "https://api-gateway.top-parser.com"
WIN_PARTNER = "44ba10e5-7df2-47ab-a44d-dc93803c7a6e"
WIN_ORIGIN = "https://1wixpv.life"
WIN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PUSH_URL = (f"wss://api-gateway.top-parser.com/push-server-v2/"
            f"?EIO=4&transport=websocket&Language=ru&externalPartnerId={WIN_PARTNER}")

HOCKEY_SPORT_ID = 35
# подпись m3u8 живёт несколько минут — обновляемся чаще, чтобы не упираться в 400
STATE_TTL = 120
LIVE_TTL = 60            # кэш списка live-матчей
# Подпись в URL живёт несколько минут, а плеер переиспользует ссылку на
# медиа-плейлист вечно: свежие параметры в неё не приходят. Если возраст
# timestamp больше SIGN_TTL — подменяем подпись на свежую до запроса,
# иначе origin отдаёт заглушку placeholders/timeout.ts (~173 кбит/с —
# зритель видит «мыло», а старый фоллбэк не срабатывает: заглушка = 200)
SIGN_TTL = 120

_SSL = ssl.create_default_context()
_state: dict[int, tuple[float, dict]] = {}
_locks: dict[int, asyncio.Lock] = {}
_live_cache: tuple[float, list] | None = None

# Один клиент на все запросы к 1win: раньше каждый сегмент поднимал
# новый TCP+TLS handshake — на старте трансляции (4-6 параллельных
# сегментов) это давало заметные заикания.
_up_client: httpx.AsyncClient | None = None

# --- PRIME: обход geo-блока 1win через пул обычных HTTP-прокси -------------
# 1win режет IP дата-центров (Alwaysdata, Cloudflare) — страница плеера
# отдаёт «Извините, недоступно в вашем регионе». Подпись HLS привязана к
# IP, поэтому на матч закрепляется ОДИН прокси и держится всю трансляцию.
_prime_proxies: list[str] = [
    p.strip() for p in settings.PRIME_PROXIES.split(",") if p.strip()
]
_proxy_clients: dict[str, httpx.AsyncClient] = {}
_match_proxy: dict[int, str] = {}   # win_id -> закреплённый прокси
_proxy_rr = 0                       # round-robin по пулу


def _proxy_client(proxy: str) -> httpx.AsyncClient:
    c = _proxy_clients.get(proxy)
    if c is None or c.is_closed:
        c = httpx.AsyncClient(
            proxy=proxy,
            timeout=25,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=4,
                keepalive_expiry=30,
                max_connections=8,
            ),
        )
        _proxy_clients[proxy] = c
    return c


def _pick_proxy(win_id: int, avoid: set[str] | None = None) -> str | None:
    """Липкий прокси на матч: подпись HLS нельзя менять посреди эфира."""
    global _proxy_rr
    if not _prime_proxies:
        return None
    cur = _match_proxy.get(win_id)
    if cur and cur in _prime_proxies and not (avoid and cur in avoid):
        return cur
    for _ in range(len(_prime_proxies)):
        cand = _prime_proxies[_proxy_rr % len(_prime_proxies)]
        _proxy_rr += 1
        if not (avoid and cand in avoid):
            _match_proxy[win_id] = cand
            return cand
    return _prime_proxies[0]


def _shared_client() -> httpx.AsyncClient:
    global _up_client
    if _up_client is None or _up_client.is_closed:
        _up_client = httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                keepalive_expiry=60,
                max_connections=40,
            ),
        )
    return _up_client

CORS = {"Access-Control-Allow-Origin": "*"}
MANIFEST_HEADERS = {**CORS, "Cache-Control": "no-cache, no-store, must-revalidate"}
SEGMENT_HEADERS = {**CORS, "Cache-Control": "public, max-age=20"}


def _api_headers(extra: dict | None = None) -> dict:
    h = {
        "User-Agent": WIN_UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "x-lang": "ru",
        "x-user-location": "RU",
        "x-external-partner-id": WIN_PARTNER,
        "Origin": WIN_ORIGIN,
        "Referer": WIN_ORIGIN + "/",
    }
    if extra:
        h.update(extra)
    return h


async def _push_broadcast_url(match_id: int) -> str | None:
    """Одноразовое подключение к push-серверу 1win -> broadcast.url матча."""
    headers = {
        "Origin": WIN_ORIGIN,
        "x-external-partner-id": WIN_PARTNER,
        "User-Agent": WIN_UA,
    }
    try:
        async with websockets.connect(
            PUSH_URL, ssl=_SSL, additional_headers=headers,
            max_size=16 * 1024 * 1024, open_timeout=15,
        ) as ws:
            await asyncio.wait_for(ws.recv(), 15)
            await ws.send("40")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), deadline - time.monotonic())
                except asyncio.TimeoutError:
                    break
                if msg == "2":
                    await ws.send("3")
                    continue
                if msg.startswith("40"):
                    await ws.send(
                        '42["subscribe",{"messageType":"subscribe-match-info",'
                        '"data":{"matchIds":[' + str(match_id) + "]}}]"
                    )
                    continue
                if msg.startswith("42") and str(match_id) in msg:
                    try:
                        arr = json.loads(msg[2:])
                        payload = arr[1]["data"]
                    except Exception:
                        continue
                    if payload.get("matchId") == match_id:
                        return (payload.get("broadcast") or {}).get("url")
    except Exception:
        return None
    return None


async def _fetch_player_source(
    broadcast_url: str, proxy: str | None = None
) -> tuple[str | None, str | None, int, int, str]:
    """HTML плеера 1win: (m3u8, embed, status, length, preview).

    Большинство трансляций отдаёт прямой m3u8 (только при Referer из белого
    списка 1win); часть — iframe внутри себя (Twitch и другие плееры).
    Если задан PROXY_URL — запрос идёт через Cloudflare Worker (EU),
    иначе US IP получает заглушку с таймером вместо плеера.
    `proxy` — обычный HTTP-прокси (пул PRIME_PROXIES): 1win режет IP
    дата-центров, HLS-подпись при этом привязана к IP прокси.
    """
    try:
        if proxy:
            client = _proxy_client(proxy)
        else:
            client = _shared_client()
        try:
            proxied = _proxy_target(broadcast_url)
            if proxied:
                # РФ-прокси (хостинг): сам ставит заголовки и ходит с РФ IP
                r = await _shared_client().get(proxied, headers=_PROXY_REQ_HEADERS)
            else:
                headers = {
                    "User-Agent": WIN_UA,
                    "Referer": WIN_ORIGIN + "/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Sec-Fetch-Dest": "iframe",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "cross-site",
                    "Upgrade-Insecure-Requests": "1",
                }
                r = await client.get(broadcast_url, headers=headers)
        except httpx.HTTPError as e:
            if proxy:
                logger.warning("PRIME proxy %s failed for player: %s", proxy, e)
            raise
    except Exception:
        return None, None, 0, 0, ""
    text = r.text
    hdr = " || HEADERS: " + "; ".join(f"{k}={v}" for k, v in r.headers.items())
    if r.status_code != 200:
        return None, None, r.status_code, len(r.content), text[:2000] + hdr
    m = re.search(r"https://[^'\"\s]+\.m3u8[^'\"\s]*", text)
    if m:
        return m.group(0).rstrip("'\";,"), None, r.status_code, len(r.content), ""
    iframe = re.search(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", text, re.I)
    if iframe:
        return None, iframe.group(1), r.status_code, len(r.content), ""
    return None, None, r.status_code, len(r.content), text[:2000] + hdr


async def _fetch_player_m3u8(broadcast_url: str) -> tuple[str | None, int, int, str]:
    """Совместимая обёртка: только HLS-часть источника."""
    m3u8, _embed, status, length, preview = await _fetch_player_source(broadcast_url)
    return m3u8, status, length, preview


async def _get_state(win_id: int, force: bool = False) -> dict | None:
    lock = _locks.setdefault(win_id, asyncio.Lock())
    async with lock:
        cached = _state.get(win_id)
        now = time.time()
        if cached:
            age = now - cached[0]
            if not force and age < STATE_TTL:
                return cached[1]
            if force and age < 15:
                # только что обновлялись — параллельные запросы не долбим WS
                return cached[1]
        broadcast_url = await _push_broadcast_url(win_id)
        if broadcast_url:
            # прокси «липкий» на матч, но если мёртвый — пробуем следующий
            tried: set[str] = set()
            for _ in range(len(_prime_proxies) or 1):
                proxy = _pick_proxy(win_id, tried)
                if proxy:
                    tried.add(proxy)
                m3u8, embed, _status, _len, _prev = await _fetch_player_source(
                    broadcast_url, proxy
                )
                if m3u8 or embed:
                    st: dict = {"broadcast": broadcast_url, "got_at": now}
                    if proxy:
                        st["proxy"] = proxy
                    if m3u8:
                        st["m3u8"] = m3u8
                    else:
                        st["embed"] = embed
                    _state[win_id] = (now, st)
                    return st
                # прокси не смог вытянуть плеер — сбрасываем липкость
                _match_proxy.pop(win_id, None)
        # источник молчит — держимся за недавнее состояние, если оно есть
        if cached and now - cached[0] < STATE_TTL * 4:
            return cached[1]
        return None


async def _upstream_get(url: str, proxy: str | None = None) -> tuple[bytes, int]:
    try:
        client = _proxy_client(proxy) if proxy else _shared_client()
        proxied = _proxy_target(url)
        if proxied:
            r = await _shared_client().get(proxied, headers=_PROXY_REQ_HEADERS)
        else:
            headers = {"User-Agent": WIN_UA, "Accept": "*/*", "Referer": WIN_ORIGIN + "/"}
            r = await client.get(url, headers=headers)
        return r.content, r.status_code
    except httpx.HTTPError as e:
        if proxy:
            logger.warning("PRIME proxy %s failed for upstream: %s", proxy, e)
        return b"", 0
    except Exception:
        return b"", 0


def _rekey(url: str, fresh_m3u8: str) -> str:
    """Подменяет протухающие параметры подписи на свежие (из свежего m3u8)."""
    fresh_q = urllib.parse.parse_qs(urllib.parse.urlparse(fresh_m3u8).query)
    parsed = urllib.parse.urlparse(url)
    own_q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    for key in ("timestamp", "key", "another_key"):
        if key in fresh_q:
            own_q[key] = fresh_q[key]
    query = urllib.parse.urlencode({k: v[0] for k, v in own_q.items()})
    return urllib.parse.urlunparse(parsed._replace(query=query))


def _sign_age(url: str) -> float:
    """Возраст подписи (сек) по параметру timestamp; 0, если его нет."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        return time.time() - int((q.get("timestamp") or [""])[0])
    except ValueError:
        return 0.0


def _is_placeholder(content: bytes) -> bool:
    """Ответ-заглушка origin'а вместо настоящего потока."""
    return b"placeholders/" in content


def _absolutize(ref: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url, ref)


def _proxy_target(url: str) -> str | None:
    """URL запроса через РФ-прокси (PROXY_URL), либо None — напрямую.

    В PROXY_URL может быть query (токен), поэтому разделитель ? или &.
    """
    if not settings.PROXY_URL:
        return None
    sep = "&" if "?" in settings.PROXY_URL else "?"
    return f"{settings.PROXY_URL}{sep}url={urllib.parse.quote(url, safe='')}"


# Заголовки запроса К прокси-хостингу: его nginx режет не-браузерные
# User-Agent, а сами заголовки прокси пробрасывает к 1win уже сам.
_PROXY_REQ_HEADERS = {
    "User-Agent": WIN_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _rewrite_playlist(text: str, base_url: str, win_id: int) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            absolute = _absolutize(stripped, base_url)
            out.append(f"/api/broadcast/{win_id}/part?u="
                       f"{urllib.parse.quote(absolute, safe='')}")
        else:
            out.append(line)
    return "\n".join(out)


def _is_manifest(url: str) -> bool:
    return ".m3u8" in url.split("?")[0]


async def _fetch_manifest(win_id: int, st: dict) -> tuple[bytes, int]:
    proxy = st.get("proxy")
    content, status = await _upstream_get(st["m3u8"], proxy)
    if status != 200 or not content or _is_placeholder(content):
        # прокси умер / подпись протухла: сбрасываем кэш, иначе
        # force-обновление вернёт ТО ЖЕ состояние с мёртвым прокси
        # (защита «только что обновлялись» — возраст < 15 сек)
        _state.pop(win_id, None)
        _match_proxy.pop(win_id, None)
        st2 = await _get_state(win_id, force=True)
        if st2 and st2.get("m3u8"):
            content, status = await _upstream_get(st2["m3u8"], st2.get("proxy"))
            st = st2
    return content, status


@router.get("/live")
async def live_matches():
    """Live-хоккейные матчи 1win, у которых есть трансляция."""
    global _live_cache
    if _live_cache and time.time() - _live_cache[0] < LIVE_TTL:
        return _live_cache[1]

    try:
        hockey = [i for i in await fetch_hockey_line()
                  if i.get("serviceV2") == "live"]
    except RuntimeError as e:
        raise HTTPException(502, f"1win API недоступен: {e}")
    ids = [i["id"] for i in hockey][:80]
    if not ids:
        _live_cache = (time.time(), [])
        return []

    with_bc = await _broadcast_urls(ids)
    result = []
    for i in hockey:
        bc = with_bc.get(i["id"])
        if not bc:
            continue
        result.append({
            "id": i["id"],
            "name": i.get("name", ""),
            "home": (i.get("homeTeam") or {}).get("name", ""),
            "away": (i.get("awayTeam") or {}).get("name", ""),
            "tournament": (i.get("tournament") or {}).get("slug", ""),
            "start_at": i.get("startAt"),
            "broadcast_url": bc,
        })
    _live_cache = (time.time(), result)
    return result


async def fetch_hockey_line() -> list[dict]:
    """Весь хоккей из линии 1win — live и прематч одним запросом."""
    r = await _shared_client().post(
        f"{WIN_API}/matches/get-many", json={}, headers=_api_headers()
    )
    if r.status_code != 200:
        raise RuntimeError(f"1win API: HTTP {r.status_code}")
    try:
        items = r.json().get("result", {}).get("items") or []
    except Exception as e:
        raise RuntimeError(f"1win API: битый ответ ({e})")
    return [i for i in items if i.get("sportId") == HOCKEY_SPORT_ID]


async def match_snapshots(match_ids: list[int]) -> dict[int, dict]:
    """Подписка на несколько матчей одним WS-подключением.

    Возвращает {match_id: {"broadcast": url, "home_score", "away_score",
    "periods", "status"} } — всё, что push-сервер прислал в match-info.
    """
    if not match_ids:
        return {}
    headers = {
        "Origin": WIN_ORIGIN,
        "x-external-partner-id": WIN_PARTNER,
        "User-Agent": WIN_UA,
    }
    wanted = set(match_ids)
    out: dict[int, dict] = {}
    try:
        async with websockets.connect(
            PUSH_URL, ssl=_SSL, additional_headers=headers,
            max_size=16 * 1024 * 1024, open_timeout=15,
        ) as ws:
            await asyncio.wait_for(ws.recv(), 15)
            await ws.send("40")
            joined = ",".join(str(i) for i in match_ids)
            subscribed = False
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                # выходим только когда у всех матчей есть broadcast.url —
                # он может прийти отдельным сообщением спустя секунды
                if len(out) >= len(wanted) and all(
                    s.get("broadcast") for s in out.values()
                ):
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), deadline - time.monotonic())
                except asyncio.TimeoutError:
                    break
                if msg == "2":
                    await ws.send("3")
                    continue
                if msg.startswith("40") and not subscribed:
                    await ws.send('42["subscribe",{"messageType":"subscribe-match-info",'
                                 '"data":{"matchIds":[' + joined + "]}}]")
                    subscribed = True
                    continue
                if not msg.startswith("42"):
                    continue
                try:
                    arr = json.loads(msg[2:])
                    payload = arr[1]["data"]
                    mid = payload["matchId"]
                except Exception:
                    continue
                if mid not in wanted:
                    continue
                snap = out.setdefault(mid, {})
                if payload.get("status"):
                    snap["status"] = payload["status"]
                url = (payload.get("broadcast") or {}).get("url")
                if url:
                    snap["broadcast"] = url
                score = payload.get("matchScore") or {}
                for src, dst in (("t1", "home_score"), ("t2", "away_score")):
                    try:
                        snap[dst] = int(score[src])
                    except (KeyError, TypeError, ValueError):
                        pass
                if payload.get("periodsScore") is not None:
                    snap["periods"] = payload["periodsScore"]
    except Exception:
        pass
    return out


async def _broadcast_urls(match_ids: list[int]) -> dict[int, str]:
    """Подписка на несколько матчей одним WS-подключением."""
    snaps = await match_snapshots(match_ids)
    return {mid: s["broadcast"] for mid, s in snaps.items() if s.get("broadcast")}


def _norm(name: str) -> str:
    # канонизация до сравнения: "Динамо Москва" == "Динамо М",
    # "Шанхай Дрэгонс" == "Шанхайские Драконы" и т.п.
    s = canonical_team_name(name or "")
    s = s.lower().replace("ё", "е").strip()
    s = re.sub(r"^(мхк|хк|фх|академия|сдюссор)\s+", "", s)
    s = re.sub(r"[^\wа-я\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _same_team(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def find_live_entry(
    home: str, away: str, date: str | None, matches: list[dict] | None = None
) -> dict | None:
    """Лучший live-матч 1win (с трансляцией) под названия команд.

    Общая точка для /find и для джобы, которая дописывает PRIME к
    КХЛ/МХЛ/ВХЛ-строкам. `matches` — готовый список live-матчей,
    чтобы не перезапрашивать линию на каждый матч.
    """

    def score(m: dict) -> int:
        hay_home, hay_away = m["home"], m["away"]
        pair_ok = (_same_team(home, hay_home) and _same_team(away, hay_away)) or \
                  (_same_team(home, hay_away) and _same_team(away, hay_home))
        if not pair_ok:
            # запасной вариант — по названию матча целиком
            n = _norm(m["name"])
            if not (_norm(home) in n and _norm(away) in n):
                return -1
        if date and m.get("start_at"):
            day = time.strftime("%Y-%m-%d", time.gmtime(m["start_at"]))
            base = 2 if day == date else 1
        else:
            base = 1
        # статистические события (khl-team-statistics-...) — не настоящие
        # матчи, они не должны перебивать реальную трансляцию
        if "statistics" in (m.get("tournament") or ""):
            base -= 1
        return base

    ranked = sorted(((score(m), m) for m in matches or []), key=lambda x: -x[0])
    if not ranked or ranked[0][0] < 0:
        return None
    return ranked[0][1]


@router.get("/find")
async def find_match(
    home: str = Query(...),
    away: str = Query(...),
    date: str | None = Query(None, description="YYYY-MM-DD (UTC)"),
):
    """Ищет live-матч 1win с трансляцией по названиям команд."""
    matches = await live_matches()
    if not matches:
        raise HTTPException(404, "Нет live-матчей с трансляцией")

    m = find_live_entry(home, away, date, matches)
    if m is None:
        raise HTTPException(404, "Матч не найден в 1win")

    # Какой у источника формат: HLS (наш прокси) или iframe-плеер (Twitch).
    st = await _get_state(m["id"])
    stream: dict | None = None
    if st and st.get("embed"):
        stream = {"kind": "embed", "url": st["embed"]}
    elif st and st.get("m3u8"):
        stream = {"kind": "hls"}

    return {"id": m["id"], "name": m["name"], "tournament": m["tournament"],
            "home": m["home"], "away": m["away"], "start_at": m["start_at"],
            "stream": stream}


@router.get("/_debug/{win_id}")
async def debug_source(win_id: int):
    """Пошаговая диагностика источника (WS -> player HTML -> m3u8)."""
    out: dict = {"win_id": win_id}
    t0 = time.time()
    url = await _push_broadcast_url(win_id)
    out["push"] = {"url": url, "ms": int((time.time() - t0) * 1000)}
    if url:
        t0 = time.time()
        m3u8, embed, status, length, preview = await _fetch_player_source(url)
        out["player"] = {"status": status, "len": length, "m3u8": m3u8,
                         "embed": embed,
                         "ms": int((time.time() - t0) * 1000), "preview": preview}
        if m3u8:
            content, up_status = await _upstream_get(m3u8)
            out["upstream"] = {"status": up_status, "len": len(content),
                               "head": content[:100].decode("utf-8", "replace")}
    return out


@router.get("/{win_id}/stream.m3u8")
async def stream_manifest(win_id: int):
    st = await _get_state(win_id)
    if not st or not st.get("m3u8"):
        raise HTTPException(404, "Трансляция не найдена")
    content, status = await _fetch_manifest(win_id, st)
    if status != 200 or not content or _is_placeholder(content):
        raise HTTPException(502, "Источник недоступен")
    # _fetch_manifest мог пересобрать состояние (другой прокси/edge) —
    # базовый URL для перезаписи относительных ссылок берём свежий
    fresh = (_state.get(win_id) or (0, st))[1]
    base = fresh.get("m3u8") or st["m3u8"]
    text = content.decode("utf-8", errors="replace")
    return Response(
        content=_rewrite_playlist(text, base, win_id),
        media_type="application/vnd.apple.mpegurl",
        headers=MANIFEST_HEADERS,
    )


@router.get("/{win_id}/part")
async def stream_part(win_id: int, u: str = Query(..., description="Абсолютный upstream URL")):
    if not u.startswith("http"):
        raise HTTPException(400, "Bad url")

    # HLS-подпись привязана к IP прокси — весь матч должен идти через один
    cached_st = (_state.get(win_id) or (0, {}))[1]
    proxy = cached_st.get("proxy")

    # подпись старше SIGN_TTL — подменяем ДО запроса: origin отдаёт
    # протухшие URL и с 200 (заглушка placeholders/timeout.ts), поэтому
    # старый фоллбэк «только при не-200» никогда не срабатывал
    if _sign_age(u) > SIGN_TTL:
        st = await _get_state(win_id)
        if st and st.get("m3u8"):
            u = _rekey(u, st["m3u8"])
            proxy = st.get("proxy", proxy)

    content, status = await _upstream_get(u, proxy)

    # протухшая сессия вернула заглушку — перечитываем состояние
    # принудительно и пробуем ещё раз со свежей подписью
    if _is_manifest(u) and status in (200, 206) and _is_placeholder(content):
        st = await _get_state(win_id, force=True)
        if st and st.get("m3u8"):
            u = _rekey(u, st["m3u8"])
            proxy = st.get("proxy", proxy)
            content, status = await _upstream_get(u, proxy)

    if status not in (200, 206) or not content:
        # прокси умер (407/таймаут) или подпись протухла — сбрасываем
        # состояние, чтобы следующий запрос собрал цепочку заново через
        # живой прокси из пула
        _state.pop(win_id, None)
        _match_proxy.pop(win_id, None)
        st = await _get_state(win_id, force=True)
        if st and st.get("m3u8"):
            proxy = st.get("proxy")
            content, status = await _upstream_get(_rekey(u, st["m3u8"]), proxy)
    if status not in (200, 206) or not content:
        raise HTTPException(502, "Upstream недоступен")

    if _is_manifest(u):
        if _is_placeholder(content):
            # сессия умерла совсем — пусть клиент переключится на источник
            raise HTTPException(502, "Источник отдаёт заглушку")
        return Response(
            content=_rewrite_playlist(content.decode("utf-8", errors="replace"), u, win_id),
            media_type="application/vnd.apple.mpegurl",
            headers=MANIFEST_HEADERS,
        )

    media_type = "video/mp2t" if ".ts" in u.split("?")[0] else "application/octet-stream"
    return Response(content=content, media_type=media_type, headers=SEGMENT_HEADERS)
