from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="cart")
    coupon = models.ForeignKey("coupons.Coupon", on_delete=models.SET_NULL, null=True, blank=True)
    gift_wrap = models.BooleanField(default=False)
    gift_message = models.CharField(max_length=250, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Cart #{self.pk} ({self.user or 'guest'})"

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "variant"], name="unique_cart_line"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product}"

    @property
    def unit_price(self):
        return self.variant.effective_price if self.variant_id else self.product.price

    @property
    def unit_original_price(self):
        original = self.variant.effective_original_price if self.variant_id else self.product.original_price
        return original or self.unit_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def line_original_total(self):
        return self.unit_original_price * self.quantity

    @property
    def available_stock(self):
        if self.variant_id:
            return self.variant.stock_quantity if self.variant.is_active else 0
        return self.product.stock_quantity

    @property
    def is_available(self):
        return self.product.is_active and self.available_stock >= self.quantity
