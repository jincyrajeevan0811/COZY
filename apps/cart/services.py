from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.core.utils import money

from .models import Cart, CartItem

SESSION_CART_KEY = "cart_id"
MAX_QTY_PER_LINE = 10


class CartError(Exception):
    pass


def _cart_queryset():
    return Cart.objects.select_related("coupon")


def get_cart(request, create=False):
    """Return the current cart (user cart when signed in, session cart for guests)."""
    if request.user.is_authenticated:
        cart = _cart_queryset().filter(user=request.user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=request.user)
        return cart
    cart_id = request.session.get(SESSION_CART_KEY)
    cart = _cart_queryset().filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if cart is None and create:
        cart = Cart.objects.create()
        request.session[SESSION_CART_KEY] = cart.pk
    return cart


def cart_item_count(request):
    if request.user.is_authenticated:
        qs = CartItem.objects.filter(cart__user=request.user)
    else:
        cart_id = request.session.get(SESSION_CART_KEY)
        if not cart_id:
            return 0
        qs = CartItem.objects.filter(cart_id=cart_id, cart__user__isnull=True)
    return qs.aggregate(t=Sum("quantity"))["t"] or 0


def cart_items(cart):
    if cart is None:
        return []
    return list(
        cart.items.select_related("product", "product__category", "variant", "variant__inventory")
        .prefetch_related("product__images")
    )


def _validate_target(product, variant):
    if not product.is_active:
        raise CartError("This product is currently unavailable.")
    if product.has_variants and variant is None:
        raise CartError("Please select an option (colour / size) before adding to cart.")
    if variant is not None and (variant.product_id != product.id or not variant.is_active):
        raise CartError("The selected option is not available.")


@transaction.atomic
def add_to_cart(cart, product, variant=None, quantity=1, replace=False):
    _validate_target(product, variant)
    quantity = max(1, int(quantity))
    item = CartItem.objects.select_for_update().filter(cart=cart, product=product, variant=variant).first()
    new_qty = quantity if (replace or item is None) else item.quantity + quantity
    stock = variant.stock_quantity if variant else product.stock_quantity
    if stock <= 0:
        raise CartError("Sorry, this item is out of stock.")
    if new_qty > stock:
        raise CartError(f"Only {stock} left in stock.")
    if new_qty > MAX_QTY_PER_LINE:
        raise CartError(f"You can buy up to {MAX_QTY_PER_LINE} of this item per order.")
    if item is None:
        item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=new_qty)
    else:
        item.quantity = new_qty
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    return item


@transaction.atomic
def merge_carts(session_cart, user):
    """Merge a guest cart into the user's cart after login (respecting stock limits)."""
    user_cart, _ = Cart.objects.get_or_create(user=user)
    if session_cart is None or session_cart.pk == user_cart.pk:
        return user_cart
    for item in session_cart.items.select_related("product", "variant"):
        existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
        stock = item.available_stock
        qty = item.quantity + (existing.quantity if existing else 0)
        qty = min(qty, stock, MAX_QTY_PER_LINE)
        if qty <= 0:
            continue
        if existing:
            existing.quantity = qty
            existing.save(update_fields=["quantity"])
        else:
            CartItem.objects.create(cart=user_cart, product=item.product, variant=item.variant, quantity=qty)
    if session_cart.coupon_id and not user_cart.coupon_id:
        user_cart.coupon_id = session_cart.coupon_id
    if session_cart.gift_wrap:
        user_cart.gift_wrap = True
        user_cart.gift_message = session_cart.gift_message
    user_cart.save()
    session_cart.delete()
    return user_cart


def summarize(cart, user=None, shipping_method=None, payment_method=None, items=None):
    """Compute all cart/checkout totals in one place (used by cart page, checkout and order creation)."""
    from apps.shipping.services import active_methods, shipping_charge
    from apps.website_settings.models import WebsiteSetting

    site = WebsiteSetting.load()
    items = cart_items(cart) if items is None else items
    subtotal = sum((i.line_total for i in items), Decimal("0"))
    mrp_total = sum((i.line_original_total for i in items), Decimal("0"))
    product_savings = mrp_total - subtotal
    issues = [i for i in items if not i.is_available]

    coupon_discount = Decimal("0")
    coupon_error = ""
    coupon = cart.coupon if cart else None
    if coupon and items:
        coupon_discount, coupon_error = coupon.evaluate(user, [(i.product, i.line_total) for i in items], subtotal)
    after_discount = subtotal - coupon_discount

    if shipping_method is None:
        shipping_method = active_methods().first()
    shipping = shipping_charge(shipping_method, after_discount) if items else Decimal("0")

    gift_wrap_charge = site.gift_wrap_charge if (cart and cart.gift_wrap and site.gift_wrap_enabled and items) else Decimal("0")
    cod_charge = site.cod_extra_charge if payment_method == "cod" else Decimal("0")

    rate = site.tax_percent or Decimal("0")
    taxable = after_discount
    if site.prices_include_tax:
        tax = taxable * rate / (Decimal("100") + rate) if rate else Decimal("0")
        tax_added = Decimal("0")
    else:
        tax = taxable * rate / Decimal("100")
        tax_added = tax

    grand_total = after_discount + shipping + gift_wrap_charge + cod_charge + tax_added
    remaining_for_free = Decimal("0")
    if site.free_shipping_threshold and after_discount < site.free_shipping_threshold:
        remaining_for_free = site.free_shipping_threshold - after_discount

    return {
        "items": items,
        "item_count": sum(i.quantity for i in items),
        "subtotal": money(subtotal),
        "mrp_total": money(mrp_total),
        "product_savings": money(product_savings),
        "coupon": coupon if (coupon and not coupon_error) else None,
        "coupon_code": coupon.code if coupon else "",
        "coupon_discount": money(coupon_discount),
        "coupon_error": coupon_error,
        "shipping_method": shipping_method,
        "shipping": money(shipping),
        "gift_wrap": bool(cart and cart.gift_wrap),
        "gift_wrap_charge": money(gift_wrap_charge),
        "cod_charge": money(cod_charge),
        "tax": money(tax),
        "tax_percent": rate,
        "tax_inclusive": site.prices_include_tax,
        "grand_total": money(grand_total),
        "total_savings": money(product_savings + coupon_discount),
        "remaining_for_free_shipping": money(remaining_for_free),
        "issues": issues,
        "has_issues": bool(issues),
    }
