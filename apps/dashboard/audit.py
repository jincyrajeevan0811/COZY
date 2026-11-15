import logging

from apps.core.utils import client_ip

from .models import AdminActivityLog

logger = logging.getLogger(__name__)


def log_activity(request, action, obj=None, description="", object_type=None):
    try:
        AdminActivityLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            object_type=object_type or (obj._meta.verbose_name.title() if obj is not None else ""),
            object_id=str(getattr(obj, "pk", "") or ""),
            object_repr=str(obj)[:200] if obj is not None else "",
            description=description[:500],
            ip_address=client_ip(request) or None,
        )
    except Exception:  # audit logging must never break the action itself
        logger.exception("Could not write audit log")
