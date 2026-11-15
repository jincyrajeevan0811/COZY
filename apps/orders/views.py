from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.forms import AddressForm
from apps.accounts.models import Address
from apps.cart.services import cart_items, get_cart, summarize
from apps.shipping.models import ShippingMethod
from apps.shipping.services import active_methods, estimate_delivery
from apps.website_settings.models import WebsiteSetting

from .forms import CancelOrderForm, ReturnRequestForm, TrackOrderForm
from .invoice import build_invoice_pdf
from .models import Order, ReturnRequest
from .services import OrderError, customer_cancel, place_order, request_return, validate_checkout


def _selected_method(request):
    code = request.POST.get("shipping_method") or request.GET.get("shipping_method")
    method = ShippingMethod.objects.filter(code=code, is_active=True).first() if code else None
    return method or active_methods().first()


@login_required
def checkout(request):
    cart = get_cart(request)
    if cart is None or not cart.items.exists():
        messages.info(request, "Your bag is empty.")
        return redirect("cart:detail")

    addresses = request.user.addresses.all()
    address_form = AddressForm(request.POST or None, prefix="addr",
                               initial={"full_name": request.user.full_name, "phone": request.user.phone})
    methods = list(active_methods())
    site = WebsiteSetting.load()

    if request.method == "POST":
        method = _selected_method(request)
        payment_method = request.POST.get("payment_method")
        address = None
        if request.POST.get("address_id") == "new" or not addresses.exists():
            if address_form.is_valid():
                address = address_form.save(commit=False)
                address.user = request.user
                address.save()
            else:
                messages.error(request, "Please correct the delivery address.")
        else:
            address = addresses.filter(pk=request.POST.get("address_id")).first()
            if address is None:
                messages.error(request, "Please choose a delivery address.")
        if address is not None:
            try:
                order = place_order(
                    user=request.user, cart=cart, address=address, shipping_method=method,
                    payment_method=payment_method, note=request.POST.get("note", ""),
                )
            except OrderError as exc:
                messages.error(request, str(exc))
            else:
                if order.payment_method == Order.PAYMENT_RAZORPAY:
                    return redirect("payments:pay", order_number=order.order_number)
                return redirect("orders:success", order_number=order.order_number)

    method = _selected_method(request)
    summary = summarize(cart, request.user, method, request.POST.get("payment_method") or "razorpay")
    delivery = {m.code: estimate_delivery(m) for m in methods}
    from apps.payments.razorpay_client import is_configured

    return render(request, "checkout/checkout.html", {
        "cart": cart,
        "summary": summary,
        "addresses": addresses,
        "address_form": address_form,
        "shipping_methods": methods,
        "selected_method": method,
        "delivery": delivery,
        "site_settings": site,
        "razorpay_ready": is_configured(),
        "selected_address_id": request.POST.get("address_id") or (addresses.first().pk if addresses.exists() else "new"),
    })


@login_required
def checkout_summary(request):
    """AJAX: recalculate totals when shipping or payment method changes."""
    cart = get_cart(request)
    method = _selected_method(request)
    payment_method = request.GET.get("payment_method")
    address = request.user.addresses.filter(pk=request.GET.get("address_id")).first() if request.GET.get("address_id", "").isdigit() else None
    summary, errors = validate_checkout(request.user, cart, address, method, payment_method)
    return JsonResponse({
        "subtotal": str(summary["subtotal"]),
        "coupon_discount": str(summary["coupon_discount"]),
        "shipping": str(summary["shipping"]),
        "gift_wrap_charge": str(summary["gift_wrap_charge"]),
        "cod_charge": str(summary["cod_charge"]),
        "tax": str(summary["tax"]),
        "grand_total": str(summary["grand_total"]),
        "errors": errors,
    })


@login_required
def order_success(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number, user=request.user)
    return render(request, "checkout/success.html", {"order": order})


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    status = request.GET.get("status")
    if status == "active":
        orders = orders.exclude(status__in=["delivered", "cancelled", "returned", "refunded"])
    elif status in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status)
    page = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"page_obj": page, "orders": page.object_list, "status": status})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("shipment", "shipment__provider").prefetch_related("items", "status_history",
                                                                                        "return_requests", "refunds"),
        order_number=order_number, user=request.user,  # prevents cross-customer access
    )
    reviewed_ids = set(request.user.reviews.values_list("product_id", flat=True))
    return render(request, "orders/order_detail.html", {
        "order": order,
        "timeline": order.timeline(),
        "cancel_form": CancelOrderForm(),
        "reviewed_ids": reviewed_ids,
    })


@login_required
@require_POST
def cancel_order(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    form = CancelOrderForm(request.POST)
    if form.is_valid():
        reason = form.cleaned_data["reason"]
        if form.cleaned_data.get("details"):
            reason += f" — {form.cleaned_data['details']}"
        try:
            customer_cancel(order, request.user, reason)
            msg = "Your order has been cancelled."
            if order.payment_status == "paid":
                msg += " Your refund will be processed within 5-7 business days."
            messages.success(request, msg)
        except OrderError as exc:
            messages.error(request, str(exc))
    return redirect("orders:detail", order_number=order_number)


@login_required
def return_order(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number, user=request.user)
    if not order.can_return:
        messages.error(request, "This order is not eligible for return.")
        return redirect("orders:detail", order_number=order_number)
    form = ReturnRequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            request_return(order, request.user, form.cleaned_data["reason"], form.cleaned_data.get("description", ""),
                           form.cleaned_data.get("image"))
            messages.success(request, "Return requested. We'll update you within 48 hours.")
            return redirect("orders:detail", order_number=order_number)
        except OrderError as exc:
            messages.error(request, str(exc))
    return render(request, "orders/return_form.html", {"order": order, "form": form})


@login_required
def returns_and_cancellations(request):
    returns = ReturnRequest.objects.filter(order__user=request.user).select_related("order")
    cancelled = Order.objects.filter(user=request.user, status__in=[Order.CANCELLED, Order.REFUNDED]).filter(
        Q(cancelled_at__isnull=False) | Q(status=Order.CANCELLED))
    return render(request, "orders/returns.html", {"returns": returns, "cancelled_orders": cancelled})


@login_required
def invoice_pdf(request, order_number):
    if request.user.is_staff_member and request.user.has_access("orders.view"):
        order = get_object_or_404(Order, order_number=order_number)
    else:
        order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.status == Order.PENDING and order.needs_payment:
        messages.info(request, "The invoice will be available once payment is complete.")
        return redirect("orders:detail", order_number=order_number)
    pdf = build_invoice_pdf(order)
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "inline" if request.GET.get("view") else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="COZY-Invoice-{order.order_number}.pdf"'
    return response


def track_order(request):
    """Guest-friendly tracking with order number + email."""
    form = TrackOrderForm(request.POST or request.GET or None)
    order = None
    if form.is_bound and form.is_valid():
        order = Order.objects.filter(
            order_number=form.cleaned_data["order_number"].strip().upper(),
            email__iexact=form.cleaned_data["email"].strip(),
        ).select_related("shipment", "shipment__provider").prefetch_related("items", "status_history").first()
        if order is None:
            messages.error(request, "We couldn't find an order with those details.")
    return render(request, "orders/track.html", {"form": form, "order": order,
                                                 "timeline": order.timeline() if order else None})
