import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .models import ServiceablePincode, ShippingMethod

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


def check_pincode(pincode):
    """Return a dict describing serviceability for a PIN code (longest-prefix match)."""
    pincode = (pincode or "").strip()
    if not PIN_RE.match(pincode):
        return {"valid": False, "serviceable": False, "cod": False, "extra_days": 0, "message": "Enter a valid 6-digit PIN code."}
    rules = ServiceablePincode.objects.all()
    if not rules.exists():
        return {"valid": True, "serviceable": True, "cod": True, "extra_days": 0, "message": "Delivery available."}
    candidates = [pincode[:i] for i in range(6, 0, -1)]
    match = None
    rules_by_prefix = {r.pincode_prefix: r for r in rules.filter(pincode_prefix__in=candidates)}
    for prefix in candidates:
        if prefix in rules_by_prefix:
            match = rules_by_prefix[prefix]
            break
    if not match or not match.is_serviceable:
        return {"valid": True, "serviceable": False, "cod": False, "extra_days": 0,
                "message": "Sorry, we do not deliver to this PIN code yet."}
    location = ", ".join(p for p in [match.city, match.state] if p)
    return {
        "valid": True,
        "serviceable": True,
        "cod": match.cod_available,
        "extra_days": match.extra_days,
        "message": f"Delivery available{(' to ' + location) if location else ''}.",
    }


def estimate_delivery(method=None, extra_days=0):
    method = method or ShippingMethod.objects.filter(is_active=True).first()
    today = timezone.localdate()
    min_days = (method.min_days if method else 3) + extra_days
    max_days = (method.max_days if method else 7) + extra_days
    return today + timedelta(days=min_days), today + timedelta(days=max_days)


def default_delivery_estimate():
    start, end = estimate_delivery()
    return {"start": start, "end": end}


def shipping_charge(method, subtotal):
    """Shipping charge for a method and an order subtotal (after discounts)."""
    from apps.website_settings.models import WebsiteSetting

    if method is None:
        return Decimal("0")
    threshold = method.free_above
    if threshold is None:
        threshold = WebsiteSetting.load().free_shipping_threshold
    if threshold is not None and threshold > 0 and subtotal >= threshold:
        return Decimal("0")
    return method.charge


def active_methods():
    return ShippingMethod.objects.filter(is_active=True)
