from django.urls import path

from apps.reports import views as report_views

from . import views, views_catalog, views_orders, views_people
from .crud import build_crud_views
from .registry import CRUD_MODULES

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/charts/", views.chart_data, name="chart_data"),
    path("notifications/", views.notifications, name="notifications"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("settings/", views.site_settings, name="settings"),
    # Products & inventory
    path("products/", views_catalog.product_list, name="product_list"),
    path("products/new/", views_catalog.product_form, name="product_create"),
    path("products/<int:pk>/edit/", views_catalog.product_form, name="product_edit"),
    path("products/<int:pk>/toggle/", views_catalog.product_toggle, name="product_toggle"),
    path("products/<int:pk>/delete/", views_catalog.product_delete, name="product_delete"),
    path("products/bulk-action/", views_catalog.product_bulk_action, name="product_bulk_action"),
    path("products/bulk-upload/", views_catalog.product_bulk_upload, name="product_bulk_upload"),
    path("products/bulk-upload/template.csv", views_catalog.product_upload_template, name="product_upload_template"),
    path("inventory/", views_catalog.inventory_list, name="inventory_list"),
    path("inventory/<int:pk>/adjust/", views_catalog.inventory_adjust, name="inventory_adjust"),
    path("inventory/history/", views_catalog.stock_history, name="stock_history"),
    # Orders
    path("orders/", views_orders.order_list, name="order_list"),
    path("orders/<str:order_number>/", views_orders.order_detail, name="order_detail"),
    path("orders/<str:order_number>/status/", views_orders.order_update_status, name="order_update_status"),
    path("orders/<str:order_number>/shipment/", views_orders.order_update_shipment, name="order_update_shipment"),
    path("orders/<str:order_number>/note/", views_orders.order_update_note, name="order_update_note"),
    path("orders/<str:order_number>/print/", views_orders.order_print, name="order_print"),
    path("returns/", views_orders.return_list, name="return_list"),
    path("returns/<int:pk>/", views_orders.return_detail, name="return_detail"),
    path("refunds/", views_orders.refund_list, name="refund_list"),
    path("refunds/<int:pk>/process/", views_orders.refund_process, name="refund_process"),
    path("payments/", views_orders.payment_list, name="payment_list"),
    path("abandoned-carts/", views_orders.abandoned_carts, name="abandoned_carts"),
    path("abandoned-carts/<int:pk>/remind/", views_orders.abandoned_cart_remind, name="abandoned_cart_remind"),
    # People
    path("customers/", views_people.customer_list, name="customer_list"),
    path("customers/<int:pk>/", views_people.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/toggle/", views_people.customer_toggle, name="customer_toggle"),
    path("staff/", views_people.staff_list, name="staff_list"),
    path("staff/new/", views_people.staff_form, name="staff_create"),
    path("staff/<int:pk>/edit/", views_people.staff_form, name="staff_edit"),
    path("roles/", views_people.role_list, name="role_list"),
    path("roles/new/", views_people.role_form, name="role_create"),
    path("roles/<int:pk>/edit/", views_people.role_form, name="role_edit"),
    path("roles/<int:pk>/delete/", views_people.role_delete, name="role_delete"),
    path("reviews/", views_people.review_list, name="review_list"),
    path("reviews/<int:pk>/action/", views_people.review_action, name="review_action"),
    path("support/", views_people.ticket_list, name="ticket_list"),
    path("support/<int:pk>/", views_people.ticket_detail, name="ticket_detail"),
    # Reports
    path("reports/", report_views.report_view, name="reports"),
    path("reports/<slug:key>/", report_views.report_view, name="report"),
]

for _cfg in CRUD_MODULES:
    urlpatterns += build_crud_views(_cfg)
