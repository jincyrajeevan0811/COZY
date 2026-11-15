from django.contrib import admin

from .models import SupportMessage, SupportTicket


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ["ticket_number", "subject", "email", "status", "priority", "assigned_to", "updated_at"]
    list_filter = ["status", "priority", "category"]
    inlines = [SupportMessageInline]
