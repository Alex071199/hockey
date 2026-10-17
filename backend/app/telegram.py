"""Telegram bot: long-polling /start deep links + outbound messages."""

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def bot_username() -> str:
    return settings.TELEGRAM_BOT_USERNAME


def deep_link(code: str) -> str:
    return f"https://t.me/{bot_username()}?start={code}"


async def _call(method: str, payload: dict, timeout: float = 20.0) -> dict | None:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return None
    url = f"{API_BASE}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except Exception as e:
        logger.warning("telegram %s failed: %s", method, e)
        return None
    if not data.get("ok"):
        logger.warning("telegram %s not ok: %s", method, data)
    return data


async def send_message(chat_id: str | int, text: str) -> bool:
    data = await _call("sendMessage", {"chat_id": chat_id, "text": text})
    return bool(data and data.get("ok"))


async def _bind_code(code: str, chat_id: int) -> int:
    from sqlalchemy import update

    from app.database import async_session
    from app.models import Reminder

    async with async_session() as db:
        res = await db.execute(
            update(Reminder).where(Reminder.code == code).values(chat_id=str(chat_id))
        )
        await db.commit()
        return res.rowcount or 0


def _is_admin(chat_id: int) -> bool:
    admin = (settings.TELEGRAM_ADMIN_CHAT_ID or "").strip()
    return bool(admin) and str(chat_id) == admin


async def _subscribe(chat_id: int, username: str | None) -> bool:
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Subscriber

    async with async_session() as db:
        res = await db.execute(select(Subscriber).where(Subscriber.chat_id == str(chat_id)))
        sub = res.scalar_one_or_none()
        if sub:
            if not sub.active:
                sub.active = True
                await db.commit()
            return False
        db.add(Subscriber(chat_id=str(chat_id), username=username, active=True))
        await db.commit()
        return True


async def _unsubscribe(chat_id: int) -> None:
    from sqlalchemy import update

    from app.database import async_session
    from app.models import Subscriber

    async with async_session() as db:
        await db.execute(
            update(Subscriber)
            .where(Subscriber.chat_id == str(chat_id))
            .values(active=False)
        )
        await db.commit()


async def _active_subscribers() -> list[str]:
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Subscriber

    async with async_session() as db:
        res = await db.execute(select(Subscriber.chat_id).where(Subscriber.active == True))  # noqa: E712
        return [row[0] for row in res.all()]


async def _save_news(text: str) -> None:
    """Сохранить новость в БД — она попадёт в колокольчик на сайте."""
    try:
        from app.database import async_session
        from app.models import News

        async with async_session() as db:
            db.add(News(text=text))
            await db.commit()
    except Exception as e:
        logger.warning("news save failed: %s", e)


async def broadcast(text: str) -> tuple[int, int]:
    """Send text to all active subscribers. Returns (sent, failed)."""
    # Всё, что видят все подписчики бота, попадает и на сайт (колокольчик)
    await _save_news(text)
    chat_ids = await _active_subscribers()
    sent = failed = 0
    for cid in chat_ids:
        if await send_message(cid, text):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # stay well under Telegram rate limits
    logger.info("Broadcast: sent=%d failed=%d", sent, failed)
    return sent, failed


async def _handle_message(msg: dict) -> None:
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    username = (msg.get("from") or {}).get("username")
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    is_admin = _is_admin(chat_id)

    if not is_admin:
        logger.info("telegram message from chat_id=%s (@%s): %s", chat_id, username, text[:50])

    if cmd == "/start":
        code = parts[1] if len(parts) > 1 else ""
        if code:
            bound = await _bind_code(code, chat_id)
            new_sub = await _subscribe(chat_id, username)
            if bound:
                await send_message(
                    chat_id,
                    "✅ Готово! Напоминание подключено.\n"
                    "Сообщение придёт в этот чат, когда матч начнётся."
                    + ("\n\n📢 Вы также подписаны на новости — /stop отменяет подписку." if new_sub else ""),
                )
            else:
                await send_message(
                    chat_id,
                    "❌ Код не найден. Откройте матч на сайте и нажмите «Напоминание» заново.",
                )
        else:
            new_sub = await _subscribe(chat_id, username)
            if new_sub:
                await send_message(
                    chat_id,
                    "👋 Привет! Я присылаю уведомления о начале матчей и новости хоккея.\n\n"
                    "• Напоминания — на сайте: у матча нажмите «Напоминание»\n"
                    "• Новости канала приходят сюда автоматически\n"
                    "• Отписаться от новостей — /stop",
                )
            else:
                await send_message(
                    chat_id,
                    "Вы уже подписаны. Напоминания включаются на сайте: "
                    "у матча нажмите «Напоминание».",
                )
        return

    if cmd == "/stop":
        await _unsubscribe(chat_id)
        await send_message(chat_id, "🔕 Подписка на новости отменена. Напоминания о матчах продолжают работать.")
        return

    if cmd == "/sub":
        new_sub = await _subscribe(chat_id, username)
        await send_message(
            chat_id,
            "📢 Вы подписаны на новости." if new_sub else "Вы уже подписаны на новости.",
        )
        return

    if cmd in ("/help", "/news"):
        if cmd == "/news":
            if not is_admin:
                await send_message(chat_id, "Команда доступна только администратору.")
                return
            body = text[len(parts[0]):].strip()
            if not body:
                await send_message(chat_id, "Использование: /news Текст новости")
                return
            sent, failed = await broadcast(body)
            await send_message(chat_id, f"📤 Отправлено: {sent}, ошибок: {failed}")
            return
        await send_message(
            chat_id,
            "Я присылаю уведомления о начале матчей и новости хоккея.\n"
            "Сайт: hockey-live.online\n"
            "Отписаться от новостей: /stop",
        )
        return

    # Admin can just type a message — it gets broadcast as news.
    if is_admin:
        sent, failed = await broadcast(text)
        await send_message(chat_id, f"📤 Отправлено: {sent}, ошибок: {failed}")
        return

    await send_message(
        chat_id,
        "Не понял команду. Доступно:\n/sub — подписаться на новости\n/stop — отписаться\n/help — помощь",
    )


async def _handle_update(u: dict) -> None:
    msg = u.get("message") or u.get("edited_message")
    if not msg:
        return
    try:
        await _handle_message(msg)
    except Exception:
        logger.exception("telegram update handling failed")


async def polling_task() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not set — Telegram reminders disabled")
        return

    logger.info("Telegram polling started for @%s", bot_username())
    offset = 0
    while True:
        data = await _call(
            "getUpdates",
            {"offset": offset, "timeout": 50, "allowed_updates": ["message"]},
            timeout=70,
        )
        if data and data.get("ok"):
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                await _handle_update(u)
        else:
            await asyncio.sleep(5)
