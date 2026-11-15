from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class ShippingMethod(TimeStampedModel):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)
    description = models.CharField(max_length=200, blank=True)
    charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    free_above = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Order value above which this method is free. Blank = use the site-wide free shipping threshold.",
    )
    min_days = models.PositiveSmallIntegerField(default=3)
    max_days = models.PositiveSmallIntegerField(default=7)
    cod_allowed = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "charge"]

    def __str__(self):
        return self.name


class ServiceablePincode(models.Model):
    """Pincode serviceability rules. A rule may target an exact PIN code or a prefix (e.g. '560').

    If no rules exist at all, every valid Indian PIN code is treated as serviceable.
    """

    pincode_prefix = models.CharField(max_length=6, unique=True, help_text="Full PIN code or a prefix such as 560")
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    is_serviceable = models.BooleanField(default=True)
    cod_available = models.BooleanField(default=True)
    extra_days = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["pincode_prefix"]

    def __str__(self):
        return self.pincode_prefix


class ShippingProvider(TimeStampedModel):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)
    tracking_url_template = models.CharField(
        max_length=255, blank=True, help_text="Use {tracking_number}, e.g. https://courier.example/track/{tracking_number}"
    )
    integration_class = models.CharField(
        max_length=150, default="apps.shipping.providers.ManualProvider",
        help_text="Python path of the courier integration class. Keep ManualProvider until an API is integrated.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Shipment(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("packed", "Packed"),
        ("shipped", "Shipped"),
        ("in_transit", "In transit"),
        ("out_for_delivery", "Out for delivery"),
        ("delivered", "Delivered"),
        ("returned", "Returned to origin"),
    ]

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="shipment")
    provider = models.ForeignKey(ShippingProvider, on_delete=models.SET_NULL, null=True, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Shipment for {self.order}"

    @property
    def tracking_url(self):
        if self.provider and self.provider.tracking_url_template and self.tracking_number:
            return self.provider.tracking_url_template.replace("{tracking_number}", self.tracking_number)
        return ""
