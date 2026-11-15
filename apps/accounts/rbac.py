"""
COZY role-based access control.

Permissions and default roles are defined here and synchronised into the database
after every `migrate` (see signals.py). Roles and their permissions can then be
edited by the Super Admin from the dashboard.

Security note: permissions are always enforced on the server side through the
decorators / mixins below. Hiding menu items is only a convenience.
"""
from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

PERMISSIONS = [
    # (codename, name, module)
    ("dashboard.view", "View dashboard overview", "Dashboard"),
    ("products.manage", "Manage products, images and variants", "Catalogue"),
    ("categories.manage", "Manage categories and attributes", "Catalogue"),
    ("reviews.manage", "Moderate product reviews", "Catalogue"),
    ("inventory.manage", "Manage stock and inventory", "Inventory"),
    ("inventory.view", "View inventory and stock reports", "Inventory"),
    ("orders.view", "View orders", "Orders"),
    ("orders.manage", "Update orders, status and shipping", "Orders"),
    ("returns.manage", "Handle returns and cancellations", "Orders"),
    ("refunds.manage", "Process refunds", "Payments"),
    ("payments.view", "View payments", "Payments"),
    ("shipping.manage", "Manage shipping methods, pincodes and providers", "Shipping"),
    ("customers.view", "View customers", "Customers"),
    ("customers.manage", "Activate / deactivate customers", "Customers"),
    ("coupons.manage", "Manage coupons and offers", "Marketing"),
    ("content.manage", "Manage banners, pages, blog and homepage", "Content"),
    ("newsletter.manage", "Manage newsletter subscribers", "Marketing"),
    ("support.manage", "Handle support tickets", "Support"),
    ("reports.view", "View and export reports", "Reports"),
    ("settings.manage", "Manage website settings", "Settings"),
    ("users.manage", "Manage staff users", "Administration"),
    ("roles.manage", "Manage roles and permissions", "Administration"),
    ("audit.view", "View admin activity log", "Administration"),
]

ALL_CODES = [p[0] for p in PERMISSIONS]

ROLE_DEFINITIONS = {
    "super-admin": {
        "name": "Super Admin",
        "description": "Full system access, including roles, permissions and settings.",
        "staff": True,
        "permissions": ALL_CODES,
    },
    "admin": {
        "name": "Admin",
        "description": "Manages products, orders, customers, inventory and reports.",
        "staff": True,
        "permissions": [
            "dashboard.view", "products.manage", "categories.manage", "reviews.manage", "inventory.manage",
            "inventory.view", "orders.view", "orders.manage", "returns.manage", "refunds.manage",
            "payments.view", "shipping.manage", "customers.view", "customers.manage", "coupons.manage",
            "content.manage", "newsletter.manage", "support.manage", "reports.view", "users.manage", "audit.view",
        ],
    },
    "product-manager": {
        "name": "Product Manager",
        "description": "Product, category, image and variant management.",
        "staff": True,
        "permissions": ["dashboard.view", "products.manage", "categories.manage", "reviews.manage", "inventory.view"],
    },
    "order-manager": {
        "name": "Order Manager",
        "description": "Orders, status updates, shipping and return requests.",
        "staff": True,
        "permissions": ["dashboard.view", "orders.view", "orders.manage", "returns.manage", "shipping.manage", "payments.view"],
    },
    "inventory-manager": {
        "name": "Inventory Manager",
        "description": "Stock management and inventory reports.",
        "staff": True,
        "permissions": ["dashboard.view", "inventory.manage", "inventory.view", "reports.view"],
    },
    "support-staff": {
        "name": "Customer Support Staff",
        "description": "Customer inquiries, support tickets and permitted order information.",
        "staff": True,
        "permissions": ["dashboard.view", "support.manage", "orders.view", "customers.view"],
    },
    "content-manager": {
        "name": "Content Manager",
        "description": "Homepage banners, website pages, blogs and promotional content.",
        "staff": True,
        "permissions": ["dashboard.view", "content.manage", "newsletter.manage"],
    },
    "customer": {
        "name": "Customer",
        "description": "Own account, purchases, orders, tracking, wishlist and reviews.",
        "staff": False,
        "permissions": [],
    },
}


def sync_roles_and_permissions(reset_permissions=False):
    """Create missing permissions/roles. Existing role permissions are only reset on request."""
    from .models import AccessPermission, Role

    perm_objs = {}
    for code, name, module in PERMISSIONS:
        obj, _ = AccessPermission.objects.update_or_create(codename=code, defaults={"name": name, "module": module})
        perm_objs[code] = obj

    for slug, data in ROLE_DEFINITIONS.items():
        role, created = Role.objects.get_or_create(
            slug=slug,
            defaults={
                "name": data["name"],
                "description": data["description"],
                "is_staff_role": data["staff"],
                "is_system": True,
            },
        )
        if created or reset_permissions or slug == "super-admin":
            role.permissions.set([perm_objs[c] for c in data["permissions"]])


# ---------------------------------------------------------------------------
# Enforcement helpers
# ---------------------------------------------------------------------------
def _deny(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('accounts:login')}?next={request.get_full_path()}")
    raise PermissionDenied("You do not have permission to access this page.")


def staff_required(view_func):
    """Allow any active staff member (role with is_staff_role)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff_member:
            return view_func(request, *args, **kwargs)
        return _deny(request)

    return _wrapped


def permission_required(*codes, require_all=False):
    """Require one (default) or all of the given RBAC permission codes."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_authenticated and user.is_staff_member:
                checks = [user.has_access(c) for c in codes]
                if (all(checks) if require_all else any(checks)):
                    return view_func(request, *args, **kwargs)
            return _deny(request)

        return _wrapped

    return decorator


def super_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_super_admin:
            return view_func(request, *args, **kwargs)
        return _deny(request)

    return _wrapped


class PermissionRequiredMixin(AccessMixin):
    """Class-based equivalent of @permission_required. Set `required_permission`."""

    required_permission = "dashboard.view"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        if not (user.is_staff_member and user.has_access(self.required_permission)):
            raise PermissionDenied("You do not have permission to access this page.")
        return super().dispatch(request, *args, **kwargs)
