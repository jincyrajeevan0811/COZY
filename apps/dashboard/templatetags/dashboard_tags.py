from django import template

register = template.Library()


@register.filter
def can(user, codename):
    """{% if request.user|can:"orders.manage" %} — UI convenience only; views enforce permissions."""
    return bool(user and user.is_authenticated and user.has_access(codename))


@register.simple_tag(takes_context=True)
def active(context, *prefixes):
    """Return 'active' when the current URL name starts with one of the prefixes."""
    match = getattr(context["request"], "resolver_match", None)
    name = match.url_name if match else ""
    return "active" if any(name.startswith(p) for p in prefixes) else ""


@register.simple_tag(takes_context=True)
def staff_unread(context):
    user = context["request"].user
    if not user.is_authenticated:
        return 0
    return user.notifications.filter(is_staff_alert=True, is_read=False).count()


@register.simple_tag(takes_context=True)
def staff_alerts(context, limit=6):
    user = context["request"].user
    if not user.is_authenticated:
        return []
    return list(user.notifications.filter(is_staff_alert=True)[:limit])
