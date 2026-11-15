from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.utils import money


class Coupon(TimeStampedModel):
    PERCENT, FIXED = "percent", "fixed"
    TYPE_CHOICES = [(PERCENT, "Percentage"), (FIXED, "Fixed amount")]
    SCOPE_ALL, SCOPE_CATEGORY, SCOPE_PRODUCT = "all", "category", "product"
    SCOPE_CHOICES = [(SCOPE_ALL, "Entire order"), (SCOPE_CATEGORY, "Specific categories"), (SCOPE_PRODUCT, "Specific products")]

    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=PERCENT)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text="Cap for percentage coupons")
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_ALL)
    categories = models.ManyToManyField("categories.Category", blank=True)
    products = models.ManyToManyField("products.Product", blank=True)
    first_order_only = models.BooleanField(default=False)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Total uses allowed (blank = unlimited)")
    per_user_limit = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    campaign = models.CharField(max_length=60, blank=True, help_text="Seasonal campaign label, e.g. Diwali 2026")
    is_public = models.BooleanField(default=True, help_text="Show on the customer offers page")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def clean(self):
        if self.discount_type == self.PERCENT and self.value and self.value > 100:
            raise ValidationError({"value": "Percentage cannot exceed 100."})
        if self.valid_to and self.valid_from and self.valid_to <= self.valid_from:
            raise ValidationError({"valid_to": "End date must be after the start date."})

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    @property
    def label(self):
        if self.discount_type == self.PERCENT:
            return f"{self.value.normalize():f}% OFF"
        return f"₹{self.value.normalize():f} OFF"

    def eligible_subtotal(self, lines):
        """Subtotal of cart lines this coupon applies to. `lines` = iterable of (product, line_total)."""
        if self.scope == self.SCOPE_ALL:
            return sum((total for _, total in lines), Decimal("0"))
        if self.scope == self.SCOPE_CATEGORY:
            cat_ids = set(self.categories.values_list("id", flat=True))
            return sum((t for p, t in lines if p.category_id in cat_ids), Decimal("0"))
        prod_ids = set(self.products.values_list("id", flat=True))
        return sum((t for p, t in lines if p.id in prod_ids), Decimal("0"))

    def evaluate(self, user, lines, subtotal):
        """Return (discount_amount, error_message). Error is '' when the coupon is valid."""
        now = timezone.now()
        if not self.is_active:
            return Decimal("0"), "This coupon is no longer active."
        if self.valid_from and now < self.valid_from:
            return Decimal("0"), "This coupon is not active yet."
        if self.valid_to and now > self.valid_to:
            return Decimal("0"), "This coupon has expired."
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return Decimal("0"), "This coupon has reached its usage limit."
        if subtotal < self.min_order_value:
            return Decimal("0"), f"Add items worth ₹{self.min_order_value - subtotal:.0f} more to use this coupon."
        if user is not None and user.is_authenticated:
            if self.per_user_limit and self.usages.filter(user=user).count() >= self.per_user_limit:
                return Decimal("0"), "You have already used this coupon."
            if self.first_order_only and user.orders.exclude(status="cancelled").exists():
                return Decimal("0"), "This coupon is valid on your first order only."
        elif self.first_order_only:
            return Decimal("0"), "Sign in to use this first-order coupon."
        eligible = self.eligible_subtotal(lines)
        if eligible <= 0:
            return Decimal("0"), "This coupon does not apply to the items in your cart."
        if self.discount_type == self.PERCENT:
            discount = eligible * self.value / Decimal("100")
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = min(self.value, eligible)
        return money(discount), ""


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_usages")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="coupon_usages")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-used_at"]

    def __str__(self):
        return f"{self.coupon} by {self.user}"
