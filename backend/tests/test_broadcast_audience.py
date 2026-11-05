"""Аудитории рассылки: "all" (бот + колокольчик) и "app" (только владельцы ТВ-кодов)."""

from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from app import telegram
from app.database import async_session
from app.models import Broadcast, BroadcastDelivery, News, Subscriber, TvCode

SUB_CHAT = "999000111"
APP_CHAT = "999000222"
APP_TEXT = "__test_broadcast_for_app__"
ALL_TEXT = "__test_broadcast_for_all__"


async def _cleanup() -> None:
    async with async_session() as db:
        await db.execute(delete(Subscriber).where(Subscriber.chat_id == SUB_CHAT))
        await db.execute(delete(TvCode).where(TvCode.chat_id == APP_CHAT))
        await db.execute(delete(News).where(News.text.in_([APP_TEXT, ALL_TEXT])))
        for text in (APP_TEXT, ALL_TEXT):
            res = await db.execute(select(Broadcast.id).where(Broadcast.text == text))
            ids = [row[0] for row in res.all()]
            if ids:
                await db.execute(
                    delete(BroadcastDelivery).where(
                        BroadcastDelivery.broadcast_id.in_(ids)
                    )
                )
                await db.execute(delete(Broadcast).where(Broadcast.id.in_(ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_app_audience_goes_only_to_code_holders_without_site_news():
    await _cleanup()
    sent_to: list[str] = []

    async def fake_send(chat_id, text, keyboard=None):
        sent_to.append(str(chat_id))
        return 42

    try:
        async with async_session() as db:
            db.add(Subscriber(chat_id=SUB_CHAT, active=True))
            db.add(TvCode(code="__TEST_CODE_1__", chat_id=APP_CHAT))
            await db.commit()

        with patch.object(telegram, "send_message", fake_send):
            sent, failed = await telegram.broadcast(APP_TEXT, audience="app")

        # получил только владелец кода, подписчик — нет
        assert APP_CHAT in sent_to, "владелец кода должен получить рассылку"
        assert SUB_CHAT not in sent_to, "подписчик без кода получать не должен"
        assert sent == len(sent_to) and failed == 0

        async with async_session() as db:
            res = await db.execute(select(News).where(News.text == APP_TEXT))
            assert res.first() is None, "рассылка владельцам ТВ не должна попасть на сайт"

            res = await db.execute(
                select(Broadcast).where(Broadcast.text == APP_TEXT)
            )
            bcast = res.scalar_one()
            assert bcast.news_id is None
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_all_audience_reaches_subscribers_and_site():
    await _cleanup()
    sent_to: list[str] = []

    async def fake_send(chat_id, text, keyboard=None):
        sent_to.append(str(chat_id))
        return 42

    try:
        async with async_session() as db:
            db.add(Subscriber(chat_id=SUB_CHAT, active=True))
            db.add(TvCode(code="__TEST_CODE_2__", chat_id=APP_CHAT))
            await db.commit()

        with patch.object(telegram, "send_message", fake_send):
            sent, failed = await telegram.broadcast(ALL_TEXT, audience="all")

        # подписчики получают, владелец кода без подписки — нет
        assert SUB_CHAT in sent_to, "подписчик должен получить общую рассылку"
        assert APP_CHAT not in sent_to, "не-подписчик не должен попадать в «всем»"
        assert sent == len(sent_to) and failed == 0

        async with async_session() as db:
            res = await db.execute(select(News).where(News.text == ALL_TEXT))
            assert res.first() is not None, "общая рассылка должна попасть в колокольчик"

            res = await db.execute(
                select(Broadcast).where(Broadcast.text == ALL_TEXT)
            )
            bcast = res.scalar_one()
            assert bcast.news_id is not None
    finally:
        await _cleanup()
