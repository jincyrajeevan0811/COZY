from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Inventory(TimeStampedModel):
    """Stock record for a simple product (variant is null) or for one product variant."""

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="inventories")
    variant = models.OneToOneField("products.ProductVariant", on_delete=models.CASCADE, null=True, blank=True,
                                   related_name="inventory")
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    class Meta:
        verbose_name_plural = "inventory"
        ordering = ["quantity"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="inventory_quantity_non_negative"),
        ]
        indexes = [models.Index(fields=["quantity"])]

    def __str__(self):
        return f"{self.label}: {self.quantity}"

    @property
    def label(self):
        if self.variant_id:
            return f"{self.product.name} ({self.variant.name})"
        return self.product.name

    @property
    def sku(self):
        return self.variant.sku if self.variant_id else self.product.sku

    @property
    def is_low(self):
        return 0 < self.quantity <= self.low_stock_threshold

    @property
    def is_out(self):
        return self.quantity == 0

    @property
    def stock_status(self):
        if self.is_out:
            return "out"
        if self.is_low:
            return "low"
        return "ok"


class StockHistory(models.Model):
    STOCK_IN, STOCK_OUT, ADJUSTMENT, ORDER, CANCEL, RETURN = "in", "out", "adjustment", "order", "cancel", "return"
    TYPE_CHOICES = [
        (STOCK_IN, "Stock in"),
        (STOCK_OUT, "Stock out"),
        (ADJUSTMENT, "Adjustment"),
        (ORDER, "Order placed"),
        (CANCEL, "Order cancelled"),
        (RETURN, "Customer return"),
    ]

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="history")
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    quantity_change = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reference = models.CharField(max_length=100, blank=True, help_text="Order number, supplier invoice, etc.")
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "stock history"

    def __str__(self):
        return f"{self.inventory.label}: {self.quantity_change:+d}"
