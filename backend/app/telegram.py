"""Telegram bot: long-polling /start deep links + outbound messages."""

import asyncio
import logging
import time

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


async def send_message(
    chat_id: str | int, text: str, keyboard: list[list[str]] | None = None
) -> bool:
    payload: dict = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {
            "keyboard": [[{"text": t} for t in row] for row in keyboard],
            "resize_keyboard": True,
            "is_persistent": True,
        }
    data = await _call("sendMessage", payload)
    return bool(data and data.get("ok"))


# кнопка главного меню бота
CONNECT_TV_BUTTON = "📺 Подключить ТВ"
ISSUE_CODE_BUTTON = "🔑 Выдать код"
TV_MENU: list[list[str]] = [[CONNECT_TV_BUTTON]]

# админ в состоянии ожидания chat_id для выдачи кода: chat_id -> ts
_tvcode_pending: dict[int, float] = {}
TVCODE_TTL = 300


def _menu(is_admin: bool) -> list[list[str]]:
    """Главное меню: кнопка выдачи кода — только для админа."""
    if is_admin:
        return [[CONNECT_TV_BUTTON], [ISSUE_CODE_BUTTON]]
    return [list(TV_MENU[0])]


def tv_payment_link(chat_id: int) -> str:
    """Страница оплаты активации ТВ (форма ЮMoney, авто-сабмит)."""
    return f"https://www.hockey-live.online/tv-pay?chat_id={chat_id}"


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

    # кнопка главнего меню «Подключить ТВ» → ссылка на оплату активации
    if text == CONNECT_TV_BUTTON:
        await send_message(
            chat_id,
            "📺 Активация ТВ\n\n"
            "Чтобы приложение на телевизоре заработало, нужна активация — "
            "донат от 50 ₽ через ЮMoney.\n\n"
            "💡 Эти 50 ₽ идут на оплату серверов для стабильной работы проекта — "
            "сейчас все расходы покрываются личными деньгами.\n\n"
            "1. Откройте ссылку ниже и оплатите\n"
            "2. После оплаты в этот чат придёт 6-значный код\n"
            "3. Введите код в приложении на телевизоре\n\n"
            "⚠️ Код одноразовый — после активации перестаёт работать.",
            keyboard=_menu(is_admin),
        )
        await send_message(chat_id, tv_payment_link(chat_id))
        return

    # выдать код активации — только для админа
    if text == ISSUE_CODE_BUTTON:
        if not is_admin:
            await send_message(chat_id, "Команда доступна только администратору.")
            return
        _tvcode_pending[chat_id] = time.time()
        await send_message(
            chat_id,
            "🔑 Выдача кода активации ТВ\n\n"
            f"Пришлите chat_id получателя (число).\n"
            f"Чтобы выдать себе — ваш chat_id: {chat_id}\n\n"
            "Отмена — /cancel",
            keyboard=_menu(is_admin),
        )
        return

    # админ ждёт chat_id после нажатия «Выдать код»
    if is_admin and chat_id in _tvcode_pending:
        if time.time() - _tvcode_pending[chat_id] > TVCODE_TTL:
            _tvcode_pending.pop(chat_id, None)
            await send_message(chat_id, "⏱ Время истекло — нажмите «Выдать код» заново.", keyboard=_menu(is_admin))
            return
        if cmd == "/cancel" or text.lower() in ("отмена", "cancel"):
            _tvcode_pending.pop(chat_id, None)
            await send_message(chat_id, "Отменено.", keyboard=_menu(is_admin))
            return
        if not (text.isdigit() or (text.startswith("-") and text[1:].isdigit())):
            await send_message(chat_id, "chat_id должен быть числом. Отправьте число или /cancel.")
            return
        target = int(text)
        _tvcode_pending.pop(chat_id, None)
        from app.api.tv_auth import issue_tv_code

        code = issue_tv_code(target)
        if target == chat_id:
            await send_message(chat_id, f"🔑 Ваш код: {code}\n\nОдноразовый — введите его на ТВ.", keyboard=_menu(is_admin))
            return
        delivered = await send_message(
            target,
            "🔑 Вам выдан код активации ТВ:\n\n"
            f"{code}\n\n"
            "Введите его в приложении на телевизоре. Код одноразовый.",
        )
        if delivered:
            await send_message(chat_id, f"✅ Код отправлен в чат {target}:\n{code}", keyboard=_menu(is_admin))
        else:
            await send_message(
                chat_id,
                f"⚠️ Не удалось отправить сообщение в чат {target} (бот заблокирован?).\n"
                f"Код для chat_id {target}:\n{code}",
                keyboard=_menu(is_admin),
            )
        return

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
                    keyboard=_menu(is_admin),
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
                    "• Подключение ТВ — кнопкой ниже\n"
                    "• Отписаться от новостей — /stop",
                    keyboard=_menu(is_admin),
                )
            else:
                await send_message(
                    chat_id,
                    "Вы уже подписаны. Напоминания включаются на сайте: "
                    "у матча нажмите «Напоминание».",
                    keyboard=_menu(is_admin),
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

    if cmd == "/tvcode":
        # выдать код вручную (только админ) — /tvcode [chat_id]
        if not is_admin:
            await send_message(chat_id, "Команда доступна только администратору.")
            return
        from app.api.tv_auth import issue_tv_code

        target = parts[1] if len(parts) > 1 else str(chat_id)
        code = issue_tv_code(target)
        await send_message(chat_id, f"🔑 Код для chat_id {target}: {code}\n(одноразовый, лежит в tv_codes.json)")
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
            "Подключение ТВ — кнопкой «Подключить ТВ» ниже\n"
            "Отписаться от новостей: /stop",
            keyboard=_menu(is_admin),
        )
        return

    # Admin can just type a message — it gets broadcast as news.
    if is_admin:
        sent, failed = await broadcast(text)
        await send_message(chat_id, f"📤 Отправлено: {sent}, ошибок: {failed}")
        return

    await send_message(
        chat_id,
        "Не понял команду. Доступно:\n"
        + CONNECT_TV_BUTTON
        + " — активация приложения на ТВ\n"
        "/sub — подписаться на новости\n/stop — отписаться\n/help — помощь",
        keyboard=_menu(is_admin),
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
