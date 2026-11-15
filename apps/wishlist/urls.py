from django.urls import path

from . import views

app_name = "wishlist"

urlpatterns = [
    path("", views.wishlist_detail, name="detail"),
    path("toggle/<int:product_id>/", views.toggle, name="toggle"),
    path("item/<int:item_id>/move-to-cart/", views.move_to_cart, name="move_to_cart"),
    path("item/<int:item_id>/remove/", views.remove, name="remove"),
]
