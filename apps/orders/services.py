"""
Order business logic. Every critical operation runs inside transaction.atomic()
and changes stock only through apps.inventory.services.adjust_stock.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from apps.cart.services import cart_items, summarize
from apps.coupons.models import Coupon, CouponUsage
from apps.inventory.models import StockHistory
from apps.inventory.services import InsufficientStock, adjust_stock, get_inventory
from apps.notifications.services import notify, notify_staff, send_whatsapp
from apps.payments.models import Payment, Refund
from apps.products.models import Product
from apps.shipping.models import Shipment
from apps.shipping.services import check_pincode, estimate_delivery
from apps.website_settings.models import WebsiteSetting

from .models import Order, OrderItem, OrderStatusHistory, ReturnRequest

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


STATUS_MESSAGES = {
    Order.CONFIRMED: "Your order has been confirmed and will be prepared soon.",
    Order.PROCESSING: "We're preparing your jewellery with care.",
    Order.PACKED: "Your order is packed and ready to ship.",
    Order.SHIPPED: "Good news — your order is on its way!",
    Order.OUT_FOR_DELIVERY: "Your order is out for delivery today.",
    Order.DELIVERED: "Your order has been delivered. We hope you love it!",
    Order.CANCELLED: "Your order has been cancelled.",
    Order.RETURN_REQUESTED: "We've received your return request.",
    Order.RETURNED: "Your returned item has been received.",
    Order.REFUNDED: "Your refund has been processed.",
}

EMAIL_STATUSES = {Order.CONFIRMED, Order.SHIPPED, Order.OUT_FOR_DELIVERY, Order.DELIVERED, Order.CANCELLED,
                  Order.RETURNED, Order.REFUNDED}


def validate_checkout(user, cart, address, shipping_method, payment_method):
    """Pre-checks shared by the checkout page and order placement. Returns (summary, errors)."""
    site = WebsiteSetting.load()
    errors = []
    items = cart_items(cart)
    summary = summarize(cart, user, shipping_method, payment_method, items=items)
    if not items:
        errors.append("Your bag is empty.")
    if summary["has_issues"]:
        errors.append("Some items in your bag are no longer available in the selected quantity.")
    if summary["coupon_error"] and cart and cart.coupon_id:
        errors.append(f"Coupon: {summary['coupon_error']}")
    if address is not None:
        pin = check_pincode(address.pincode)
        if not pin["serviceable"]:
            errors.append(pin["message"])
        if payment_method == Order.PAYMENT_COD and not pin["cod"]:
            errors.append("Cash on Delivery is not available for this PIN code.")
    if shipping_method is None or not shipping_method.is_active:
        errors.append("Please choose a shipping method.")
    if payment_method == Order.PAYMENT_COD:
        if not site.cod_enabled:
            errors.append("Cash on Delivery is currently unavailable.")
        elif shipping_method and not shipping_method.cod_allowed:
            errors.append("Cash on Delivery is not available with the selected shipping method.")
        elif summary["grand_total"] > site.cod_max_order_value:
            errors.append(f"Cash on Delivery is available for orders up to ₹{site.cod_max_order_value:.0f}.")
    elif payment_method == Order.PAYMENT_RAZORPAY:
        from apps.payments.razorpay_client import is_configured

        if not is_configured():
            errors.append("Online payment is not available right now. Please choose Cash on Delivery.")
    else:
        errors.append("Please choose a payment method.")
    return summary, errors


@transaction.atomic
def place_order(*, user, cart, address, shipping_method, payment_method, note=""):
    summary, errors = validate_checkout(user, cart, address, shipping_method, payment_method)
    if errors:
        raise OrderError(" ".join(errors))

    pin = check_pincode(address.pincode)
    est_from, est_to = estimate_delivery(shipping_method, pin.get("extra_days", 0))
    order = Order.objects.create(
        user=user,
        payment_method=payment_method,
        email=user.email,
        full_name=address.full_name,
        phone=address.phone,
        line1=address.line1,
        line2=address.line2,
        landmark=address.landmark,
        city=address.city,
        state=address.state,
        pincode=address.pincode,
        country=address.country,
        shipping_method=shipping_method,
        shipping_method_name=shipping_method.name,
        estimated_delivery_from=est_from,
        estimated_delivery_to=est_to,
        mrp_total=summary["mrp_total"],
        subtotal=summary["subtotal"],
        coupon=summary["coupon"],
        coupon_code=summary["coupon"].code if summary["coupon"] else "",
        coupon_discount=summary["coupon_discount"],
        shipping_charge=summary["shipping"],
        gift_wrap=summary["gift_wrap"],
        gift_message=cart.gift_message if summary["gift_wrap"] else "",
        gift_wrap_charge=summary["gift_wrap_charge"],
        cod_charge=summary["cod_charge"],
        tax_amount=summary["tax"],
        tax_percent=summary["tax_percent"],
        tax_inclusive=summary["tax_inclusive"],
        grand_total=summary["grand_total"],
        customer_note=note[:500],
    )

    for item in summary["items"]:
        inventory = get_inventory(item.product, item.variant)
        try:
            adjust_stock(inventory, -item.quantity, StockHistory.ORDER, user=user, reference=order.order_number)
        except InsufficientStock as exc:
            raise OrderError(str(exc)) from exc
        primary = item.product.primary_image
        OrderItem.objects.create(
            order=order,
            product=item.product,
            variant=item.variant,
            product_name=item.product.name,
            variant_name=item.variant.name if item.variant else "",
            sku=item.variant.sku if item.variant else item.product.sku,
            image=primary.image.name if primary else "",
            unit_price=item.unit_price,
            original_price=item.unit_original_price,
            quantity=item.quantity,
            line_total=item.line_total,
            return_days=item.product.return_days,
            is_returnable=item.product.is_returnable,
        )
        Product.objects.filter(pk=item.product_id).update(sold_count=F("sold_count") + item.quantity)

    OrderStatusHistory.objects.create(order=order, status=Order.PENDING, note="Order placed", changed_by=user)
    Shipment.objects.create(order=order, estimated_delivery=est_to)

    if summary["coupon"]:
        CouponUsage.objects.create(coupon=summary["coupon"], user=user, order=order,
                                   discount_amount=summary["coupon_discount"])
        Coupon.objects.filter(pk=summary["coupon"].pk).update(used_count=F("used_count") + 1)

    if payment_method == Order.PAYMENT_COD:
        Payment.objects.create(order=order, gateway="cod", amount=order.grand_total, status="pending")
        transaction.on_commit(lambda: send_order_placed_notifications(order))

    # Empty the cart — the order now holds the items (stock is reserved).
    cart.items.all().delete()
    cart.coupon = None
    cart.gift_wrap = False
    cart.gift_message = ""
    cart.save()
    return order


def send_order_placed_notifications(order):
    link = reverse("orders:detail", args=[order.order_number])
    notify(
        order.user,
        f"Order {order.order_number} placed",
        f"Thank you for shopping with COZY! Your order total is ₹{order.grand_total}.",
        link=link,
        category="order",
        email_template="emails/order_confirmation.html",
        email_subject=f"Your COZY order {order.order_number} is confirmed",
        email_context={"order": order},
    )
    send_whatsapp(order.phone, f"COZY: Order {order.order_number} received. Total ₹{order.grand_total}.")
    notify_staff("orders.view", "New order received",
                 f"{order.order_number} — ₹{order.grand_total} ({order.get_payment_method_display()})",
                 link=reverse("dashboard:order_detail", args=[order.order_number]), category="order")


@transaction.atomic
def mark_order_paid(order, payment, payment_id, signature="", method="", raw=None):
    """Called only after server-side signature verification (or a verified webhook)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == "captured":
        return order  # idempotent (callback + webhook can both arrive)
    payment.status = "captured"
    payment.razorpay_payment_id = payment_id
    if signature:
        payment.razorpay_signature = signature
    payment.method = method or payment.method
    if raw:
        payment.raw_response = raw
    payment.save()
    order.payment_status = "paid"
    order.save(update_fields=["payment_status", "updated_at"])
    if order.status == Order.CANCELLED:
        # Payment arrived after the order was auto-cancelled: queue a refund for staff.
        Refund.objects.get_or_create(order=order, return_request=None, status="pending",
                                     defaults={"payment": payment, "amount": payment.amount,
                                               "reason": "Payment received after order cancellation"})
        transaction.on_commit(lambda: notify_staff(
            "refunds.manage", "Refund needed", f"Payment received for cancelled order {order.order_number}.",
            link=reverse("dashboard:refund_list"), category="payment"))
        return order
    if order.status == Order.PENDING:
        change_status(order, Order.CONFIRMED, note="Payment received online", notify_customer=False)
    transaction.on_commit(lambda: send_order_placed_notifications(order))
    return order


