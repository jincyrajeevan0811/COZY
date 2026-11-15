from django.contrib import admin

from .models import ProductReview, ReviewImage


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 0


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "is_verified_purchase", "status", "created_at"]
    list_filter = ["status", "rating", "is_verified_purchase"]
    inlines = [ReviewImageInline]
