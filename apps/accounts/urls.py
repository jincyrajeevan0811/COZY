from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("verify-resend/", views.resend_verification, name="resend_verification"),
    path("", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("password/change/", views.change_password, name="change_password"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/new/", views.address_form, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_form, name="address_edit"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:pk>/default/", views.address_set_default, name="address_default"),
    path("reviews/", views.my_reviews, name="reviews"),
    path("offers/", views.offers, name="offers"),
    path("payments/", views.payment_history, name="payments"),
    path("password/reset/", views.password_reset, name="password_reset"),
    path("password/reset/sent/", views.password_reset_done, name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("password/reset/complete/", views.password_reset_complete, name="password_reset_complete"),
]
