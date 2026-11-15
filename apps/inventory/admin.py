from django.contrib import admin

from .models import Inventory, StockHistory


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ["product", "variant", "quantity", "low_stock_threshold", "updated_at"]
    search_fields = ["product__name", "product__sku", "variant__sku"]
    readonly_fields = ["quantity"]  # change stock through the dashboard so history is recorded


@admin.register(StockHistory)
class StockHistoryAdmin(admin.ModelAdmin):
    list_display = ["inventory", "movement_type", "quantity_change", "balance_after", "reference", "user", "created_at"]
    list_filter = ["movement_type"]

    def has_change_permission(self, request, obj=None):
        return False
