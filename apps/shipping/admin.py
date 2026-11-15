from django.contrib import admin

from .models import ServiceablePincode, Shipment, ShippingMethod, ShippingProvider

admin.site.register(ShippingMethod)
admin.site.register(ServiceablePincode)
admin.site.register(ShippingProvider)
admin.site.register(Shipment)