def _restore_stock(order, movement_type, user=None):
    if order.stock_restored:
        return
    for item in order.items.select_related("product", "variant"):
        if item.product is None:
            continue
        inventory = get_inventory(item.product, item.variant)
        adjust_stock(inventory, item.quantity, movement_type, user=user, reference=order.order_number)
        Product.objects.filter(pk=item.product_id, sold_count__gte=item.quantity).update(
            sold_count=F("sold_count") - item.quantity)
    order.stock_restored = True


@transaction.atomic
def change_status(order, new_status, user=None, note="", notify_customer=True, force=False):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if new_status == order.status:
        return order
    if not force and new_status not in order.allowed_next_statuses:
        raise OrderError(
            f"Cannot change status from {order.get_status_display()} to {dict(Order.STATUS_CHOICES).get(new_status, new_status)}."
        )
    now = timezone.now()
    shipment = getattr(order, "shipment", None)
    update_fields = ["status", "updated_at"]

    if new_status == Order.CONFIRMED:
        order.confirmed_at = now
        update_fields.append("confirmed_at")
    elif new_status in (Order.SHIPPED, Order.OUT_FOR_DELIVERY) and shipment:
        shipment.status = new_status
        if new_status == Order.SHIPPED and not shipment.shipped_at:
            shipment.shipped_at = now
        shipment.save()
    elif new_status == Order.PACKED and shipment:
        shipment.status = "packed"
        shipment.save()
    elif new_status == Order.DELIVERED:
        if order.status == Order.RETURN_REQUESTED:
            pass  # return rejected → back to delivered, keep original delivery date
        else:
            order.delivered_at = now
            update_fields.append("delivered_at")
            if shipment:
                shipment.status = "delivered"
                shipment.delivered_at = now
                shipment.save()
            if order.payment_method == Order.PAYMENT_COD and order.payment_status != "paid":
                order.payment_status = "paid"
                update_fields.append("payment_status")
                order.payments.filter(gateway="cod").update(status="captured")
    elif new_status == Order.CANCELLED:
        order.cancelled_at = now
        order.cancel_reason = note[:255]
        _restore_stock(order, StockHistory.CANCEL, user)
        update_fields += ["cancelled_at", "cancel_reason", "stock_restored"]
        if order.coupon_id:
            CouponUsage.objects.filter(order=order).delete()
            Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
        if order.payment_status == "paid":
            payment = order.payments.filter(status="captured", gateway="razorpay").first()
            Refund.objects.get_or_create(
                order=order, return_request=None, status="pending",
                defaults={"payment": payment, "amount": order.grand_total, "reason": "Order cancelled"},
            )
        elif order.payment_status == "pending":
            order.payments.filter(status__in=["created", "pending"]).update(status="failed", error_message="Order cancelled")
    elif new_status == Order.RETURNED:
        _restore_stock(order, StockHistory.RETURN, user)
        update_fields.append("stock_restored")
        if shipment:
            shipment.status = "returned"
            shipment.save()
    elif new_status == Order.REFUNDED:
        order.payment_status = "refunded"
        update_fields.append("payment_status")

    order.status = new_status
    order.save(update_fields=list(dict.fromkeys(update_fields)))
    OrderStatusHistory.objects.create(order=order, status=new_status, note=note[:255], changed_by=user)

    if notify_customer:
        message = STATUS_MESSAGES.get(new_status, f"Order status updated to {order.get_status_display()}.")
        link = reverse("orders:detail", args=[order.order_number])
        send_email = new_status in EMAIL_STATUSES
        transaction.on_commit(lambda: notify(
            order.user, f"Order {order.order_number}: {order.get_status_display()}", message, link=link,
            category="shipping" if new_status in (Order.SHIPPED, Order.OUT_FOR_DELIVERY, Order.DELIVERED) else "order",
            email_template="emails/order_status.html" if send_email else None,
            email_subject=f"COZY order {order.order_number} — {order.get_status_display()}",
            email_context={"order": order, "status_message": message, "note": note},
        ))
        if new_status in (Order.SHIPPED, Order.OUT_FOR_DELIVERY, Order.DELIVERED):
            transaction.on_commit(lambda: send_whatsapp(order.phone, f"COZY: {order.order_number} — {message}"))
    return order


