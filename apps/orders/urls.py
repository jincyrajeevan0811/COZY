from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/summary/", views.checkout_summary, name="checkout_summary"),
    path("track/", views.track_order, name="track"),
    path("", views.order_list, name="list"),
    path("returns/", views.returns_and_cancellations, name="returns"),
    path("<str:order_number>/", views.order_detail, name="detail"),
    path("<str:order_number>/success/", views.order_success, name="success"),
    path("<str:order_number>/cancel/", views.cancel_order, name="cancel"),
    path("<str:order_number>/return/", views.return_order, name="return"),
    path("<str:order_number>/invoice/", views.invoice_pdf, name="invoice"),
]
