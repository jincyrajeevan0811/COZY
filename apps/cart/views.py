from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.utils import is_ajax, safe_next_url
from apps.products.models import Product, ProductVariant

from .models import CartItem
from .services import CartError, add_to_cart, cart_item_count, get_cart, summarize


def cart_detail(request):
    cart = get_cart(request)
    summary = summarize(cart, request.user)
    if summary["coupon_error"] and cart and cart.coupon_id:
        messages.warning(request, f"Coupon {summary['coupon_code']}: {summary['coupon_error']}")
    for item in summary["issues"]:
        messages.warning(request, f"{item.product.name}: only {item.available_stock} available. Please update the quantity.")
    from apps.products.models import Product as P

    suggestions = P.objects.for_listing().filter(is_bestseller=True).exclude(
        id__in=[i.product_id for i in summary["items"]])[:4]
    return render(request, "cart/cart.html", {"cart": cart, "summary": summary, "suggestions": suggestions})


def cart_drawer(request):
    """HTML fragment for the slide-in mini bag."""
    cart = get_cart(request)
    summary = summarize(cart, request.user)
    return render(request, "cart/_drawer.html", {"cart": cart, "summary": summary})


@require_POST
def cart_add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    variant = None
    if request.POST.get("variant_id"):
        variant = get_object_or_404(ProductVariant, pk=request.POST.get("variant_id"), product=product)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    cart = get_cart(request, create=True)
    try:
        add_to_cart(cart, product, variant, quantity)
        ok, msg = True, f"{product.name} added to your bag."
    except CartError as exc:
        ok, msg = False, str(exc)

    if request.POST.get("buy_now") and ok:
        return redirect("orders:checkout")
    if is_ajax(request):
        return JsonResponse({"ok": ok, "message": msg, "cart_count": cart_item_count(request)}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, msg)
    return redirect(safe_next_url(request, reverse("cart:detail")))


@require_POST
def cart_update(request, item_id):
    cart = get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart) if cart else None
    if item is None:
        return redirect("cart:detail")
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = item.quantity
    if quantity <= 0:
        item.delete()
        messages.info(request, "Item removed from your bag.")
    else:
        try:
            add_to_cart(cart, item.product, item.variant, quantity, replace=True)
        except CartError as exc:
            messages.error(request, str(exc))
    return redirect("cart:detail")


@require_POST
def cart_remove(request, item_id):
    cart = get_cart(request)
    if cart:
        CartItem.objects.filter(pk=item_id, cart=cart).delete()
        messages.info(request, "Item removed from your bag.")
    return redirect("cart:detail")


@require_POST
def move_to_wishlist(request, item_id):
    if not request.user.is_authenticated:
        messages.info(request, "Sign in to save items to your wishlist.")
        return redirect("accounts:login")
    from apps.wishlist.models import Wishlist, WishlistItem

    cart = get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart) if cart else None
    if item:
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        WishlistItem.objects.get_or_create(wishlist=wishlist, product=item.product)
        item.delete()
        messages.success(request, "Moved to your wishlist.")
    return redirect("cart:detail")


@require_POST
def apply_coupon(request):
    from apps.coupons.models import Coupon

    code = (request.POST.get("code") or "").strip().upper()
    cart = get_cart(request)
    if not cart or not cart.items.exists():
        messages.error(request, "Your bag is empty.")
        return redirect("cart:detail")
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None:
        messages.error(request, "Invalid coupon code.")
        return redirect(safe_next_url(request, reverse("cart:detail")))
    cart.coupon = coupon
    summary = summarize(cart, request.user)
    if summary["coupon_error"]:
        cart.coupon = None
        messages.error(request, summary["coupon_error"])
    else:
        cart.save(update_fields=["coupon", "updated_at"])
        messages.success(request, f"Coupon {coupon.code} applied — you save ₹{summary['coupon_discount']}.")
    return redirect(safe_next_url(request, reverse("cart:detail")))


@require_POST
def remove_coupon(request):
    cart = get_cart(request)
    if cart and cart.coupon_id:
        cart.coupon = None
        cart.save(update_fields=["coupon", "updated_at"])
        messages.info(request, "Coupon removed.")
    return redirect(safe_next_url(request, reverse("cart:detail")))


@require_POST
def gift_wrap(request):
    cart = get_cart(request)
    if cart:
        cart.gift_wrap = request.POST.get("gift_wrap") == "on"
        cart.gift_message = (request.POST.get("gift_message") or "")[:250]
        cart.save(update_fields=["gift_wrap", "gift_message", "updated_at"])
        messages.success(request, "Gift options updated.")
    return redirect(safe_next_url(request, reverse("cart:detail")))
