from django.urls import path

from . import views

app_name = "shipping"

urlpatterns = [
    path("pincode-check/", views.pincode_check, name="pincode_check"),
]
