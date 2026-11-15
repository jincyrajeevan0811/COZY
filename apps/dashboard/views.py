"""Dashboard overview, analytics API, staff notifications, audit log and site settings."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncYear
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.rbac import permission_required, staff_required
from apps.categories.models import Category
from apps.inventory.models import Inventory
from apps.orders.models import Order, OrderItem
from apps.payments.models import Refund
from apps.products.models import Product
from apps.website_settings.context_processors import clear_site_caches
from apps.website_settings.models import WebsiteSetting

from .audit import log_activity
from .forms import WebsiteSettingForm
from .models import AdminActivityLog

PAID_STATES = ["paid", "partially_refunded"]


def _revenue(qs):
    return qs.filter(payment_status__in=PAID_STATES).aggregate(t=Sum("grand_total"))["t"] or Decimal("0")


def _sellable_inventory():
    return Inventory.objects.filter(product__is_active=True).filter(
        Q(variant__isnull=True, product__has_variants=False) | Q(variant__is_active=True, product__has_variants=True)
    )


@staff_required
def home(request):
    user = request.user
    if not user.has_access("dashboard.view"):
        return render(request, "dashboard/no_access.html", status=403)
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    orders = Order.objects.all()
    refunds_total = Refund.objects.filter(status="processed").aggregate(t=Sum("amount"))["t"] or Decimal("0")
    inv = _sellable_inventory()

    stats = {
        "total_revenue": _revenue(orders) - refunds_total,
        "today_sales": _revenue(orders.filter(created_at__gte=today_start)),
        "month_sales": _revenue(orders.filter(created_at__gte=month_start)),
        "today_orders": orders.filter(created_at__gte=today_start).count(),
        "total_orders": orders.count(),
        "pending_orders": orders.filter(status=Order.PENDING).count(),
        "processing_orders": orders.filter(status__in=[Order.CONFIRMED, Order.PROCESSING, Order.PACKED]).count(),
        "shipped_orders": orders.filter(status__in=[Order.SHIPPED, Order.OUT_FOR_DELIVERY]).count(),
        "delivered_orders": orders.filter(status=Order.DELIVERED).count(),
        "cancelled_orders": orders.filter(status=Order.CANCELLED).count(),
        "return_requests": orders.filter(status=Order.RETURN_REQUESTED).count(),
        "total_customers": User.objects.filter(Q(role__isnull=True) | Q(role__is_staff_role=False), is_superuser=False).count(),
        "active_customers": User.objects.filter(orders__created_at__gte=now - timedelta(days=90)).distinct().count(),
        "total_products": Product.objects.count(),
        "active_products": Product.objects.filter(is_active=True).count(),
        "out_of_stock": inv.filter(quantity=0).count(),
        "low_stock": inv.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold")).count(),
        "total_categories": Category.objects.count(),
        "pending_refunds": Refund.objects.filter(status="pending").count(),
    }
    month_prev_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_month_sales = _revenue(orders.filter(created_at__gte=month_prev_start, created_at__lt=month_start))
    stats["month_growth"] = (
        round((stats["month_sales"] - prev_month_sales) * 100 / prev_month_sales, 1) if prev_month_sales else None
    )

    best_sellers = (
        OrderItem.objects.exclude(order__status__in=[Order.CANCELLED])
        .filter(product__isnull=False)
        .values("product_id", "product_name")
        .annotate(qty=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-qty")[:6]
    )
    context = {
        "stats": stats,
        "recent_orders": Order.objects.select_related("user")[:8],
        "recent_customers": User.objects.filter(Q(role__isnull=True) | Q(role__is_staff_role=False)).order_by("-date_joined")[:6],
        "best_sellers": best_sellers,
        "low_stock_items": inv.filter(quantity__lte=F("low_stock_threshold")).select_related("product", "variant")
                              .order_by("quantity")[:6],
    }
    return render(request, "dashboard/home.html", context)


@permission_required("dashboard.view")
def chart_data(request):
    """JSON for dashboard charts — always computed from real orders."""
    period = request.GET.get("period", "daily")
    now = timezone.localtime()
    paid = Order.objects.filter(payment_status__in=PAID_STATES)
    if period == "weekly":
        start = now - timedelta(weeks=12)
        trunc, fmt = TruncWeek("created_at"), "%d %b"
    elif period == "monthly":
        start = (now - timedelta(days=365)).replace(day=1)
        trunc, fmt = TruncMonth("created_at"), "%b %Y"
    elif period == "yearly":
        start = now.replace(year=now.year - 4, month=1, day=1)
        trunc, fmt = TruncYear("created_at"), "%Y"
    else:
        period = "daily"
        start = now - timedelta(days=13)
        trunc, fmt = TruncDate("created_at"), "%d %b"
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        paid.filter(created_at__gte=start).annotate(bucket=trunc).values("bucket")
        .annotate(revenue=Sum("grand_total"), orders=Count("id")).order_by("bucket")
    )
    data = {}
    for row in rows:
        bucket = row["bucket"]
        key = bucket.strftime(fmt) if bucket else ""
        data[key] = (float(row["revenue"] or 0), row["orders"])

    # Fill gaps so the chart has a continuous axis.
    labels = []
    if period == "daily":
        labels = [(start + timedelta(days=i)).strftime(fmt) for i in range(14)]
    elif period == "weekly":
        first = (start - timedelta(days=start.weekday()))
        labels = [(first + timedelta(weeks=i)).strftime(fmt) for i in range(13)]
    elif period == "monthly":
        y, m = start.year, start.month
        for _ in range(13):
            labels.append(datetime(y, m, 1).strftime(fmt))
            m += 1
            if m > 12:
                y, m = y + 1, 1
    else:
        labels = [str(start.year + i) for i in range(5)]
    for key in data:
        if key not in labels:
            labels.append(key)

    status_counts = dict(Order.objects.values_list("status").annotate(n=Count("id")))
    status_labels = dict(Order.STATUS_CHOICES)
    categories = (
        OrderItem.objects.exclude(order__status=Order.CANCELLED).filter(product__isnull=False)
        .values("product__category__name").annotate(revenue=Sum("line_total")).order_by("-revenue")[:6]
    )
    products = (
        OrderItem.objects.exclude(order__status=Order.CANCELLED)
        .values("product_name").annotate(qty=Sum("quantity")).order_by("-qty")[:6]
    )
    return JsonResponse({
        "sales": {
            "labels": labels,
            "revenue": [data.get(lbl, (0, 0))[0] for lbl in labels],
            "orders": [data.get(lbl, (0, 0))[1] for lbl in labels],
        },
        "status": {
            "labels": [status_labels.get(s, s) for s in status_counts],
            "values": list(status_counts.values()),
        },
        "categories": {
            "labels": [c["product__category__name"] for c in categories],
            "values": [float(c["revenue"] or 0) for c in categories],
        },
        "products": {
            "labels": [p["product_name"][:28] for p in products],
            "values": [p["qty"] for p in products],
        },
    })


@staff_required
def notifications(request):
    qs = request.user.notifications.filter(is_staff_alert=True)
    if request.method == "POST":
        qs.filter(is_read=False).update(is_read=True)
        return redirect("dashboard:notifications")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "dashboard/notifications.html", {"page_obj": page})


@permission_required("audit.view")
def audit_log(request):
    qs = AdminActivityLog.objects.select_related("user")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(object_repr__icontains=q) | Q(description__icontains=q) | Q(user__email__icontains=q))
    if request.GET.get("action"):
        qs = qs.filter(action=request.GET["action"])
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(request, "dashboard/audit_log.html", {"page_obj": page, "q": q,
                                                        "actions": AdminActivityLog.ACTION_CHOICES})


@permission_required("settings.manage")
def site_settings(request):
    instance = WebsiteSetting.load()
    instance = WebsiteSetting.objects.get(pk=instance.pk)
    form = WebsiteSettingForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        clear_site_caches()
        log_activity(request, "update", instance, "Website settings updated")
        messages.success(request, "Website settings saved.")
        return redirect("dashboard:settings")
    groups = [
        ("Brand", ["site_name", "tagline", "logo", "favicon", "announcement_text", "announcement_active"]),
        ("Contact", ["contact_email", "contact_phone", "whatsapp_number", "address", "business_hours", "gstin"]),
        ("Commerce", ["currency_symbol", "free_shipping_threshold", "tax_percent", "prices_include_tax", "cod_enabled",
                      "cod_max_order_value", "cod_extra_charge", "gift_wrap_enabled", "gift_wrap_charge",
                      "return_window_days", "return_policy_summary", "low_stock_threshold"]),
        ("Homepage story & newsletter", ["brand_title", "brand_text", "brand_image", "newsletter_title", "newsletter_text"]),
        ("Footer & social", ["footer_about", "copyright_text", "instagram_url", "instagram_handle", "facebook_url",
                             "youtube_url", "pinterest_url", "twitter_url"]),
        ("SEO & analytics", ["meta_title", "meta_description", "og_image", "google_analytics_id", "facebook_pixel_id"]),
    ]
    grouped = [(title, [form[name] for name in names if name in form.fields]) for title, names in groups]
    return render(request, "dashboard/settings.html", {"form": form, "groups": grouped})
