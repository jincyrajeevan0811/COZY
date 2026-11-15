import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.orders.services import mark_order_paid

from . import razorpay_client
from .models import Payment

logger = logging.getLogger(__name__)


@login_required
def pay(request, order_number):
    """Create (or reuse) a Razorpay order and render Razorpay Checkout."""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if not order.needs_payment:
        if order.payment_status == "paid":
            return redirect("orders:success", order_number=order.order_number)
        messages.error(request, "This order can no longer be paid online.")
        return redirect("orders:detail", order_number=order.order_number)
    if not razorpay_client.is_configured():
        messages.error(request, "Online payment is not configured. Please contact support.")
        return redirect("orders:detail", order_number=order.order_number)

    payment = order.payments.filter(gateway="razorpay", status="created", amount=order.grand_total).first()
    if payment is None:
        try:
            rp_order = razorpay_client.create_order(order.grand_total, order.order_number,
                                                    notes={"order_number": order.order_number})
        except razorpay_client.RazorpayError as exc:
            messages.error(request, f"Payment could not be started: {exc}")
            return redirect("orders:detail", order_number=order.order_number)
        payment = Payment.objects.create(order=order, gateway="razorpay", amount=order.grand_total,
                                         razorpay_order_id=rp_order["id"], raw_response=rp_order)
    context = {
        "order": order,
        "payment": payment,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "amount_paise": razorpay_client.to_paise(order.grand_total),
        "verify_url": reverse("payments:verify"),
        "failed_url": reverse("payments:failed", args=[order.order_number]),
    }
    return render(request, "checkout/payment.html", context)


@login_required
@require_POST
def verify(request):
    """Handler called by Razorpay Checkout. The signature is verified server-side before marking paid."""
    rp_order_id = request.POST.get("razorpay_order_id", "")
    rp_payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    payment = get_object_or_404(Payment, razorpay_order_id=rp_order_id, order__user=request.user)
    order = payment.order

    if not razorpay_client.verify_payment_signature(rp_order_id, rp_payment_id, signature):
        payment.status = "failed"
        payment.error_message = "Signature verification failed"
        payment.razorpay_payment_id = rp_payment_id
        payment.save()
        Order.objects.filter(pk=order.pk, payment_status="pending").update(payment_status="failed")
        logger.warning("Razorpay signature mismatch for order %s", order.order_number)
        messages.error(request, "We could not verify your payment. If money was debited, it will be refunded automatically.")
        return redirect("payments:failed", order_number=order.order_number)

    method = ""
    try:
        details = razorpay_client.fetch_payment(rp_payment_id)
        method = details.get("method", "")
    except razorpay_client.RazorpayError:
        details = {}
    mark_order_paid(order, payment, rp_payment_id, signature, method=method, raw=details or None)
    messages.success(request, "Payment successful! Your order is confirmed.")
    return redirect("orders:success", order_number=order.order_number)


@login_required
def failed(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if request.GET.get("reason"):
        payment = order.payments.filter(gateway="razorpay", status="created").first()
        if payment:
            payment.error_message = request.GET["reason"][:255]
            payment.save(update_fields=["error_message", "updated_at"])
    return render(request, "checkout/payment_failed.html", {"order": order})


@csrf_exempt
@require_POST
def webhook(request):
    """Razorpay webhook (configure `payment.captured` and `payment.failed` events)."""
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not razorpay_client.verify_webhook_signature(request.body, signature):
        return HttpResponseBadRequest("invalid signature")
    try:
        event = json.loads(request.body.decode())
    except ValueError:
        return HttpResponseBadRequest("invalid payload")
    entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    payment = Payment.objects.filter(razorpay_order_id=entity.get("order_id", "")).select_related("order").first()
    if payment is None:
        return HttpResponse("ignored")
    if event.get("event") == "payment.captured":
        mark_order_paid(payment.order, payment, entity.get("id", ""), method=entity.get("method", ""), raw=entity)
    elif event.get("event") == "payment.failed" and payment.status == "created":
        payment.status = "failed"
        payment.error_message = (entity.get("error_description") or "")[:255]
        payment.save()
        Order.objects.filter(pk=payment.order_id, payment_status="pending").update(payment_status="failed")
    return JsonResponse({"ok": True})