def customer_cancel(order, user, reason):
    if order.user_id != user.id:
        raise OrderError("Order not found.")
    if not order.can_cancel:
        raise OrderError("This order can no longer be cancelled.")
    order = change_status(order, Order.CANCELLED, user=user, note=f"Cancelled by customer: {reason}"[:255])
    notify_staff("returns.manage", "Order cancelled by customer", f"{order.order_number}: {reason}",
                 link=reverse("dashboard:order_detail", args=[order.order_number]), category="order")
    return order


@transaction.atomic
def request_return(order, user, reason, description="", image=None):
    if order.user_id != user.id:
        raise OrderError("Order not found.")
    if not order.can_return:
        raise OrderError("This order is not eligible for return.")
    rr = ReturnRequest.objects.create(order=order, reason=reason, description=description, image=image,
                                      refund_amount=order.grand_total - order.shipping_charge - order.cod_charge)
    change_status(order, Order.RETURN_REQUESTED, user=user, note=f"Return requested: {rr.get_reason_display()}")
    transaction.on_commit(lambda: notify_staff(
        "returns.manage", "New return request", f"{order.order_number}: {rr.get_reason_display()}",
        link=reverse("dashboard:return_detail", args=[rr.pk]), category="order"))
    return rr


@transaction.atomic
def handle_return(return_request, action, user, note="", refund_amount=None):
    """Staff actions: approve, reject, receive (creates a pending refund)."""
    rr = ReturnRequest.objects.select_for_update().select_related("order").get(pk=return_request.pk)
    order = rr.order
    if action == "approve" and rr.status == "requested":
        rr.status = "approved"
        notify(order.user, f"Return approved for {order.order_number}",
               "Your return has been approved. Our courier partner will contact you for pickup.",
               link=reverse("orders:detail", args=[order.order_number]), category="order",
               email_template="emails/notification.html")
    elif action == "reject" and rr.status in ("requested", "approved"):
        rr.status = "rejected"
        change_status(order, Order.DELIVERED, user=user, note=f"Return rejected: {note}"[:255])
    elif action == "receive" and rr.status == "approved":
        rr.status = "received"
        if refund_amount is not None:
            rr.refund_amount = Decimal(refund_amount)
        change_status(order, Order.RETURNED, user=user, note=note or "Returned item received")
        payment = order.payments.filter(status="captured").first()
        Refund.objects.create(order=order, payment=payment if payment and payment.gateway == "razorpay" else None,
                              return_request=rr, amount=rr.refund_amount or order.grand_total,
                              reason=f"Return: {rr.get_reason_display()}")
    else:
        raise OrderError("This action is not allowed for the current return status.")
    rr.admin_note = (rr.admin_note + "\n" + note).strip() if note else rr.admin_note
    rr.handled_by = user
    rr.save()
    return rr


