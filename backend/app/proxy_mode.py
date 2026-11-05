"""Режим reverse proxy: если задан PROXY_TARGET, экземпляр становится
прозрачным пробросом на другой деплой (Railway).

Нужен, когда панель хостинга недоступна (блокировка по IP) и сменить тип
сайта на настоящий reverse proxy нельзя: приложение само проксирует запросы,
поэтому домен hockey-live.alwaysdata.net продолжает работать, а весь тяжёлый
трафик (видео, APK, API) уходит на быстрый Railway. Ссылки клиентов, OTA и
вебхук ЮMoney при этом не меняются.
"""

import asyncio
import logging
from urllib.parse import urlparse

import httpx
import websockets
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Заголовки, которые не пробрасываются между hop'ами (RFC 9110, 7.6.1).
# accept-encoding убираем тоже: апстрим отдаёт ответ без сжатия (identity),
# а gzip для клиента делает наш GZipMiddleware — так нет двойного сжатия.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "accept-encoding",
}

_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# HTTP-клиент проброса; создаётся в mount_proxy, закрывается через lifespan
# (см. aclose() — add_event_handler в новых версиях FastAPI удалён).
_client: httpx.AsyncClient | None = None


async def aclose() -> None:
    """Закрывает пул соединений прокси (вызывается из lifespan)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def mount_proxy(app, target: str) -> None:
    """Ставит catch-all маршрут, перекрывающий все локальные эндпоинты."""
    global _client
    target = target.rstrip("/")
    parsed = urlparse(target)
    authority = parsed.netloc
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"

    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0),
        follow_redirects=False,
    )
    client = _client

    @app.api_route("/{path:path}", methods=_METHODS)
    async def forward(request: Request, path: str) -> StreamingResponse:
        url = f"{target}/{path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in _HOP_BY_HOP
        }
        headers["host"] = authority
        headers["accept-encoding"] = "identity"
        headers["x-forwarded-for"] = request.client.host if request.client else ""
        headers["x-forwarded-proto"] = request.url.scheme
        headers["x-forwarded-host"] = request.headers.get("host", "")

        body = await request.body()
        upstream_request = client.build_request(
            request.method, url, headers=headers, content=body or None
        )
        upstream = await client.send(upstream_request, stream=True)
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in _HOP_BY_HOP
        }

        async def _stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(
            _stream(),
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @app.websocket("/ws")
    async def forward_websocket(ws: WebSocket) -> None:
        """Бирдирекция /ws: клиент <-> апстрим (обновления матчей в реальном времени)."""
        await ws.accept()
        upstream_url = f"{ws_scheme}://{authority}/ws"
        try:
            async with websockets.connect(
                upstream_url, max_size=16 * 1024 * 1024, open_timeout=15
            ) as upstream:
                pump_tasks = [
                    asyncio.create_task(_upstream_to_client(upstream, ws)),
                    asyncio.create_task(_client_to_upstream(ws, upstream)),
                ]
                _done, pending = await asyncio.wait(
                    pump_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
        except (WebSocketDisconnect, Exception) as exc:  # noqa: BLE001
            logger.info("ws proxy closed: %s", exc)
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass


async def _upstream_to_client(upstream, ws: WebSocket) -> None:
    async for message in upstream:
        if isinstance(message, str):
            await ws.send_text(message)
        else:
            await ws.send_bytes(message)


async def _client_to_upstream(ws: WebSocket, upstream) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            break
        text = message.get("text")
        if text is not None:
            await upstream.send(text)
        else:
            payload = message.get("bytes")
            if payload is not None:
                await upstream.send(payload)
