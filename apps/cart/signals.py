from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Cart
from .services import SESSION_CART_KEY, merge_carts


@receiver(user_logged_in)
def merge_guest_cart(sender, request, user, **kwargs):
    if request is None or not hasattr(request, "session"):
        return
    cart_id = request.session.pop(SESSION_CART_KEY, None)
    session_cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if session_cart is not None:
        merge_carts(session_cart, user)
