from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.utils import random_code
from apps.core.validators import IMAGE_VALIDATORS


class Order(TimeStampedModel):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_REQUESTED = "return_requested"
    RETURNED = "returned"
    REFUNDED = "refunded"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
        (PROCESSING, "Processing"),
        (PACKED, "Packed"),
        (SHIPPED, "Shipped"),
        (OUT_FOR_DELIVERY, "Out for Delivery"),
        (DELIVERED, "Delivered"),
        (CANCELLED, "Cancelled"),
        (RETURN_REQUESTED, "Return Requested"),
        (RETURNED, "Returned"),
        (REFUNDED, "Refunded"),
    ]

    # Allowed status transitions (enforced by orders.services.change_status)
    TRANSITIONS = {
        PENDING: [CONFIRMED, CANCELLED],
        CONFIRMED: [PROCESSING, PACKED, CANCELLED],
        PROCESSING: [PACKED, CANCELLED],
        PACKED: [SHIPPED, CANCELLED],
        SHIPPED: [OUT_FOR_DELIVERY, DELIVERED],
        OUT_FOR_DELIVERY: [DELIVERED],
        DELIVERED: [RETURN_REQUESTED],
        RETURN_REQUESTED: [RETURNED, DELIVERED],
        RETURNED: [REFUNDED],
        CANCELLED: [REFUNDED],
        REFUNDED: [],
    }

    TIMELINE = [
        (PENDING, "Order Placed", "bi-bag-check"),
        (CONFIRMED, "Confirmed", "bi-patch-check"),
        (PROCESSING, "Processing", "bi-gear"),
        (PACKED, "Packed", "bi-box-seam"),
        (SHIPPED, "Shipped", "bi-truck"),
        (OUT_FOR_DELIVERY, "Out for Delivery", "bi-geo-alt"),
        (DELIVERED, "Delivered", "bi-house-heart"),
    ]

    CUSTOMER_CANCELLABLE = [PENDING, CONFIRMED, PROCESSING]

    PAYMENT_COD, PAYMENT_RAZORPAY = "cod", "razorpay"
    PAYMENT_METHOD_CHOICES = [(PAYMENT_COD, "Cash on Delivery"), (PAYMENT_RAZORPAY, "Online payment (Razorpay)")]

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
        ("partially_refunded", "Partially refunded"),
    ]

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending", db_index=True)

    # Customer & address snapshot (orders must not change if the address book changes)
    email = models.EmailField()
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6)
    country = models.CharField(max_length=60, default="India")

    # Shipping
    shipping_method = models.ForeignKey("shipping.ShippingMethod", on_delete=models.SET_NULL, null=True, blank=True)
    shipping_method_name = models.CharField(max_length=80, blank=True)
    estimated_delivery_from = models.DateField(null=True, blank=True)
    estimated_delivery_to = models.DateField(null=True, blank=True)

    # Money
    mrp_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    coupon = models.ForeignKey("coupons.Coupon", on_delete=models.SET_NULL, null=True, blank=True)
    coupon_code = models.CharField(max_length=30, blank=True)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    gift_wrap = models.BooleanField(default=False)
    gift_message = models.CharField(max_length=250, blank=True)
    gift_wrap_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    cod_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_inclusive = models.BooleanField(default=True)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)

    customer_note = models.CharField(max_length=500, blank=True)
    admin_note = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    stock_restored = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"]), models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_number()
        super().save(*args, **kwargs)

    @classmethod
    def generate_number(cls):
        prefix = f"CZ{timezone.localdate():%y%m%d}"
        while True:
            number = prefix + random_code(5, "0123456789")
            if not cls.objects.filter(order_number=number).exists():
                return number

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.order_number])

    @property
    def address_lines(self):
        return [p for p in [self.line1, self.line2, self.landmark, f"{self.city}, {self.state} - {self.pincode}", self.country] if p]

    @property
    def allowed_next_statuses(self):
        return self.TRANSITIONS.get(self.status, [])

    @property
    def can_cancel(self):
        return self.status in self.CUSTOMER_CANCELLABLE

    @property
    def return_deadline(self):
        if not self.delivered_at:
            return None
        days = min([i.return_days for i in self.items.all()] or [0])
        return self.delivered_at + timedelta(days=days)

    @property
    def can_return(self):
        if self.status != self.DELIVERED or not self.delivered_at:
            return False
        if not all(i.is_returnable for i in self.items.all()):
            return False
        if self.return_requests.exclude(status="rejected").exists():
            return False
        deadline = self.return_deadline
        return deadline is not None and timezone.now() <= deadline

    @property
    def needs_payment(self):
        return (
            self.payment_method == self.PAYMENT_RAZORPAY
            and self.payment_status in ("pending", "failed")
            and self.status == self.PENDING
        )

    @property
    def total_quantity(self):
        return sum(i.quantity for i in self.items.all())

    def timeline(self):
        """Steps for the customer tracking page, with reached/current flags and timestamps."""
        history = {}
        for h in self.status_history.all():
            history.setdefault(h.status, h.created_at)
        order_of = [s for s, _, _ in self.TIMELINE]
        current_idx = order_of.index(self.status) if self.status in order_of else None
        if current_idx is None:  # cancelled / returns: show the furthest reached step
            reached = [order_of.index(s) for s in history if s in order_of]
            current_idx = max(reached) if reached else 0
        steps = []
        for idx, (status, label, icon) in enumerate(self.TIMELINE):
            steps.append({
                "status": status,
                "label": label,
                "icon": icon,
                "done": idx <= current_idx,
                "current": idx == current_idx and self.status in order_of,
                "at": history.get(status),
            })
        return steps


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=120, blank=True)
    sku = models.CharField(max_length=60)
    image = models.CharField(max_length=255, blank=True, help_text="Image path snapshot")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    return_days = models.PositiveSmallIntegerField(default=7)
    is_returnable = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def image_url(self):
        if self.image:
            return f"{settings.MEDIA_URL}{self.image}"
        return ""


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "order status history"

    def __str__(self):
        return f"{self.order} → {self.status}"


class ReturnRequest(TimeStampedModel):
    REASON_CHOICES = [
        ("damaged", "Item arrived damaged"),
        ("wrong_item", "Wrong item received"),
        ("not_as_described", "Not as described"),
        ("quality", "Quality not as expected"),
        ("size_fit", "Size / fit issue"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved — awaiting pickup"),
        ("rejected", "Rejected"),
        ("received", "Item received"),
        ("refunded", "Refunded"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="return_requests")
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="returns/", blank=True, validators=IMAGE_VALIDATORS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested", db_index=True)
    admin_note = models.TextField(blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return for {self.order}"
