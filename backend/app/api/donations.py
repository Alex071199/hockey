import hashlib
import hmac
import logging
import time
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tv_auth import issue_tv_code, mark_payment_seen
from app.config import settings
from app.database import get_db
from app.models import Donation, Match
from app.ws import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["donations"])

_last_rain_at: float = 0
RAIN_COOLDOWN = 20
# окно, в котором событие отдаётся ВСЕМ поллерам (не consumed)
RAIN_TTL = 15


_rain_event: dict | None = None


def _rain_duration(amount: int) -> float:
    """Секунды показа дождя: чем больше донат, тем дольше (6..30с)."""
    return max(6.0, min(30.0, 5.0 + amount * 0.009))


def _new_rain_event(
    match_id: int, team: str, amount: int, donor: str, message: str = ""
) -> dict:
    now = time.time()
    duration = round(_rain_duration(amount), 1)
    return {
        "id": int(now * 1000),
        "team": team,
        "amount": amount,
        "donor": donor,
        "message": message,
        "match_id": match_id,
        "ts": now,
        "duration": duration,
        # событие доступно поллерам дольше показа (поллер раз в 3 сек)
        "ttl": round(min(45.0, duration + 10.0), 1),
    }


class DonationCreate(BaseModel):
    match_id: int
    team: str
    amount: int
    donor_name: str = "Аноним"


@router.post("/donations/create")
async def create_donation(
    data: DonationCreate,
    db: AsyncSession = Depends(get_db),
):
    match = (await db.execute(select(Match).where(Match.id == data.match_id))).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if data.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum donation is 100 RUB")

    # вебхук получает только label — кодируем в него сторону (h/a),
    # иначе команда доната не определить
    side = "h" if data.team == match.team_home else "a"
    label = f"{data.match_id}_{side}_{int(time.time() * 1000)}"

    # после оплаты ЮMoney редиректит на successURL; ведём на страницу-посредник,
    # которая в режиме popup шлёт сообщение в открытую вкладку матча
    match_url = f"https://www.hockey-live.online/{match.league.lower()}/match/{match.id}"
    success_url = f"https://www.hockey-live.online/donate-success?back={quote(match_url, safe='')}"

    # https://yoomoney.ru/docs/payment-buttons/using-api/forms:
    # обязательны receiver, quickpay-form, paymentType, sum; отправка POST.
    fields = {
        "receiver": settings.YOOMONEY_WALLET,
        "quickpay-form": "button",
        "paymentType": "AC",
        "sum": str(data.amount),
        "label": label,
        "targets": data.team,
        "successURL": success_url,
    }

    return {
        "form_action": "https://yoomoney.ru/quickpay/confirm",
        "fields": fields,
        "label": label,
    }


def _verify_notification(fields: dict[str, str], secret: str) -> bool:
    """Проверка подписи уведомления ЮMoney.

    Новый формат (с 18.05.2026): sign = HMAC-SHA256 в HEX по строке из
    URL-кодированных (RFC 3986) значений всех параметров, кроме sign,
    отсортированных по алфавиту и склеенных через `&` в виде `key=value`.
    Старый формат: sha1(notification_type&operation_id&amount&currency&
    datetime&sender&codepro&secret&label).
    """
    if not secret:
        return False
    sign = fields.get("sign", "")
    if sign:
        sign_src = "&".join(
            f"{key}={quote(val, safe='')}"
            for key, val in sorted(fields.items())
            if key != "sign"
        )
        expected = hmac.new(secret.encode(), sign_src.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sign)
    sha1_hash = fields.get("sha1_hash", "")
    if sha1_hash:
        payload = (
            f"{fields.get('notification_type', '')}&{fields.get('operation_id', '')}"
            f"&{fields.get('amount', '')}&{fields.get('currency', '')}"
            f"&{fields.get('datetime', '')}&{fields.get('sender', '')}"
            f"&{fields.get('codepro', 'false')}&{secret}"
            f"&{fields.get('label', '')}"
        )
        expected = hashlib.sha1(payload.encode()).hexdigest()
        return hmac.compare_digest(expected, sha1_hash)
    return False


