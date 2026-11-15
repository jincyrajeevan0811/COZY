from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.utils import optimize_image
from apps.core.validators import IMAGE_VALIDATORS


class ProductReview(TimeStampedModel):
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(max_length=2000)
    is_verified_purchase = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)
    admin_reply = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_product_user")]

    def __str__(self):
        return f"{self.rating}★ {self.product} by {self.user}"


class ReviewImage(models.Model):
    review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="reviews/", validators=IMAGE_VALIDATORS)

    def save(self, *args, **kwargs):
        optimize_image(self.image, max_size=1200)
        super().save(*args, **kwargs)
