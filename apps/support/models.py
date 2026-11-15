from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel
from apps.core.utils import random_code


class SupportTicket(TimeStampedModel):
    STATUS_CHOICES = [("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")]
    PRIORITY_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]
    CATEGORY_CHOICES = [
        ("order", "Order related"),
        ("payment", "Payment"),
        ("product", "Product enquiry"),
        ("return", "Return / refund"),
        ("other", "Other"),
    ]

    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="tickets")
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=15, blank=True)
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open", db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="assigned_tickets")

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.ticket_number}: {self.subject}"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            while True:
                number = "TKT-" + random_code(6, "0123456789")
                if not SupportTicket.objects.filter(ticket_number=number).exists():
                    self.ticket_number = number
                    break
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("support:detail", args=[self.ticket_number])


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_staff_reply = models.BooleanField(default=False)
    message = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message on {self.ticket}"
