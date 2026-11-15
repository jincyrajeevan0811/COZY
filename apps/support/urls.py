from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("new/", views.ticket_create, name="create"),
    path("<str:ticket_number>/", views.ticket_detail, name="detail"),
]
