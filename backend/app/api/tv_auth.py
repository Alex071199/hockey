"""TV-активация: одноразовые 6-значные коды за донат от 50 ₽ (ЮMoney).

Схема:
1. Пользователь в боте нажимает «Подключить ТВ» → получает ссылку на
   страницу оплаты /tv-pay?chat_id=... (форма ЮMoney, label tv_<chat_id>_<ts>).
2. ЮMoney шлёт вебхук в /api/donations/webhook — ветка label tv_ выдаёт код
   и отправляет его пользователю в бот.
3. Код лежит в tv_codes.json (файл вне git — доступен только серверу).
4. Приложение на ТВ шлёт POST /api/tv/activate — код удаляется из файла
   (одноразовый) и приложение разблокируется.
"""

import json
import logging
import random
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tv-auth"])

TV_CODES_FILE = Path(__file__).resolve().parents[2] / "tv_codes.json"
MIN_AMOUNT = 50


def _load() -> dict:
    try:
        data = json.loads(TV_CODES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("codes", [])
            data.setdefault("ops", [])
            return data
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("tv_codes read failed: %s", e)
    return {"codes": [], "ops": []}


def _save(data: dict) -> None:
    TV_CODES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def issue_tv_code(chat_id: str | int) -> str:
    """Сгенерировать 6-значный код и положить в файл (одноразовый)."""
    data = _load()
    existing = {c.get("code") for c in data["codes"]}
    while True:
        code = str(random.randint(100000, 999999))
        if code not in existing:
            break
    data["codes"].append(
        {"code": code, "chat_id": str(chat_id), "created": int(time.time())}
    )
    _save(data)
    logger.info("TV code issued for chat_id=%s", chat_id)
    return code


def consume_tv_code(code: str) -> bool:
    """Удалить код из файла после активации на ТВ. False — кода нет/использован."""
    data = _load()
    before = len(data["codes"])
    data["codes"] = [c for c in data["codes"] if c.get("code") != code]
    if len(data["codes"]) == before:
        return False
    _save(data)
    return True


def mark_payment_seen(operation_id: str) -> bool:
    """Дедуп вебхуков ЮMoney. True — платёж ещё не обрабатывался."""
    if not operation_id:
        return True
    data = _load()
    if operation_id in data["ops"]:
        return False
    data["ops"].append(operation_id)
    data["ops"] = data["ops"][-500:]
    _save(data)
    return True


class TvRequest(BaseModel):
    chat_id: str


class TvActivate(BaseModel):
    code: str


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
    """Активация на ТВ: код проверяется и сразу удаляется из файла."""
    code = data.code.strip()
    if not (code.isdigit() and len(code) == 6):
        raise HTTPException(status_code=400, detail="Код состоит из 6 цифр")
    if not consume_tv_code(code):
        raise HTTPException(status_code=410, detail="Код не найден или уже использован")
    return {"ok": True}
