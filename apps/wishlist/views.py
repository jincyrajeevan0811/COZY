from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cart.services import CartError, add_to_cart, cart_item_count, get_cart
from apps.core.utils import is_ajax, safe_next_url
from apps.products.models import Product

from .models import Wishlist, WishlistItem


@login_required
def wishlist_detail(request):
    items = (
        WishlistItem.objects.filter(wishlist__user=request.user)
        .select_related("product", "product__category")
        .prefetch_related("product__images")
    )
    return render(request, "accounts/wishlist.html", {"items": items})


@require_POST
def toggle(request, product_id):
    if not request.user.is_authenticated:
        login_url = f"{reverse('accounts:login')}?{urlencode({'next': request.META.get('HTTP_REFERER', '/')})}"
        if is_ajax(request):
            return JsonResponse({"ok": False, "login_required": True, "login_url": login_url}, status=401)
        return redirect(login_url)
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    item = WishlistItem.objects.filter(wishlist=wishlist, product=product).first()
    if item:
        item.delete()
        added, msg = False, "Removed from your wishlist."
    else:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        added, msg = True, "Saved to your wishlist."
    count = wishlist.items.count()
    if is_ajax(request):
        return JsonResponse({"ok": True, "added": added, "message": msg, "wishlist_count": count})
    messages.success(request, msg)
    return redirect(safe_next_url(request, reverse("wishlist:detail")))


@login_required
@require_POST
def move_to_cart(request, item_id):
    item = get_object_or_404(WishlistItem, pk=item_id, wishlist__user=request.user)
    if item.product.has_variants:
        messages.info(request, "Please choose an option for this product.")
        return redirect(item.product.get_absolute_url())
    try:
        add_to_cart(get_cart(request, create=True), item.product, None, 1)
        item.delete()
        messages.success(request, f"{item.product.name} moved to your bag.")
    except CartError as exc:
        messages.error(request, str(exc))
    if is_ajax(request):
        return JsonResponse({"ok": True, "cart_count": cart_item_count(request)})
    return redirect("wishlist:detail")


@login_required
@require_POST
def remove(request, item_id):
    WishlistItem.objects.filter(pk=item_id, wishlist__user=request.user).delete()
    messages.info(request, "Removed from your wishlist.")
    return redirect("wishlist:detail")
