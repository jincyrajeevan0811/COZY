from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, ExpressionWrapper, F, Q

from .models import ProductAttribute

SORT_OPTIONS = [
    ("latest", "Latest"),
    ("popular", "Popularity"),
    ("bestselling", "Best selling"),
    ("rating", "Top rated"),
    ("price_asc", "Price: low to high"),
    ("price_desc", "Price: high to low"),
    ("discount", "Biggest discount"),
]

SORT_MAP = {
    "latest": ["-created_at"],
    "popular": ["-view_count", "-sold_count"],
    "bestselling": ["-sold_count", "-created_at"],
    "rating": ["-avg_rating", "-review_count"],
    "price_asc": ["price"],
    "price_desc": ["-price"],
    "discount": ["-discount_ratio", "-created_at"],
}

FLAG_FILTERS = {
    "new": Q(is_new_arrival=True),
    "bestseller": Q(is_bestseller=True),
    "trending": Q(is_trending=True),
    "featured": Q(is_featured=True),
    "sale": Q(original_price__gt=F("price")),
}

COLLECTIONS = {
    "new-arrivals": ("New Arrivals", "new", "latest"),
    "best-sellers": ("Best Sellers", "bestseller", "bestselling"),
    "trending": ("Trending Now", "trending", "popular"),
    "featured": ("Featured Picks", "featured", "latest"),
    "offers": ("Special Offers", "sale", "discount"),
}


def _decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def search_q(query):
    """AND across words, OR across fields: name, SKU, keywords, category and description."""
    q = Q()
    for term in query.split()[:8]:
        q &= (
            Q(name__icontains=term)
            | Q(sku__iexact=term)
            | Q(tags__icontains=term)
            | Q(category__name__icontains=term)
            | Q(subcategory__name__icontains=term)
            | Q(short_description__icontains=term)
            | Q(material__value__icontains=term)
            | Q(color__value__icontains=term)
        )
    return q


def apply_filters(queryset, params):
    """Apply GET filters to a product queryset. Returns (queryset, active_filters dict)."""
    active = {}
    queryset = queryset.annotate(
        discount_ratio=ExpressionWrapper(
            (F("original_price") - F("price")) * 100 / F("original_price"),
            output_field=DecimalField(max_digits=6, decimal_places=2),
        )
    )

    q = (params.get("q") or "").strip()
    if q:
        queryset = queryset.filter(search_q(q))
        active["q"] = q

    sub = params.get("sub")
    if sub:
        queryset = queryset.filter(subcategory__slug=sub)
        active["sub"] = sub

    cat = params.get("category")
    if cat:
        queryset = queryset.filter(category__slug=cat)
        active["category"] = cat

    for attr in (ProductAttribute.COLOR, ProductAttribute.MATERIAL, ProductAttribute.STYLE):
        values = [v for v in params.getlist(attr) if v]
        if values:
            queryset = queryset.filter(**{f"{attr}__slug__in": values})
            active[attr] = values

    min_price, max_price = _decimal(params.get("min_price")), _decimal(params.get("max_price"))
    if min_price is not None:
        queryset = queryset.filter(price__gte=min_price)
        active["min_price"] = min_price
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)
        active["max_price"] = max_price

    if params.get("availability") == "in":
        queryset = queryset.filter(stock_total__gt=0)
        active["availability"] = "in"

    discount = _decimal(params.get("discount"))
    if discount:
        queryset = queryset.filter(original_price__gt=F("price"), discount_ratio__gte=discount)
        active["discount"] = discount

    flag = params.get("flag")
    if flag in FLAG_FILTERS:
        queryset = queryset.filter(FLAG_FILTERS[flag])
        active["flag"] = flag

    sort = params.get("sort") or "latest"
    if sort not in SORT_MAP:
        sort = "latest"
    queryset = queryset.order_by(*SORT_MAP[sort], "-id")
    return queryset.distinct(), active, sort
