from django.conf import settings
from django.db import models


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ("order", "Order"),
        ("payment", "Payment"),
        ("shipping", "Shipping"),
        ("promo", "Offer"),
        ("stock", "Inventory"),
        ("support", "Support"),
        ("review", "Review"),
        ("system", "System"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="system")
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    is_staff_alert = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.title} → {self.user}"

    @property
    def icon(self):
        return {
            "order": "bi-bag-check", "payment": "bi-credit-card", "shipping": "bi-truck", "promo": "bi-gift",
            "stock": "bi-box-seam", "support": "bi-headset", "review": "bi-star", "system": "bi-bell",
        }.get(self.category, "bi-bell")
