"""Customers, staff users, roles & permissions, review moderation and support tickets."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import AccessPermission, Role, User
from apps.accounts.rbac import permission_required, super_admin_required
from apps.orders.models import Order
from apps.reviews.models import ProductReview
from apps.support.forms import ReplyForm
from apps.support.models import SupportTicket
from apps.support.services import add_reply

from .audit import log_activity
from .forms import RoleForm, StaffUserForm, TicketUpdateForm


def _customers():
    return User.objects.filter(Q(role__isnull=True) | Q(role__is_staff_role=False), is_superuser=False)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@permission_required("customers.view")
def customer_list(request):
    qs = _customers().annotate(
        order_count=Count("orders", distinct=True),
        total_spent=Sum("orders__grand_total", filter=Q(orders__payment_status__in=["paid", "partially_refunded"])),
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
    if request.GET.get("status") == "active":
        qs = qs.filter(is_active=True)
    elif request.GET.get("status") == "inactive":
        qs = qs.filter(is_active=False)
    sort = request.GET.get("sort", "-date_joined")
    if sort.lstrip("-") in ("date_joined", "order_count", "total_spent", "first_name"):
        qs = qs.order_by(sort)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/customers/list.html", {"page_obj": page, "q": q})


@permission_required("customers.view")
def customer_detail(request, pk):
    customer = get_object_or_404(User.objects.select_related("profile", "role"), pk=pk)
    if customer.is_staff_member and not request.user.has_access("users.manage"):
        raise PermissionDenied
    orders = Order.objects.filter(user=customer)
    paid = orders.filter(payment_status__in=["paid", "partially_refunded"])
    context = {
        "customer": customer,
        "orders": orders[:20],
        "order_count": orders.count(),
        "total_spent": paid.aggregate(t=Sum("grand_total"))["t"] or 0,
        "addresses": customer.addresses.all(),
        "reviews": customer.reviews.select_related("product")[:10],
        "tickets": SupportTicket.objects.filter(user=customer)[:10],
        "can_manage": request.user.has_access("customers.manage"),
    }
    return render(request, "dashboard/customers/detail.html", context)


@permission_required("customers.manage")
@require_POST
def customer_toggle(request, pk):
    customer = get_object_or_404(User, pk=pk)
    if customer == request.user:
        messages.error(request, "You cannot deactivate your own account.")
    elif customer.is_super_admin and not request.user.is_super_admin:
        messages.error(request, "Only a Super Admin can change another Super Admin.")
    elif customer.is_staff_member and not request.user.has_access("users.manage"):
        messages.error(request, "You are not allowed to change staff accounts.")
    else:
        customer.is_active = not customer.is_active
        customer.save(update_fields=["is_active"])
        log_activity(request, "update", customer, "Activated" if customer.is_active else "Deactivated")
        messages.success(request, f"{customer.email} {'activated' if customer.is_active else 'deactivated'}.")
    return redirect("dashboard:customer_detail", pk=pk)


# ---------------------------------------------------------------------------
# Staff users
# ---------------------------------------------------------------------------
@permission_required("users.manage")
def staff_list(request):
    qs = User.objects.filter(Q(role__is_staff_role=True) | Q(is_superuser=True)).select_related("role")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if request.GET.get("role"):
        qs = qs.filter(role__slug=request.GET["role"])
    return render(request, "dashboard/staff/list.html", {
        "staff": qs.order_by("role__name", "first_name"), "q": q, "roles": Role.objects.filter(is_staff_role=True),
    })


@permission_required("users.manage")
def staff_form(request, pk=None):
    member = get_object_or_404(User, pk=pk) if pk else None
    if member and member.is_super_admin and not request.user.is_super_admin:
        raise PermissionDenied("Only a Super Admin can edit another Super Admin.")
    form = StaffUserForm(request.POST or None, instance=member, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        role = form.cleaned_data["role"]
        if role.slug == Role.SUPER_ADMIN and not request.user.is_super_admin:
            raise PermissionDenied("Only a Super Admin can assign the Super Admin role.")
        if member and member == request.user and not form.cleaned_data["is_active"]:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            user = form.save()
            log_activity(request, "update" if pk else "create", user, f"Role: {role.name}")
            messages.success(request, f"Staff member {user.email} saved.")
            return redirect("dashboard:staff_list")
    return render(request, "dashboard/staff/form.html", {"form": form, "member": member})


# ---------------------------------------------------------------------------
# Roles & permissions (Super Admin only)
# ---------------------------------------------------------------------------
@super_admin_required
def role_list(request):
    roles = Role.objects.annotate(user_count=Count("users"), perm_count=Count("permissions", distinct=True))
    return render(request, "dashboard/staff/roles.html", {"roles": roles})


@super_admin_required
def role_form(request, pk=None):
    role = get_object_or_404(Role, pk=pk) if pk else None
    form = RoleForm(request.POST or None, instance=role)
    if role and role.slug == Role.SUPER_ADMIN:
        form.fields["permissions"].disabled = True
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        log_activity(request, "update" if pk else "create", obj, f"{obj.permissions.count()} permissions")
        messages.success(request, f"Role “{obj.name}” saved.")
        return redirect("dashboard:role_list")
    perms_by_module = {}
    for perm in AccessPermission.objects.all():
        perms_by_module.setdefault(perm.module, []).append(perm)
    selected = set(role.permissions.values_list("pk", flat=True)) if role else set()
    if request.method == "POST":
        selected = {int(p) for p in request.POST.getlist("permissions") if p.isdigit()}
    return render(request, "dashboard/staff/role_form.html", {
        "form": form, "role": role, "perms_by_module": perms_by_module, "selected": selected,
    })


@super_admin_required
@require_POST
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if role.is_system:
        messages.error(request, "System roles cannot be deleted.")
    elif role.users.exists():
        messages.error(request, "Reassign the users of this role before deleting it.")
    else:
        log_activity(request, "delete", role)
        role.delete()
        messages.success(request, "Role deleted.")
    return redirect("dashboard:role_list")


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
@permission_required("reviews.manage")
def review_list(request):
    qs = ProductReview.objects.select_related("product", "user").prefetch_related("images")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    if request.GET.get("rating"):
        qs = qs.filter(rating=request.GET["rating"])
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(comment__icontains=q) | Q(user__email__icontains=q))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "dashboard/reviews/list.html", {
        "page_obj": page, "status": status, "q": q,
        "pending_count": ProductReview.objects.filter(status="pending").count(),
    })


@permission_required("reviews.manage")
@require_POST
def review_action(request, pk):
    review = get_object_or_404(ProductReview, pk=pk)
    action = request.POST.get("action")
    if action in ("approved", "rejected"):
        review.status = action
        review.admin_reply = request.POST.get("admin_reply", review.admin_reply)[:2000]
        review.save()
        log_activity(request, "status", review, f"Review {action}")
        messages.success(request, f"Review {action}.")
    elif action == "reply":
        review.admin_reply = request.POST.get("admin_reply", "")[:2000]
        review.save(update_fields=["admin_reply", "updated_at"])
        messages.success(request, "Reply saved.")
    elif action == "delete":
        log_activity(request, "delete", review)
        review.delete()
        messages.success(request, "Review deleted.")
    return redirect(request.META.get("HTTP_REFERER") or "dashboard:review_list")


# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------
@permission_required("support.manage")
def ticket_list(request):
    qs = SupportTicket.objects.select_related("user", "assigned_to", "order")
    for field in ("status", "priority", "category"):
        if request.GET.get(field):
            qs = qs.filter(**{field: request.GET[field]})
    if request.GET.get("mine"):
        qs = qs.filter(assigned_to=request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(ticket_number__icontains=q) | Q(subject__icontains=q) | Q(email__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    counts = dict(SupportTicket.objects.values_list("status").annotate(n=Count("id")))
    return render(request, "dashboard/support/list.html", {
        "page_obj": page, "q": q, "counts": counts, "status_choices": SupportTicket.STATUS_CHOICES,
        "priority_choices": SupportTicket.PRIORITY_CHOICES,
    })


@permission_required("support.manage")
def ticket_detail(request, pk):
    ticket = get_object_or_404(SupportTicket.objects.select_related("user", "order", "assigned_to"), pk=pk)
    reply_form = ReplyForm(request.POST if "reply" in request.POST else None)
    update_form = TicketUpdateForm(request.POST if "update" in request.POST else None, instance=ticket)
    if request.method == "POST":
        if "reply" in request.POST and reply_form.is_valid():
            add_reply(ticket, request.user, reply_form.cleaned_data["message"], is_staff=True)
            if not ticket.assigned_to_id:
                SupportTicket.objects.filter(pk=ticket.pk).update(assigned_to=request.user)
            messages.success(request, "Reply sent to the customer.")
            return redirect("dashboard:ticket_detail", pk=pk)
        if "update" in request.POST and update_form.is_valid():
            update_form.save()
            log_activity(request, "update", ticket, f"Status {ticket.status}, priority {ticket.priority}")
            messages.success(request, "Ticket updated.")
            return redirect("dashboard:ticket_detail", pk=pk)
    return render(request, "dashboard/support/detail.html", {
        "ticket": ticket, "ticket_messages": ticket.messages.select_related("sender"),
        "reply_form": reply_form, "update_form": update_form,
    })
