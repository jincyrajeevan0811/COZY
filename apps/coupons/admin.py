from django.contrib import admin

from .models import Coupon, CouponUsage


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "discount_type", "value", "used_count", "usage_limit", "valid_to", "is_active"]
    filter_horizontal = ["categories", "products"]


admin.site.register(CouponUsage)
