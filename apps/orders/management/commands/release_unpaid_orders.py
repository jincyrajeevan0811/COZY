from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services import OrderError, change_status


class Command(BaseCommand):
    help = "Cancel online-payment orders that were never paid and release their reserved stock. Run every 10-15 minutes (cron)."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=settings.UNPAID_ORDER_TIMEOUT_MINUTES)
        orders = Order.objects.filter(
            payment_method=Order.PAYMENT_RAZORPAY, payment_status__in=["pending", "failed"], status=Order.PENDING,
            created_at__lt=cutoff,
        )
        released = 0
        for order in orders:
            try:
                change_status(order, Order.CANCELLED, note="Payment not completed in time — stock released",
                              notify_customer=True)
                released += 1
            except OrderError as exc:
                self.stderr.write(f"{order.order_number}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Released {released} unpaid order(s)."))
