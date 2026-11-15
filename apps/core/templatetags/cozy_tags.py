from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def _indian_grouping(integer_part: str) -> str:
    if len(integer_part) <= 3:
        return integer_part
    last3 = integer_part[-3:]
    rest = integer_part[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups) + "," + last3


@register.filter
def inr(value, decimals=None):
    """Format a number as Indian Rupees: ₹1,23,456.00 (drops .00 when decimals='auto')."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    negative = amount < 0
    amount = abs(amount).quantize(Decimal("0.01"))
    integer, _, fraction = f"{amount:.2f}".partition(".")
    text = _indian_grouping(integer)
    if not (decimals == "auto" and fraction == "00"):
        text = f"{text}.{fraction}"
    return f"{'-' if negative else ''}₹{text}"


@register.filter
def stars(rating):
    """Render a 0-5 rating as Bootstrap Icons stars."""
    try:
        rating = float(rating or 0)
    except (TypeError, ValueError):
        rating = 0
    html = []
    for i in range(1, 6):
        if rating >= i:
            html.append('<i class="bi bi-star-fill"></i>')
        elif rating >= i - 0.5:
            html.append('<i class="bi bi-star-half"></i>')
        else:
            html.append('<i class="bi bi-star"></i>')
    return mark_safe(f'<span class="stars" aria-label="{rating:.1f} out of 5">{"".join(html)}</span>')


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def multiply(value, arg):
    try:
        return Decimal(value) * Decimal(arg)
    except (InvalidOperation, TypeError, ValueError):
        return ""


@register.filter
def percent_of(value, total):
    try:
        total = Decimal(total)
        return round(Decimal(value) * 100 / total) if total else 0
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Return the current querystring with some parameters replaced (used by filters/pagination)."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    if "page" not in kwargs:
        query.pop("page", None)
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag
def status_badge(status, label=None):
    colors = {
        "pending": "warning", "confirmed": "info", "processing": "info", "packed": "primary",
        "shipped": "primary", "out_for_delivery": "primary", "delivered": "success",
        "cancelled": "danger", "return_requested": "warning", "returned": "secondary",
        "refunded": "secondary", "paid": "success", "failed": "danger", "captured": "success",
        "created": "warning", "open": "warning", "in_progress": "info", "resolved": "success",
        "closed": "secondary", "approved": "success", "rejected": "danger", "requested": "warning",
        "received": "info", "processed": "success", "partially_refunded": "secondary",
    }
    color = colors.get(str(status), "light")
    return format_html('<span class="badge rounded-pill badge-soft-{}">{}</span>', color, label or str(status).replace("_", " ").title())


@register.simple_tag(takes_context=True)
def url_without(context, key):
    """Current querystring without `key` (and without page)."""
    query = context["request"].GET.copy()
    query.pop(key, None)
    query.pop("page", None)
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"


FILTER_LABELS = {
    "sub": "Type", "category": "Category", "color": "Colour", "material": "Material", "style": "Style",
    "min_price": "Min ₹", "max_price": "Max ₹", "availability": "In stock", "discount": "Discount %", "flag": "Collection",
}


@register.filter
def filter_label(key):
    return FILTER_LABELS.get(key, str(key).replace("_", " ").title())


@register.filter
def display_value(value):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v).replace("-", " ").title() for v in value)
    return str(value).replace("-", " ")


@register.filter
def split_tags(value):
    return [t.strip() for t in str(value or "").split(",") if t.strip()]
