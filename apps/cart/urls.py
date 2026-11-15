from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    path("add/", views.cart_add, name="add"),
    path("item/<int:item_id>/update/", views.cart_update, name="update"),
    path("item/<int:item_id>/remove/", views.cart_remove, name="remove"),
    path("item/<int:item_id>/move-to-wishlist/", views.move_to_wishlist, name="move_to_wishlist"),
    path("coupon/apply/", views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", views.remove_coupon, name="remove_coupon"),
    path("gift-wrap/", views.gift_wrap, name="gift_wrap"),
]
