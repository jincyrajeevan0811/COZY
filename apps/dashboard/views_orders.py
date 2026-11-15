"""Order, return, refund, payment and abandoned-cart management."""
import csv
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.accounts.rbac import permission_required
from apps.cart.models import Cart
from apps.notifications.services import send_templated_email
from apps.orders.models import Order, ReturnRequest
from apps.orders.services import OrderError, change_status, handle_return, process_refund
from apps.payments.models import Payment, Refund
from apps.shipping.models import Shipment

from .audit import log_activity
from .forms import AdminNoteForm, OrderStatusForm, RefundProcessForm, ReturnActionForm, ShipmentForm


def _filtered_orders(request):
    qs = Order.objects.select_related("user")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(order_number__icontains=q) | Q(full_name__icontains=q) | Q(email__icontains=q)
                       | Q(phone__icontains=q) | Q(shipment__tracking_number__icontains=q))
    for field in ("status", "payment_status", "payment_method"):
        if request.GET.get(field):
            qs = qs.filter(**{field: request.GET[field]})
    start, end = parse_date(request.GET.get("start", "") or ""), parse_date(request.GET.get("end", "") or "")
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs, q


@permission_required("orders.view")
def order_list(request):
    qs, q = _filtered_orders(request)
    if request.GET.get("export") == "csv":
        log_activity(request, "export", None, "Exported orders CSV", object_type="Order")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="cozy-orders.csv"'
        writer = csv.writer(response)
        writer.writerow(["Order", "Date", "Customer", "Email", "Phone", "City", "Status", "Payment", "Payment status",
                         "Items", "Subtotal", "Discount", "Shipping", "Total"])
        for o in qs.annotate(n=Sum("items__quantity")):
            writer.writerow([o.order_number, timezone.localtime(o.created_at).strftime("%Y-%m-%d %H:%M"), o.full_name,
                             o.email, o.phone, o.city, o.get_status_display(), o.get_payment_method_display(),
                             o.get_payment_status_display(), o.n, o.subtotal, o.coupon_discount, o.shipping_charge,
                             o.grand_total])
        return response
    counts = dict(Order.objects.values_list("status").annotate(n=Count("id")))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/orders/list.html", {
        "page_obj": page, "q": q, "status_choices": Order.STATUS_CHOICES, "counts": counts,
        "payment_status_choices": Order.PAYMENT_STATUS_CHOICES, "payment_method_choices": Order.PAYMENT_METHOD_CHOICES,
    })


def _get_order(order_number):
    return get_object_or_404(
        Order.objects.select_related("user", "shipping_method", "shipment", "shipment__provider")
        .prefetch_related("items", "status_history__changed_by", "payments", "refunds", "return_requests"),
        order_number=order_number,
    )


@permission_required("orders.view")
def order_detail(request, order_number):
    order = _get_order(order_number)
    shipment, _ = Shipment.objects.get_or_create(order=order)
    return render(request, "dashboard/orders/detail.html", {
        "order": order,
        "status_form": OrderStatusForm(order),
        "shipment_form": ShipmentForm(instance=shipment),
        "note_form": AdminNoteForm(instance=order),
        "can_manage": request.user.has_access("orders.manage"),
        "customer_orders": Order.objects.filter(user=order.user).count(),
    })


