from django.contrib import admin

from .models import Payment, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "gateway", "amount", "status", "razorpay_payment_id", "created_at"]
    list_filter = ["gateway", "status"]
    search_fields = ["order__order_number", "razorpay_order_id", "razorpay_payment_id"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["order", "amount", "status", "processed_at"]
    list_filter = ["status"]
