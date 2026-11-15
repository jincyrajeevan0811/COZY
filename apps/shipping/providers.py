"""
Courier integrations are kept modular. Each ShippingProvider row points to a class
implementing this interface. ManualProvider is used until a courier API (Shiprocket,
Delhivery, etc.) is integrated; add a new subclass and reference it from the dashboard.
"""
from importlib import import_module


class BaseProvider:
    def __init__(self, provider):
        self.provider = provider

    def create_shipment(self, shipment):
        """Book a pickup with the courier. Return the tracking number (or '' when manual)."""
        raise NotImplementedError

    def track(self, shipment):
        """Return a status string from Shipment.STATUS_CHOICES, or None if unknown."""
        raise NotImplementedError


class ManualProvider(BaseProvider):
    """Staff enter tracking numbers and statuses by hand in the dashboard."""

    def create_shipment(self, shipment):
        return shipment.tracking_number

    def track(self, shipment):
        return shipment.status


def get_provider_backend(provider):
    path = provider.integration_class or "apps.shipping.providers.ManualProvider"
    module_path, _, class_name = path.rpartition(".")
    if not module_path.startswith("apps.shipping."):
        raise ValueError("Courier integrations must live in apps.shipping.")
    cls = getattr(import_module(module_path), class_name)
    return cls(provider)
