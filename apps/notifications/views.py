from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.utils import is_ajax

from .models import Notification


@login_required
def notification_list(request):
    qs = request.user.notifications.filter(is_staff_alert=False)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "accounts/notifications.html", {"page_obj": page, "notifications": page.object_list})


@login_required
def open_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    link = notification.link
    if link and url_has_allowed_host_and_scheme(link, allowed_hosts={request.get_host()}):
        return redirect(link)
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    staff = request.POST.get("scope") == "staff"
    request.user.notifications.filter(is_read=False, is_staff_alert=staff).update(is_read=True)
    if is_ajax(request):
        return JsonResponse({"ok": True})
    return redirect(request.META.get("HTTP_REFERER") or "notifications:list")
