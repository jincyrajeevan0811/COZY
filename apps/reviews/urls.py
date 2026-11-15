from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("write/<int:product_id>/", views.write_review, name="write"),
]
