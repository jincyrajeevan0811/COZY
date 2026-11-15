from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "category", "is_read", "is_staff_alert", "created_at"]
    list_filter = ["category", "is_read", "is_staff_alert"]