@transaction.atomic
def process_refund(refund, user, reference="", use_gateway=True):
    from apps.payments import razorpay_client

    refund = Refund.objects.select_for_update().select_related("order", "payment").get(pk=refund.pk)
    if refund.status == "processed":
        raise OrderError("Refund already processed.")
    payment = refund.payment
    if use_gateway and payment and payment.gateway == "razorpay" and payment.razorpay_payment_id:
        try:
            response = razorpay_client.create_refund(payment.razorpay_payment_id, refund.amount,
                                                     notes={"order": refund.order.order_number})
        except razorpay_client.RazorpayError as exc:
            refund.status = "failed"
            refund.error_message = str(exc)[:255]
            refund.save()
            raise OrderError(f"Gateway refund failed: {exc}") from exc
        refund.gateway_refund_id = response.get("id", "")
    refund.reference = reference or refund.reference
    refund.status = "processed"
    refund.processed_by = user
    refund.processed_at = timezone.now()
    refund.save()

    order = refund.order
    if refund.return_request_id:
        ReturnRequest.objects.filter(pk=refund.return_request_id).update(status="refunded")
    total_refunded = sum(r.amount for r in order.refunds.filter(status="processed"))
    if payment:
        payment.status = "refunded" if total_refunded >= payment.amount else payment.status
        payment.save(update_fields=["status", "updated_at"])
    if order.status in (Order.RETURNED, Order.CANCELLED):
        change_status(order, Order.REFUNDED, user=user, note=f"Refund of ₹{refund.amount} processed")
    if total_refunded < order.grand_total:
        Order.objects.filter(pk=order.pk).update(payment_status="partially_refunded")
    return refund
