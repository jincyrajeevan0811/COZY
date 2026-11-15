"""
Core business-flow tests for COZY.

Run with:  python manage.py test
"""
import hashlib
import hmac
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Address, Role, User
from apps.accounts.rbac import sync_roles_and_permissions
from apps.cart.models import Cart
from apps.cart.services import CartError, add_to_cart, summarize
from apps.categories.models import Category
from apps.coupons.models import Coupon
from apps.inventory.models import StockHistory
from apps.inventory.services import InsufficientStock, adjust_stock, get_inventory
from apps.orders.models import Order
from apps.orders.services import OrderError, change_status, place_order
from apps.payments import razorpay_client
from apps.products.models import Product
from apps.shipping.models import ShippingMethod
from apps.website_settings.models import WebsiteSetting


class CozyTestMixin:
    def setUp(self):
        sync_roles_and_permissions()
        self.site = WebsiteSetting.load()
        self.category = Category.objects.create(name="Earrings")
        self.product = Product.objects.create(name="Pearl Drops", sku="CZ-T-1", category=self.category,
                                              price=Decimal("500"), original_price=Decimal("800"))
        adjust_stock(get_inventory(self.product), 5, StockHistory.STOCK_IN)
        self.method = ShippingMethod.objects.create(name="Standard", code="standard", charge=Decimal("50"))
        self.user = User.objects.create_user(email="asha@example.com", password="S3cure-pass!", first_name="Asha")
        self.address = Address.objects.create(user=self.user, full_name="Asha", phone="9876543210", line1="1 MG Road",
                                              city="Kochi", state="Kerala", pincode="682001")


class InventoryTests(CozyTestMixin, TestCase):
    def test_stock_cannot_go_negative(self):
        with self.assertRaises(InsufficientStock):
            adjust_stock(get_inventory(self.product), -6, StockHistory.STOCK_OUT)
        self.assertEqual(self.product.stock_quantity, 5)

    def test_history_is_recorded(self):
        adjust_stock(get_inventory(self.product), -2, StockHistory.STOCK_OUT, note="damaged")
        self.assertEqual(StockHistory.objects.filter(movement_type="out").count(), 1)
        self.assertEqual(self.product.stock_quantity, 3)


class CartTests(CozyTestMixin, TestCase):
    def test_cannot_add_more_than_stock(self):
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(CartError):
            add_to_cart(cart, self.product, None, 6)

    def test_summary_totals(self):
        cart = Cart.objects.create(user=self.user)
        add_to_cart(cart, self.product, None, 2)
        summary = summarize(cart, self.user, self.method)
        self.assertEqual(summary["subtotal"], Decimal("1000.00"))
        self.assertEqual(summary["product_savings"], Decimal("600.00"))
        self.assertEqual(summary["shipping"], Decimal("0.00"))  # above the ₹999 free-shipping threshold

    def test_coupon_minimum_order(self):
        coupon = Coupon.objects.create(code="FLAT100", discount_type="fixed", value=Decimal("100"),
                                       min_order_value=Decimal("999"))
        discount, error = coupon.evaluate(self.user, [(self.product, Decimal("500"))], Decimal("500"))
        self.assertEqual(discount, 0)
        self.assertTrue(error)
        discount, error = coupon.evaluate(self.user, [(self.product, Decimal("1000"))], Decimal("1000"))
        self.assertEqual(discount, Decimal("100.00"))
        self.assertEqual(error, "")


class OrderFlowTests(CozyTestMixin, TestCase):
    def _order(self, qty=2, method="cod"):
        cart = Cart.objects.create(user=self.user)
        add_to_cart(cart, self.product, None, qty)
        return place_order(user=self.user, cart=cart, address=self.address, shipping_method=self.method,
                           payment_method=method)

    def test_cod_order_reserves_stock_and_clears_cart(self):
        order = self._order()
        self.assertEqual(order.status, Order.PENDING)
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertFalse(Cart.objects.get(user=self.user).items.exists())
        self.assertEqual(order.status_history.count(), 1)

    def test_cancel_restores_stock(self):
        order = self._order()
        change_status(order, Order.CANCELLED, note="test", notify_customer=False)
        self.assertEqual(self.product.stock_quantity, 5)

    def test_invalid_transition_rejected(self):
        order = self._order()
        with self.assertRaises(OrderError):
            change_status(order, Order.DELIVERED)

    def test_delivery_marks_cod_paid(self):
        order = self._order()
        for status in (Order.CONFIRMED, Order.PACKED, Order.SHIPPED, Order.DELIVERED):
            order = change_status(order, status, notify_customer=False)
        self.assertEqual(order.payment_status, "paid")
        self.assertTrue(order.can_return)

    def test_customer_cannot_view_another_customers_order(self):
        order = self._order()
        other = User.objects.create_user(email="other@example.com", password="S3cure-pass!", first_name="O")
        self.client.force_login(other)
        response = self.client.get(reverse("orders:detail", args=[order.order_number]))
        self.assertEqual(response.status_code, 404)


@override_settings(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="whsec")
class RazorpaySignatureTests(TestCase):
    def test_payment_signature(self):
        sig = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
        self.assertTrue(razorpay_client.verify_payment_signature("order_1", "pay_1", sig))
        self.assertFalse(razorpay_client.verify_payment_signature("order_1", "pay_1", "tampered"))

    def test_webhook_signature(self):
        body = b'{"event":"payment.captured"}'
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        self.assertTrue(razorpay_client.verify_webhook_signature(body, sig))
        self.assertFalse(razorpay_client.verify_webhook_signature(body, "bad"))


class RBACTests(CozyTestMixin, TestCase):
    def test_customer_cannot_open_dashboard(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard:order_list")).status_code, 403)

    def test_content_manager_limited_access(self):
        staff = User.objects.create_user(email="cm@example.com", password="S3cure-pass!", first_name="C",
                                         role=Role.objects.get(slug="content-manager"))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("dashboard:banner_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:order_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:role_list")).status_code, 403)

    def test_super_admin_has_everything(self):
        admin = User.objects.create_superuser(email="boss@example.com", password="S3cure-pass!", first_name="B")
        self.assertTrue(admin.has_access("roles.manage"))
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)


class StorefrontSmokeTests(CozyTestMixin, TestCase):
    def test_public_pages_render(self):
        for name, args in [("home", []), ("products:list", []), ("products:detail", [self.product.slug]),
                           ("products:category", [self.category.slug]), ("cart:detail", []), ("site:faq", []),
                           ("site:contact", []), ("orders:track", []), ("robots_txt", [])]:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 200, name)

    def test_search_and_autocomplete(self):
        self.assertContains(self.client.get(reverse("products:search"), {"q": "pearl"}), "Pearl Drops")
        data = self.client.get(reverse("products:autocomplete"), {"q": "pea"}).json()
        self.assertEqual(data["products"][0]["name"], "Pearl Drops")
