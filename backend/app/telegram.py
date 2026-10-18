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
) -> int | None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {
            "keyboard": [[{"text": t} for t in row] for row in keyboard],
            "resize_keyboard": True,
            "is_persistent": True,
        }
    data = await _call("sendMessage", payload)
    if data and data.get("ok"):
        return (data.get("result") or {}).get("message_id")
    return None


# кнопка главного меню бота
CONNECT_TV_BUTTON = "📺 Подключить ТВ"
ISSUE_CODE_BUTTON = "🔑 Выдать код"
DELETE_LAST_BUTTON = "🗑 Удалить последнюю рассылку"
TV_MENU: list[list[str]] = [[CONNECT_TV_BUTTON]]

# админ в состоянии ожидания chat_id для выдачи кода: chat_id -> ts
_tvcode_pending: dict[int, float] = {}
TVCODE_TTL = 300

# админ подтверждает удаление последней рассылки: chat_id -> ts
_delpending: dict[int, float] = {}
DEL_TTL = 300


def _menu(is_admin: bool) -> list[list[str]]:
    """Главное меню: кнопки выдачи кода и удаления рассылки — только для админа."""
    if is_admin:
        return [[CONNECT_TV_BUTTON], [ISSUE_CODE_BUTTON], [DELETE_LAST_BUTTON]]
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


async def _save_news(text: str) -> int | None:
    """Сохранить новость в БД — она попадёт в колокольчик на сайте."""
    try:
        from app.database import async_session
        from app.models import News

        async with async_session() as db:
            row = News(text=text)
            db.add(row)
            await db.flush()
            news_id = row.id
            await db.commit()
            return news_id
    except Exception as e:
        logger.warning("news save failed: %s", e)
        return None


async def broadcast(text: str) -> tuple[int, int]:
    """Send text to all active subscribers. Returns (sent, failed)."""
    # Всё, что видят все подписчики бота, попадает и на сайт (колокольчик)
    from app.database import async_session
    from app.models import Broadcast, BroadcastDelivery

    news_id = await _save_news(text)
    async with async_session() as db:
        bcast = Broadcast(news_id=news_id, text=text)
        db.add(bcast)
        await db.flush()
        bcast_id = bcast.id
        await db.commit()

    chat_ids = await _active_subscribers()
    sent = failed = 0
    deliveries: list[BroadcastDelivery] = []
    for cid in chat_ids:
        message_id = await send_message(cid, text)
        if message_id:
            sent += 1
            deliveries.append(
                BroadcastDelivery(
                    broadcast_id=bcast_id, chat_id=str(cid), message_id=message_id
                )
            )
        else:
            failed += 1
        await asyncio.sleep(0.05)  # stay well under Telegram rate limits
    if deliveries:
        async with async_session() as db:
            db.add_all(deliveries)
            await db.commit()
    logger.info("Broadcast: sent=%d failed=%d", sent, failed)
    return sent, failed


