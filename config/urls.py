from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.website_settings import views as site_views
from apps.website_settings.sitemaps import SITEMAPS

admin.site.site_header = "COZY internal administration"
admin.site.site_title = "COZY admin"

urlpatterns = [
    path("", site_views.home, name="home"),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    path(settings.DASHBOARD_URL, include("apps.dashboard.urls", namespace="dashboard")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("shop/", include("apps.products.urls", namespace="products")),
    path("cart/", include("apps.cart.urls", namespace="cart")),
    path("wishlist/", include("apps.wishlist.urls", namespace="wishlist")),
    path("orders/", include("apps.orders.urls", namespace="orders")),
    path("payments/", include("apps.payments.urls", namespace="payments")),
    path("shipping/", include("apps.shipping.urls", namespace="shipping")),
    path("reviews/", include("apps.reviews.urls", namespace="reviews")),
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("support/", include("apps.support.urls", namespace="support")),
    path("", include("apps.website_settings.urls", namespace="site")),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", site_views.robots_txt, name="robots_txt"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.website_settings.views.error_404"
handler500 = "apps.website_settings.views.error_500"
