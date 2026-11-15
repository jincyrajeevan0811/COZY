"""
All stock changes go through `adjust_stock` so that:
  * rows are locked (select_for_update) inside a transaction,
  * inventory can never become negative,
  * every movement is written to StockHistory,
  * low / out-of-stock alerts are raised for staff.
"""
from django.db import transaction

from .models import Inventory, StockHistory


class InsufficientStock(Exception):
    def __init__(self, inventory, requested):
        self.inventory = inventory
        self.requested = requested
        super().__init__(
            f"Only {inventory.quantity} left for {inventory.label} (requested {requested})."
        )


def get_inventory(product, variant=None):
    inv, _ = Inventory.objects.get_or_create(product=product, variant=variant)
    return inv


@transaction.atomic
def adjust_stock(inventory, change, movement_type, user=None, reference="", note=""):
    """Apply a +/- change to an inventory row. Raises InsufficientStock if it would go negative."""
    inv = Inventory.objects.select_for_update().select_related("product", "variant").get(pk=inventory.pk)
    new_qty = inv.quantity + int(change)
    if new_qty < 0:
        raise InsufficientStock(inv, abs(int(change)))
    previous = inv.quantity
    inv.quantity = new_qty
    inv.save(update_fields=["quantity", "updated_at"])
    StockHistory.objects.create(
        inventory=inv,
        movement_type=movement_type,
        quantity_change=int(change),
        balance_after=new_qty,
        reference=reference[:100],
        note=note[:255],
        user=user if (user and user.is_authenticated) else None,
    )
    _maybe_alert(inv, previous)
    return inv


@transaction.atomic
def set_stock(inventory, new_quantity, user=None, note="Manual stock count"):
    inv = Inventory.objects.select_for_update().get(pk=inventory.pk)
    change = int(new_quantity) - inv.quantity
    if change == 0:
        return inv
    return adjust_stock(inv, change, StockHistory.ADJUSTMENT, user=user, note=note)


def _maybe_alert(inv, previous):
    """Notify staff when stock crosses into low or out-of-stock levels."""
    from django.urls import reverse

    from apps.notifications.services import notify_staff

    link = reverse("dashboard:inventory_list") + f"?q={inv.sku}"
    if inv.quantity == 0 and previous > 0:
        transaction.on_commit(lambda: notify_staff(
            "inventory.manage", "Out of stock", f"{inv.label} ({inv.sku}) is now out of stock.", link=link,
            category="stock"))
    elif 0 < inv.quantity <= inv.low_stock_threshold < previous:
        transaction.on_commit(lambda: notify_staff(
            "inventory.manage", "Low stock", f"{inv.label} ({inv.sku}) has only {inv.quantity} left.", link=link,
            category="stock"))
