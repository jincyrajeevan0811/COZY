from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import User, UserProfile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_migrate)
def ensure_roles(sender, **kwargs):
    # Run once, after the accounts app has been migrated.
    if getattr(sender, "label", "") != "accounts":
        return
    from .rbac import sync_roles_and_permissions

    sync_roles_and_permissions()
