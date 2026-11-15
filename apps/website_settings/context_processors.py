from django.conf import settings
from django.core.cache import cache
from django.db.models import Prefetch

from .models import StaticPage, WebsiteSetting


def _menu_categories():
    from apps.categories.models import Category, SubCategory

    data = cache.get("cozy:menu-categories")
    if data is None:
        data = list(
            Category.objects.active().filter(show_in_menu=True).prefetch_related(
                Prefetch("subcategories", queryset=SubCategory.objects.active(), to_attr="active_subs")
            )
        )
        cache.set("cozy:menu-categories", data, 300)
    return data


def _footer_pages():
    pages = cache.get("cozy:footer-pages")
    if pages is None:
        pages = {"help": [], "company": [], "policies": []}
        for page in StaticPage.objects.filter(is_active=True).exclude(footer_column=""):
            pages.setdefault(page.footer_column, []).append(page)
        cache.set("cozy:footer-pages", pages, 300)
    return pages


def site_context(request):
    # Skip the storefront queries for the Django admin.
    if request.path.startswith("/" + settings.DJANGO_ADMIN_URL):
        return {}
    from apps.cart.services import cart_item_count

    context = {
        "site": WebsiteSetting.load(),
        "menu_categories": _menu_categories(),
        "footer_pages": _footer_pages(),
        "cart_count": cart_item_count(request),
        "wishlist_count": 0,
        "wishlist_ids": set(),
        "unread_notifications": 0,
        "razorpay_enabled": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
        "SITE_URL": settings.SITE_URL,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.wishlist.models import WishlistItem

        ids = set(WishlistItem.objects.filter(wishlist__user=user).values_list("product_id", flat=True))
        context["wishlist_ids"] = ids
        context["wishlist_count"] = len(ids)
        context["unread_notifications"] = user.notifications.filter(is_read=False, is_staff_alert=False).count()
    return context


def clear_site_caches():
    cache.delete_many(["cozy:menu-categories", "cozy:footer-pages", WebsiteSetting.CACHE_KEY])
