from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pay/<str:order_number>/", views.pay, name="pay"),
    path("verify/", views.verify, name="verify"),
    path("failed/<str:order_number>/", views.failed, name="failed"),
    path("webhook/razorpay/", views.webhook, name="webhook"),
]
