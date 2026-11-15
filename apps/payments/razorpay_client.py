"""
Minimal Razorpay REST client (no SDK dependency).

Security rules followed here:
  * Card / UPI details never touch our servers — Razorpay Checkout collects them.
  * Payments are only treated as successful after the HMAC-SHA256 signature is verified
    on the server with the key secret (and webhooks with the webhook secret).
"""
import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    pass


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _request(method, path, payload=None):
    if not is_configured():
        raise RazorpayError("Razorpay keys are not configured.")
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="ignore")
        logger.error("Razorpay API error %s: %s", exc.code, body)
        try:
            message = json.loads(body).get("error", {}).get("description") or body
        except ValueError:
            message = body
        raise RazorpayError(message) from exc
    except urllib.error.URLError as exc:
        logger.error("Razorpay connection error: %s", exc)
        raise RazorpayError("Could not connect to the payment gateway. Please try again.") from exc


def create_order(amount, receipt, notes=None):
    return _request("POST", "/orders", {
        "amount": to_paise(amount),
        "currency": "INR",
        "receipt": receipt[:40],
        "notes": notes or {},
    })


def fetch_payment(payment_id):
    return _request("GET", f"/payments/{payment_id}")


def create_refund(payment_id, amount, notes=None):
    return _request("POST", f"/payments/{payment_id}/refund", {"amount": to_paise(amount), "notes": notes or {}})


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, signature):
    if not (razorpay_order_id and razorpay_payment_id and signature and settings.RAZORPAY_KEY_SECRET):
        return False
    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
