from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory, ReturnRequest


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [f.name for f in OrderItem._meta.fields]
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "note", "changed_by", "created_at"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "user", "status", "payment_method", "payment_status", "grand_total", "created_at"]
    list_filter = ["status", "payment_method", "payment_status"]
    search_fields = ["order_number", "email", "full_name", "phone"]
    readonly_fields = ["order_number", "status", "payment_status", "grand_total", "subtotal"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]


admin.site.register(ReturnRequest)
