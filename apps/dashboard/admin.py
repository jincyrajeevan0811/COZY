from django.contrib import admin

from .models import AdminActivityLog


@admin.register(AdminActivityLog)
class AdminActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "object_type", "object_repr", "ip_address"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_repr", "description", "user__email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