@router.post("/donations/webhook")
async def yoomoney_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    fields = {str(k): str(v) for k, v in form.multi_items()}

    notification_type = fields.get("notification_type", "")
    operation_id = fields.get("operation_id", "")
    amount_str = fields.get("amount", "")
    currency = fields.get("currency", "")
    dt = fields.get("datetime", "")
    sender = fields.get("sender", "")
    codepro = fields.get("codepro", "false")
    label = fields.get("label", "")
    sha1_hash = fields.get("sha1_hash", "")
    sign = fields.get("sign", "")

    secret = settings.YOOMONEY_SECRET
    signature_ok = _verify_notification(fields, secret)

    if not signature_ok:
        logger.warning(
            "Donation webhook: invalid signature; has_sign=%s has_sha1=%s "
            "secret_len=%d fields=%s",
            bool(sign),
            bool(sha1_hash),
            len(secret),
            {k: v for k, v in fields.items() if k not in ("sign", "sha1_hash")},
        )
        raise HTTPException(status_code=403, detail="Invalid signature")

    if codepro == "true":
        return {"status": "ok"}

    try:
        amount = int(float(amount_str))
    except (ValueError, TypeError):
        amount = 0

    # TV-активация: label вида tv_<chat_id>_<ts> — отдельный путь платежа,
    # идёт ДО матчевого парсинга (match_id там не число)
    if label.startswith("tv_"):
        tv_parts = label.split("_", 2)
        tv_chat = tv_parts[1] if len(tv_parts) > 1 else ""
        if amount < 50:
            logger.warning("TV webhook: amount %d < 50 RUB, ignored", amount)
            return {"status": "ok"}
        if not tv_chat:
            return {"status": "ok"}
        if not await mark_payment_seen(operation_id):
            return {"status": "ok"}
        code = await issue_tv_code(tv_chat)
        from app.telegram import send_message

        await send_message(
            tv_chat,
            "✅ Оплата получена!\n\n"
            f"Код активации для ТВ: {code}\n\n"
            "Введите его в приложении на телевизоре.\n"
            "Код одноразовый — работает только один раз.",
        )
        logger.info("TV code sent to chat_id=%s", tv_chat)
        return {"status": "ok"}

    parts = label.split("_")
    match_id = int(parts[0]) if parts and parts[0].isdigit() else 0
    side = parts[1] if len(parts) > 1 and parts[1] in ("h", "a") else ""

    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        logger.warning("Donation webhook: match %s not found", match_id)
        return {"status": "ok"}

    if side == "h":
        team = match.team_home
    elif side == "a":
        team = match.team_away
    else:
        team = match.team_home if match.team_home in label else match.team_away

    donation = Donation(
        match_id=match.id,
        team=team,
        amount=amount,
        donor_name="Аноним",
    )
    db.add(donation)
    await db.commit()

    global _last_rain_at, _rain_event
    now = time.time()
    if now - _last_rain_at >= RAIN_COOLDOWN:
        _last_rain_at = now
        _rain_event = _new_rain_event(match.id, team, amount, "Аноним")
        logger.info("Donation rain: %s %d RUB", team, amount)

    return {"status": "ok"}


class DonationConfirm(BaseModel):
    match_id: int
    team: str
    amount: int
    tx_id: str = ""
    # имя/комментарий из полей формы CloudTips (если включены на странице)
    donor_name: str = ""
    message: str = ""


@router.post("/donations/confirm")
async def confirm_donation(
    data: DonationConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Подтверждение оплаты CloudTips.

    У CloudTips нет вебхука — после успеха в iframe браузер шлёт сообщение,
    и страница матча дёргает этот endpoint. Защита от накрутки счётчика:
    валидация команды/суммы против матча и дедуп по tx_id.
    """
    match = (await db.execute(select(Match).where(Match.id == data.match_id))).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if data.team not in (match.team_home, match.team_away):
        raise HTTPException(status_code=400, detail="Unknown team for this match")
    if not (100 <= data.amount <= 100000):
        raise HTTPException(status_code=400, detail="Invalid amount")

    if data.tx_id:
        dup = (
            await db.execute(select(Donation.id).where(Donation.tx_id == data.tx_id))
        ).scalar_one_or_none()
        if dup:
            return {"status": "ok", "duplicate": True}

    donor = (data.donor_name or "").strip()[:50] or "Аноним"
    message = (data.message or "").strip()[:200]

    donation = Donation(
        match_id=match.id,
        team=data.team,
        amount=data.amount,
        donor_name=donor,
        tx_id=data.tx_id or None,
        message=message or None,
    )
    db.add(donation)
    await db.commit()

    global _last_rain_at, _rain_event
    now = time.time()
    if now - _last_rain_at >= RAIN_COOLDOWN:
        _last_rain_at = now
        _rain_event = _new_rain_event(match.id, data.team, data.amount, donor, message)
        logger.info("Donation rain (cloudtips): %s %d RUB", data.team, data.amount)

    return {"status": "ok"}


@router.get("/donations/top/{match_id}")
async def get_top_donations(
    match_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Donation.team, Donation.amount)
        .where(Donation.match_id == match_id)
        .order_by(Donation.created_at.desc())
        .limit(20)
    )
    rows = result.all()
    return [{"team": r[0], "amount": r[1]} for r in rows]


@router.get("/donations/score/{match_id}")
async def get_donation_score(
    match_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Суммы донатов по сторонам для 'соревнования болельщиков'."""
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    result = await db.execute(
        select(Donation.team, func.sum(Donation.amount))
        .where(Donation.match_id == match_id)
        .group_by(Donation.team)
    )
    sums = {team: int(total or 0) for team, total in result.all()}

    # вебхук пишет ровно team_home/team_away; старые записи (до фикса
    # стороны) могли попасть не под той командой — суммируем по имени
    home = sums.get(match.team_home, 0)
    away = sums.get(match.team_away, 0)
    unknown = sum(v for k, v in sums.items() if k not in (match.team_home, match.team_away))
    if unknown:
        away += unknown

    return {
        "home": {"name": match.team_home, "amount": home},
        "away": {"name": match.team_away, "amount": away},
    }


@router.post("/donations/test-rain")
async def test_rain(match_id: int = 0, amount: int = 500, message: str = "Проверка сообщения"):
    global _rain_event
    _rain_event = _new_rain_event(match_id, "Авангард", amount, "Тест", message)
    return {"status": "ok"}


@router.get("/donations/rain/{match_id}")
async def get_rain(match_id: int):
    global _rain_event
    if _rain_event and _rain_event.get("match_id") == match_id:
        ttl = _rain_event.get("ttl", RAIN_TTL)
        if time.time() - _rain_event.get("ts", 0) > ttl:
            _rain_event = None
            return {"rain": None}
        # НЕ забираем событие: его должны получить все, кто смотрит матч
        return {"rain": _rain_event}
    return {"rain": None}
