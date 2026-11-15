from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("search/", views.search, name="search"),
    path("search/autocomplete/", views.autocomplete, name="autocomplete"),
    path("collections/<slug:slug>/", views.collection, name="collection"),
    path("category/<slug:slug>/", views.category_detail, name="category"),
    path("quick-view/<slug:slug>/", views.quick_view, name="quick_view"),
    path("<slug:slug>/", views.product_detail, name="detail"),
]
