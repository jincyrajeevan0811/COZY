from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ProductReview


def refresh_product_rating(product):
    stats = product.reviews.filter(status="approved").aggregate(avg=Avg("rating"), n=Count("id"))
    product.avg_rating = round(stats["avg"] or 0, 2)
    product.review_count = stats["n"] or 0
    product.save(update_fields=["avg_rating", "review_count", "updated_at"])


@receiver(post_save, sender=ProductReview)
@receiver(post_delete, sender=ProductReview)
def update_rating(sender, instance, **kwargs):
    from apps.products.models import Product

    product = Product.objects.filter(pk=instance.product_id).first()
    if product is not None:
        refresh_product_rating(product)
