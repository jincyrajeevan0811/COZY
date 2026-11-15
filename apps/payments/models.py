from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("pending", "Pending (COD)"),
        ("captured", "Captured"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]
    GATEWAY_CHOICES = [("razorpay", "Razorpay"), ("cod", "Cash on Delivery")]

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created", db_index=True)
    razorpay_order_id = models.CharField(max_length=60, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=60, blank=True, db_index=True)
    razorpay_signature = models.CharField(max_length=200, blank=True)
    method = models.CharField(max_length=30, blank=True, help_text="upi / card / netbanking / wallet (from gateway)")
    error_message = models.CharField(max_length=255, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_gateway_display()} {self.amount} for {self.order}"

    @property
    def transaction_id(self):
        return self.razorpay_payment_id or self.razorpay_order_id or f"COD-{self.order.order_number}"


class Refund(TimeStampedModel):
    STATUS_CHOICES = [("pending", "Pending"), ("processed", "Processed"), ("failed", "Failed")]

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="refunds")
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="refunds")
    return_request = models.ForeignKey("orders.ReturnRequest", on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    gateway_refund_id = models.CharField(max_length=60, blank=True)
    reference = models.CharField(max_length=120, blank=True, help_text="Manual refund reference (UPI / bank transfer)")
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.amount} for {self.order}"
