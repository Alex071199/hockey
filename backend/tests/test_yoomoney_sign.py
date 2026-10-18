import hashlib
import hmac
from urllib.parse import quote

from app.api.donations import _verify_notification

# пример из документации ЮMoney (https://yoomoney.ru/docs/payment-buttons/using-api/notifications)
DOC_FIELDS = {
    "notification_type": "p2p-incoming",
    "operation_id": "441361714955017004",
    "amount": "98.00",
    "withdraw_amount": "100.00",
    "currency": "643",
    "datetime": "2013-12-26T08:28:34Z",
    "sender": "41000000000",
    "codepro": "false",
    "label": "ML23045",
    "unaccepted": "false",
    "sha1_hash": "ac13833bd6ba9eff1fa9e4bed76f3d6ebb57f6c0",
    "sign": "a452af731650e2c5b39abcdc7c28dd27db7b3b654c2230ad2c386e64afb98605",
}


def test_sign_new_format_matches_docs_example():
    assert _verify_notification(DOC_FIELDS, "secret123")


def test_sign_wrong_secret_rejected():
    assert not _verify_notification(DOC_FIELDS, "other-secret")


def test_sign_empty_secret_rejected():
    assert not _verify_notification(DOC_FIELDS, "")


def test_sign_without_sign_and_sha1_rejected():
    fields = {k: v for k, v in DOC_FIELDS.items() if k not in ("sign", "sha1_hash")}
    assert not _verify_notification(fields, "secret123")


def test_legacy_sha1_format():
    payload = (
        "p2p-incoming&441361714955017004&50.00&643"
        "&2026-10-18T11:00:00Z&41000000000&false&sec123&tv_123_456"
    )
    sha1_hash = hashlib.sha1(payload.encode()).hexdigest()
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "441361714955017004",
        "amount": "50.00",
        "currency": "643",
        "datetime": "2026-10-18T11:00:00Z",
        "sender": "41000000000",
        "codepro": "false",
        "label": "tv_123_456",
        "sha1_hash": sha1_hash,
    }
    assert _verify_notification(fields, "sec123")
    assert not _verify_notification(fields, "wrong")


def test_sign_verified_even_without_sha1_hash():
    # с 18.05.2026 ЮMoney присылает sign и может не присылать sha1_hash
    fields = {k: v for k, v in DOC_FIELDS.items() if k != "sha1_hash"}
    src = "&".join(
        f"{k}={quote(v, safe='')}"
        for k, v in sorted(fields.items())
        if k != "sign"
    )
    fields["sign"] = hmac.new(
        b"secret123", src.encode(), hashlib.sha256
    ).hexdigest()
    assert _verify_notification(fields, "secret123")
    assert not _verify_notification(fields, "wrong-secret")
