"""TV-активация: одноразовые 6-значные коды за донат от 50 ₽ (ЮMoney).

Схема:
1. Пользователь в боте нажимает «Подключить ТВ» → получает ссылку на
   страницу оплаты /tv-pay?chat_id=... (форма ЮMoney, label tv_<chat_id>_<ts>).
2. ЮMoney шлёт вебхук в /api/donations/webhook — ветка label tv_ выдаёт код
   и отправляет его пользователю в бот.
3. Код лежит в БД (таблица tv_codes). Раньше он лежал в tv_codes.json
   ВНУТРИ контейнера Railway и стирался при каждом деплое — из-за этого
   только что выданные коды «не подходили» на ТВ.
4. Приложение на ТВ шлёт POST /api/tv/activate — код удаляется из БД
   (одноразовый) и приложение разблокируется.
"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session
from app.models import TvCode, TvDevice, TvPaymentOp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tv-auth"])

# Старое файловое хранилище: при старте переносится в БД (если файл ещё есть)
TV_CODES_FILE = Path(__file__).resolve().parents[2] / "tv_codes.json"
MIN_AMOUNT = 50

_migrated = False
_migrate_lock = asyncio.Lock()


async def migrate_legacy_store() -> None:
    """Переносит tv_codes.json в БД (идемпотентно, при старте).

    Файл жил в контейнере и пропадал при каждом деплое: вместе с ним
    исчезали неиспользованные коды и активации устройств. Теперь всё
    хранится в БД и переживает деплои и рестарты.
    """
    global _migrated
    if _migrated:
        return
    async with _migrate_lock:
        if _migrated:
            return
        try:
            data = json.loads(TV_CODES_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            async with async_session() as db:
                for item in data.get("codes") or []:
                    code = str(item.get("code") or "").strip()
                    if not code:
                        continue
                    exists = (
                        await db.execute(select(TvCode.code).where(TvCode.code == code))
                    ).scalar()
                    if not exists:
                        db.add(TvCode(code=code, chat_id=str(item.get("chat_id") or "")))
                for did in data.get("devices") or []:
                    did = str(did).strip()
                    if not did:
                        continue
                    exists = (
                        await db.execute(
                            select(TvDevice.device_id).where(TvDevice.device_id == did)
                        )
                    ).scalar()
                    if not exists:
                        db.add(TvDevice(device_id=did))
                for op in (data.get("ops") or [])[-500:]:
                    op = str(op)
                    exists = (
                        await db.execute(
                            select(TvPaymentOp.op_id).where(TvPaymentOp.op_id == op)
                        )
                    ).scalar()
                    if not exists:
                        db.add(TvPaymentOp(op_id=op))
                await db.commit()
            logger.info("TV store migrated from %s", TV_CODES_FILE)
        _migrated = True


async def issue_tv_code(chat_id: str | int) -> str:
    """Сгенерировать 6-значный код и положить в БД (одноразовый)."""
    await migrate_legacy_store()
    async with async_session() as db:
        for _ in range(100):
            code = str(random.randint(100000, 999999))
            exists = (
                await db.execute(select(TvCode.code).where(TvCode.code == code))
            ).scalar()
            if exists:
                continue
            db.add(TvCode(code=code, chat_id=str(chat_id)))
            await db.commit()
            logger.info("TV code issued for chat_id=%s", chat_id)
            return code
    raise RuntimeError("не удалось подобрать свободный код")


async def consume_tv_code(code: str) -> bool:
    """Удалить код из БД после активации на ТВ. False — кода нет/использован."""
    await migrate_legacy_store()
    async with async_session() as db:
        res = await db.execute(delete(TvCode).where(TvCode.code == code))
        await db.commit()
        return bool(res.rowcount)


async def mark_payment_seen(operation_id: str) -> bool:
    """Дедуп вебхуков ЮMoney. True — платёж ещё не обрабатывался."""
    if not operation_id:
        return True
    await migrate_legacy_store()
    async with async_session() as db:
        exists = (
            await db.execute(
                select(TvPaymentOp.op_id).where(TvPaymentOp.op_id == operation_id)
            )
        ).scalar()
        if exists:
            return False
        db.add(TvPaymentOp(op_id=operation_id))
        await db.commit()
        # держим только последние 500 операций
        extra = (
            await db.execute(
                select(TvPaymentOp.op_id)
                .order_by(TvPaymentOp.created_at.desc(), TvPaymentOp.op_id.desc())
                .offset(500)
            )
        ).scalars().all()
        if extra:
            await db.execute(delete(TvPaymentOp).where(TvPaymentOp.op_id.in_(extra)))
            await db.commit()
    return True


class TvRequest(BaseModel):
    chat_id: str


class TvActivate(BaseModel):
    code: str
    device_id: str | None = None


@router.post("/tv/request")
async def tv_payment_request(data: TvRequest):
    """Форма оплаты ЮMoney для активации ТВ (label tv_<chat_id>_<ts>)."""
    chat_id = data.chat_id.strip()
    if not chat_id or not chat_id.lstrip("-").isdigit():
        raise HTTPException(status_code=400, detail="bad chat_id")
    if not settings.YOOMONEY_WALLET:
        raise HTTPException(status_code=500, detail="YOOMONEY_WALLET not configured")

    label = f"tv_{chat_id}_{int(time.time() * 1000)}"
    fields = {
        "receiver": settings.YOOMONEY_WALLET,
        "quickpay-form": "button",
        "paymentType": "AC",
        "sum": str(MIN_AMOUNT),
        "label": label,
        "targets": "Активация ТВ",
        "successURL": "https://www.hockey-live.online/tv-pay?done=1",
    }
    return {
        "form_action": "https://yoomoney.ru/quickpay/confirm",
        "fields": fields,
        "sum": MIN_AMOUNT,
    }


@router.post("/tv/activate")
async def tv_activate(data: TvActivate):
    """Активация на ТВ: код проверяется и сразу удаляется из файла.

    device_id запоминается — после обновления/переустановки приложение
    восстановит авторизацию запросом /api/tv/status.
    """
    code = data.code.strip()
    if not (code.isdigit() and len(code) == 6):
        raise HTTPException(status_code=400, detail="Код состоит из 6 цифр")
    if not await consume_tv_code(code):
        raise HTTPException(status_code=410, detail="Код не найден или уже использован")
    did = (data.device_id or "").strip()
    if did:
        async with async_session() as db:
            exists = (
                await db.execute(
                    select(TvDevice.device_id).where(TvDevice.device_id == did)
                )
            ).scalar()
            if not exists:
                db.add(TvDevice(device_id=did))
                await db.commit()
        logger.info("TV device bound: %s", did)
    return {"ok": True}


@router.get("/tv/status")
async def tv_status(device_id: str = Query(..., description="Device UUID")):
    """Была ли активация этого устройства (восстановление после обновления)."""
    did = device_id.strip()
    if not did:
        raise HTTPException(status_code=400, detail="bad device_id")
    async with async_session() as db:
        exists = (
            await db.execute(
                select(TvDevice.device_id).where(TvDevice.device_id == did)
            )
        ).scalar()
    return {"authorized": bool(exists)}
