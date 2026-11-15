"""Report builders. Each returns a dict: title, columns, rows (lists), totals (list or None)."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.utils import timezone

from apps.accounts.models import User
from apps.coupons.models import CouponUsage
from apps.inventory.models import Inventory
from apps.orders.models import Order, OrderItem, ReturnRequest
from apps.payments.models import Payment, Refund

PAID = ["paid", "partially_refunded"]


def default_range():
    end = timezone.localdate()
    return end - timedelta(days=29), end


def _orders(start, end):
    return Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end)


def sales_report(start, end, group="day"):
    trunc = {"day": TruncDate, "month": TruncMonth, "year": TruncYear}.get(group, TruncDate)
    fmt = {"day": "%d %b %Y", "month": "%b %Y", "year": "%Y"}.get(group, "%d %b %Y")
    rows_qs = (
        _orders(start, end).filter(payment_status__in=PAID).annotate(period=trunc("created_at")).values("period")
        .annotate(orders=Count("id"), gross=Sum("subtotal"), discount=Sum("coupon_discount"),
                  shipping=Sum("shipping_charge"), tax=Sum("tax_amount"), total=Sum("grand_total"))
        .order_by("period")
    )
    rows, totals = [], [0, Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0)]
    for r in rows_qs:
        vals = [r["orders"], r["gross"] or 0, r["discount"] or 0, r["shipping"] or 0, r["tax"] or 0, r["total"] or 0]
        rows.append([r["period"].strftime(fmt) if r["period"] else ""] + vals)
        totals = [a + b for a, b in zip(totals, vals)]
    return {
        "title": "Sales report",
        "columns": ["Period", "Paid orders", "Gross sales", "Coupon discounts", "Shipping", "GST", "Revenue"],
        "money_cols": [2, 3, 4, 5, 6],
        "rows": rows,
        "totals": ["Total"] + totals,
    }


def orders_report(start, end):
    qs = _orders(start, end).values("status").annotate(n=Count("id"), value=Sum("grand_total")).order_by("-n")
    labels = dict(Order.STATUS_CHOICES)
    rows = [[labels.get(r["status"], r["status"]), r["n"], r["value"] or 0] for r in qs]
    return {
        "title": "Orders by status",
        "columns": ["Status", "Orders", "Order value"],
        "money_cols": [2],
        "rows": rows,
        "totals": ["Total", sum(r[1] for r in rows), sum((r[2] for r in rows), Decimal(0))],
    }


def product_sales_report(start, end):
    qs = (
        OrderItem.objects.filter(order__created_at__date__gte=start, order__created_at__date__lte=end)
        .exclude(order__status=Order.CANCELLED)
        .values("sku", "product_name").annotate(qty=Sum("quantity"), revenue=Sum("line_total"), orders=Count("order", distinct=True))
        .order_by("-revenue")
    )
    rows = [[r["product_name"], r["sku"], r["orders"], r["qty"], r["revenue"] or 0] for r in qs]
    return {
        "title": "Product sales",
        "columns": ["Product", "SKU", "Orders", "Units sold", "Revenue"],
        "money_cols": [4],
        "rows": rows,
        "totals": ["Total", "", "", sum(r[3] for r in rows), sum((r[4] for r in rows), Decimal(0))],
    }


def category_sales_report(start, end):
    qs = (
        OrderItem.objects.filter(order__created_at__date__gte=start, order__created_at__date__lte=end)
        .exclude(order__status=Order.CANCELLED).filter(product__isnull=False)
        .values("product__category__name").annotate(qty=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-revenue")
    )
    rows = [[r["product__category__name"], r["qty"], r["revenue"] or 0] for r in qs]
    return {
        "title": "Category sales",
        "columns": ["Category", "Units sold", "Revenue"],
        "money_cols": [2],
        "rows": rows,
        "totals": ["Total", sum(r[1] for r in rows), sum((r[2] for r in rows), Decimal(0))],
    }


def customer_report(start, end):
    qs = (
        User.objects.filter(orders__created_at__date__gte=start, orders__created_at__date__lte=end,
                            orders__payment_status__in=PAID)
        .annotate(n=Count("orders", distinct=True), spent=Sum("orders__grand_total")).order_by("-spent")[:200]
    )
    rows = [[u.full_name, u.email, u.phone, u.n, u.spent or 0] for u in qs]
    return {
        "title": "Customer purchases",
        "columns": ["Customer", "Email", "Phone", "Paid orders", "Total spent"],
        "money_cols": [4],
        "rows": rows,
        "totals": None,
    }


def payment_report(start, end):
    qs = (
        Payment.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        .values("gateway", "status").annotate(n=Count("id"), amount=Sum("amount")).order_by("gateway", "status")
    )
    gateways = dict(Payment.GATEWAY_CHOICES)
    statuses = dict(Payment.STATUS_CHOICES)
    rows = [[gateways.get(r["gateway"], r["gateway"]), statuses.get(r["status"], r["status"]), r["n"], r["amount"] or 0]
            for r in qs]
    return {
        "title": "Payments",
        "columns": ["Gateway", "Status", "Transactions", "Amount"],
        "money_cols": [3],
        "rows": rows,
        "totals": None,
    }


def returns_report(start, end):
    qs = (
        ReturnRequest.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        .values("reason", "status").annotate(n=Count("id")).order_by("reason")
    )
    reasons = dict(ReturnRequest.REASON_CHOICES)
    statuses = dict(ReturnRequest.STATUS_CHOICES)
    rows = [[reasons.get(r["reason"], r["reason"]), statuses.get(r["status"], r["status"]), r["n"]] for r in qs]
    refunded = Refund.objects.filter(status="processed", processed_at__date__gte=start,
                                     processed_at__date__lte=end).aggregate(t=Sum("amount"))["t"] or 0
    return {
        "title": "Returns & refunds",
        "columns": ["Reason", "Status", "Requests"],
        "money_cols": [],
        "rows": rows,
        "totals": ["Refunds processed", f"₹{refunded}", sum(r[2] for r in rows)],
    }


def inventory_report(start=None, end=None):
    qs = (
        Inventory.objects.select_related("product", "variant", "product__category")
        .filter(Q(variant__isnull=True, product__has_variants=False) | Q(variant__isnull=False, product__has_variants=True))
        .annotate(value=ExpressionWrapper(F("quantity") * F("product__price"),
                                          output_field=DecimalField(max_digits=14, decimal_places=2)))
        .order_by("quantity")
    )
    rows = []
    for inv in qs:
        status = "Out of stock" if inv.quantity == 0 else ("Low" if inv.quantity <= inv.low_stock_threshold else "OK")
        rows.append([inv.label, inv.sku, inv.product.category.name, inv.quantity, inv.low_stock_threshold, status,
                     inv.value or 0])
    return {
        "title": "Inventory valuation",
        "columns": ["Item", "SKU", "Category", "In stock", "Low threshold", "Status", "Stock value"],
        "money_cols": [6],
        "rows": rows,
        "totals": ["Total", "", "", sum(r[3] for r in rows), "", "", sum((r[6] for r in rows), Decimal(0))],
    }


def coupon_report(start, end):
    qs = (
        CouponUsage.objects.filter(used_at__date__gte=start, used_at__date__lte=end)
        .values("coupon__code", "coupon__campaign").annotate(n=Count("id"), discount=Sum("discount_amount"),
                                                             sales=Sum("order__grand_total"))
        .order_by("-n")
    )
    rows = [[r["coupon__code"], r["coupon__campaign"], r["n"], r["discount"] or 0, r["sales"] or 0] for r in qs]
    return {
        "title": "Coupon usage",
        "columns": ["Coupon", "Campaign", "Uses", "Discount given", "Order value"],
        "money_cols": [3, 4],
        "rows": rows,
        "totals": ["Total", "", sum(r[2] for r in rows), sum((r[3] for r in rows), Decimal(0)),
                   sum((r[4] for r in rows), Decimal(0))],
    }


REPORTS = {
    "sales": ("Sales", sales_report),
    "orders": ("Orders", orders_report),
    "products": ("Products", product_sales_report),
    "categories": ("Categories", category_sales_report),
    "customers": ("Customers", customer_report),
    "payments": ("Payments", payment_report),
    "returns": ("Returns", returns_report),
    "inventory": ("Inventory", inventory_report),
    "coupons": ("Coupons", coupon_report),
}