async def _delete_last_broadcast() -> str:
    """Отозвать последнюю рассылку: deleteMessage из чатов TG + новость с сайта."""
    from sqlalchemy import delete as sql_delete, desc, select

    from app.database import async_session
    from app.models import Broadcast, BroadcastDelivery, News

    async with async_session() as db:
        res = await db.execute(select(Broadcast).order_by(desc(Broadcast.id)).limit(1))
        bcast = res.scalar_one_or_none()
        if not bcast:
            return "📋 В журнале нет рассылок — удалять нечего."
        dres = await db.execute(
            select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == bcast.id)
        )
        deliveries = dres.scalars().all()

    ok = bad = 0
    for d in deliveries:
        data = await _call(
            "deleteMessage", {"chat_id": d.chat_id, "message_id": d.message_id}
        )
        if data and data.get("ok"):
            ok += 1
        else:
            bad += 1
        await asyncio.sleep(0.05)

    async with async_session() as db:
        if bcast.news_id:
            await db.execute(sql_delete(News).where(News.id == bcast.news_id))
        await db.execute(
            sql_delete(BroadcastDelivery).where(
                BroadcastDelivery.broadcast_id == bcast.id
            )
        )
        await db.execute(sql_delete(Broadcast).where(Broadcast.id == bcast.id))
        await db.commit()

    preview = bcast.text or ""
    if len(preview) > 150:
        preview = preview[:150] + "…"
    out = [f"🗑 Рассылка удалена:\n«{preview}»\n", f"Из чатов Telegram: удалено {ok}"]
    if bad:
        out.append(
            f"не удалено {bad} (Telegram хранит сообщения только 48 часов после отправки)"
        )
    out.append(
        "Колокольчик на сайте: новость снята"
        if bcast.news_id
        else "Колокольчик: новость на сайте не найдена"
    )
    return "\n".join(out)


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
        _delpending.pop(chat_id, None)
        _tvcode_pending[chat_id] = time.time()
        await send_message(
            chat_id,
            "🔑 Выдача кода активации ТВ\n\n"
            "Пришлите chat_id получателя (число),\n"
            "либо «мне» или «мне 3» — коды придут прямо в этот чат,\n"
            "чтобы передать их человеку вручную.\n\n"
            f"Ваш chat_id: {chat_id}\n"
            "Отмена — /cancel",
            keyboard=_menu(is_admin),
        )
        return

    # удалить последнюю рассылку — только для админа
    if text == DELETE_LAST_BUTTON:
        if not is_admin:
            await send_message(chat_id, "Команда доступна только администратору.")
            return
        _tvcode_pending.pop(chat_id, None)
        from sqlalchemy import desc, select

        from app.database import async_session
        from app.models import Broadcast

        async with async_session() as db:
            res = await db.execute(
                select(Broadcast).order_by(desc(Broadcast.id)).limit(1)
            )
            last = res.scalar_one_or_none()
        if not last:
            await send_message(
                chat_id,
                "📋 В журнале нет рассылок — удалять нечего.\n"
                "(Журнал ведётся с этого обновления; старые рассылки в нём нет.)",
                keyboard=_menu(is_admin),
            )
            return
        _delpending[chat_id] = time.time()
        preview = last.text or ""
        if len(preview) > 300:
            preview = preview[:300] + "…"
        await send_message(
            chat_id,
            "🗑 Удалить последнюю рассылку?\n\n"
            f"«{preview}»\n\n"
            "Она исчезнет из чатов Telegram (Telegram позволяет удалить "
            "сообщения в течение 48 часов после отправки) и из колокольчика на сайте.\n\n"
            "Ответьте «да» для удаления. Отмена — /cancel",
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
        words = text.lower().split()
        if words and words[0] in ("мне", "себе", "самому", "сам"):
            count = 1
            if len(words) > 1 and words[1].isdigit():
                count = max(1, min(int(words[1]), 20))
            _tvcode_pending.pop(chat_id, None)
            from app.api.tv_auth import issue_tv_code

            codes = [await issue_tv_code(chat_id) for _ in range(count)]
            listed = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(codes))
            await send_message(
                chat_id,
                "🔑 Коды для передачи вручную (по одному на ТВ):\n\n"
                + listed
                + "\n\nКаждый код одноразовый.",
                keyboard=_menu(is_admin),
            )
            return
        if not (text.isdigit() or (text.startswith("-") and text[1:].isdigit())):
            await send_message(chat_id, "chat_id должен быть числом. Отправьте число или /cancel.")
            return
        target = int(text)
        _tvcode_pending.pop(chat_id, None)
        from app.api.tv_auth import issue_tv_code

        code = await issue_tv_code(target)
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

    # админ подтверждает удаление последней рассылки
    if is_admin and chat_id in _delpending:
        if time.time() - _delpending[chat_id] > DEL_TTL:
            _delpending.pop(chat_id, None)
            await send_message(chat_id, "⏱ Время истекло — нажмите «Удалить последнюю рассылку» заново.", keyboard=_menu(is_admin))
            return
        if cmd == "/cancel" or text.lower() in ("отмена", "cancel"):
            _delpending.pop(chat_id, None)
            await send_message(chat_id, "Отменено.", keyboard=_menu(is_admin))
            return
        if text.lower() in ("да", "yes", "y", "удали", "удалить"):
            _delpending.pop(chat_id, None)
            report = await _delete_last_broadcast()
            await send_message(chat_id, report, keyboard=_menu(is_admin))
            return
        await send_message(chat_id, "Чтобы удалить рассылку — ответьте «да». Отмена — /cancel.")
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

        if len(parts) > 1 and parts[1].lower() in ("мне", "себе"):
            count = 1
            if len(parts) > 2 and parts[2].isdigit():
                count = max(1, min(int(parts[2]), 20))
            codes = [await issue_tv_code(chat_id) for _ in range(count)]
            listed = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(codes))
            await send_message(chat_id, f"🔑 Коды (одноразовые, по одному на ТВ):\n{listed}")
            return
        target = parts[1] if len(parts) > 1 else str(chat_id)
        code = await issue_tv_code(target)
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
