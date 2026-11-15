"""
Notification helpers: in-app notifications, email and (optional) WhatsApp.

Emails are sent synchronously with fail_silently semantics so that a mail-server
problem never breaks checkout. For high volume, plug these calls into Celery.
"""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_templated_email(subject, recipients, template, context=None, fail_silently=True):
    from apps.website_settings.models import WebsiteSetting

    recipients = [r for r in recipients if r]
    if not recipients:
        return False
    ctx = {"site": WebsiteSetting.load(), "SITE_URL": settings.SITE_URL, "subject": subject}
    ctx.update(context or {})
    try:
        html = render_to_string(template, ctx)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, recipients)
        msg.attach_alternative(html, "text/html")
        msg.send()
        return True
    except Exception:
        logger.exception("Failed to send email '%s' to %s", subject, recipients)
        if not fail_silently:
            raise
        return False


def notify(user, title, message, link="", category="system", email_template=None, email_subject=None,
           email_context=None, send_email=None):
    """Create an in-app notification and optionally email the user."""
    from .models import Notification

    if user is None:
        return None
    notification = Notification.objects.create(user=user, title=title, message=message, link=link, category=category)
    if send_email is None:
        send_email = email_template is not None
    if send_email:
        ctx = {"user": user, "title": title, "message": message,
               "link": f"{settings.SITE_URL}{link}" if link.startswith("/") else link}
        ctx.update(email_context or {})
        send_templated_email(email_subject or title, [user.email], email_template or "emails/notification.html", ctx)
    return notification


def notify_staff(permission_code, title, message, link="", category="system", email=False):
    """Alert every active staff member whose role grants `permission_code` (Super Admins always included)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from .models import Notification

    User = get_user_model()
    staff = User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(role__slug="super-admin") | Q(role__permissions__codename=permission_code)
    ).distinct()
    created = [
        Notification(user=u, title=title, message=message, link=link, category=category, is_staff_alert=True)
        for u in staff
    ]
    Notification.objects.bulk_create(created)
    if email:
        send_templated_email(title, [u.email for u in staff], "emails/notification.html",
                             {"title": title, "message": message,
                              "link": f"{settings.SITE_URL}{link}" if link.startswith("/") else link})
    return len(created)


def send_whatsapp(phone, message):
    """Optional WhatsApp integration (generic JSON API). No-op unless WHATSAPP_API_URL/TOKEN are configured."""
    if not (settings.WHATSAPP_API_URL and settings.WHATSAPP_API_TOKEN and phone):
        return False
    payload = json.dumps({"to": phone, "message": message}).encode()
    req = urllib.request.Request(
        settings.WHATSAPP_API_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except Exception:
        logger.exception("WhatsApp notification failed")
        return False
