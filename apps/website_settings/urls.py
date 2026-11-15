from django.urls import path

from . import views

app_name = "site"

urlpatterns = [
    path("pages/<slug:slug>/", views.page_detail, name="page"),
    path("blog/", views.blog_list, name="blog_list"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
]