@permission_required("orders.manage")
@require_POST
def order_update_status(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    form = OrderStatusForm(order, request.POST)
    if form.is_valid():
        try:
            change_status(order, form.cleaned_data["status"], user=request.user, note=form.cleaned_data["note"],
                          notify_customer=form.cleaned_data["notify_customer"])
            log_activity(request, "status", order, f"Status → {form.cleaned_data['status']}")
            messages.success(request, "Order status updated.")
        except OrderError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Choose a valid next status.")
    return redirect("dashboard:order_detail", order_number=order_number)


@permission_required("orders.manage")
@require_POST
def order_update_shipment(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    shipment, _ = Shipment.objects.get_or_create(order=order)
    form = ShipmentForm(request.POST, instance=shipment)
    if form.is_valid():
        form.save()
        log_activity(request, "update", order, f"Shipping details updated (AWB {shipment.tracking_number})")
        messages.success(request, "Shipping details saved.")
    else:
        messages.error(request, "Please check the shipping details.")
    return redirect("dashboard:order_detail", order_number=order_number)


@permission_required("orders.manage")
@require_POST
def order_update_note(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    form = AdminNoteForm(request.POST, instance=order)
    if form.is_valid():
        form.save()
        messages.success(request, "Internal note saved.")
    return redirect("dashboard:order_detail", order_number=order_number)


@permission_required("orders.view")
def order_print(request, order_number):
    return render(request, "dashboard/orders/print.html", {"order": _get_order(order_number)})


# ---------------------------------------------------------------------------
# Returns & refunds
# ---------------------------------------------------------------------------
@permission_required("returns.manage")
def return_list(request):
    qs = ReturnRequest.objects.select_related("order", "order__user")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/orders/returns.html", {"page_obj": page,
                                                             "status_choices": ReturnRequest.STATUS_CHOICES})


@permission_required("returns.manage")
def return_detail(request, pk):
    rr = get_object_or_404(ReturnRequest.objects.select_related("order", "order__user"), pk=pk)
    form = ReturnActionForm(request.POST or None, initial={"refund_amount": rr.refund_amount})
    if request.method == "POST" and form.is_valid():
        try:
            handle_return(rr, form.cleaned_data["action"], request.user, form.cleaned_data.get("note", ""),
                          form.cleaned_data.get("refund_amount"))
            log_activity(request, "status", rr.order, f"Return {form.cleaned_data['action']}")
            messages.success(request, "Return updated.")
        except OrderError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:return_detail", pk=pk)
    return render(request, "dashboard/orders/return_detail.html", {"rr": rr, "form": form, "order": rr.order})


@permission_required("refunds.manage", "payments.view")
def refund_list(request):
    qs = Refund.objects.select_related("order", "payment", "processed_by")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/orders/refunds.html", {
        "page_obj": page, "form": RefundProcessForm(), "can_process": request.user.has_access("refunds.manage"),
        "status_choices": Refund.STATUS_CHOICES,
    })


@permission_required("refunds.manage")
@require_POST
def refund_process(request, pk):
    refund = get_object_or_404(Refund, pk=pk)
    form = RefundProcessForm(request.POST)
    if form.is_valid():
        try:
            process_refund(refund, request.user, form.cleaned_data["reference"], form.cleaned_data["use_gateway"])
            log_activity(request, "update", refund, f"Refund processed ₹{refund.amount}")
            messages.success(request, "Refund processed and the customer has been notified.")
        except OrderError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard:refund_list")


@permission_required("payments.view")
def payment_list(request):
    qs = Payment.objects.select_related("order")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("gateway"):
        qs = qs.filter(gateway=request.GET["gateway"])
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(order__order_number__icontains=q) | Q(razorpay_payment_id__icontains=q)
                       | Q(razorpay_order_id__icontains=q))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "dashboard/orders/payments.html", {
        "page_obj": page, "q": q, "status_choices": Payment.STATUS_CHOICES,
    })


# ---------------------------------------------------------------------------
# Abandoned carts
# ---------------------------------------------------------------------------
@permission_required("orders.manage", "customers.view")
def abandoned_carts(request):
    cutoff = timezone.now() - timedelta(hours=1)
    carts = (
        Cart.objects.filter(user__isnull=False, updated_at__lt=cutoff, items__isnull=False)
        .select_related("user").prefetch_related("items__product", "items__variant").distinct().order_by("-updated_at")
    )
    page = Paginator(carts, 25).get_page(request.GET.get("page"))
    for cart in page.object_list:
        cart.bag_value = sum((item.line_total for item in cart.items.all()), 0)
    return render(request, "dashboard/orders/abandoned_carts.html", {"page_obj": page})


@permission_required("orders.manage")
@require_POST
def abandoned_cart_remind(request, pk):
    cart = get_object_or_404(Cart.objects.select_related("user"), pk=pk, user__isnull=False)
    items = list(cart.items.select_related("product", "variant"))
    if items:
        send_templated_email("You left something sparkly behind ✨", [cart.user.email], "emails/abandoned_cart.html",
                             {"user": cart.user, "items": items,
                              "cart_url": request.build_absolute_uri(reverse("cart:detail"))})
        cart.reminder_sent_at = timezone.now()
        cart.save(update_fields=["reminder_sent_at"])
        messages.success(request, f"Reminder sent to {cart.user.email}.")
    return redirect("dashboard:abandoned_carts")
