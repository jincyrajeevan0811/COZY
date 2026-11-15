from django.conf import settings
from django.db import models


class AdminActivityLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("status", "Status change"),
        ("login", "Signed in"),
        ("export", "Exported"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="activity_logs")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    object_type = models.CharField(max_length=60, blank=True, db_index=True)
    object_id = models.CharField(max_length=40, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.action} {self.object_type} {self.object_repr}"
