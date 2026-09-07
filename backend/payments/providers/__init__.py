from django.conf import settings
from rest_framework import serializers

from .mock import MockPaymentProvider


def get_payment_provider(provider_name):
    if provider_name == MockPaymentProvider.name and settings.DEBUG:
        return MockPaymentProvider()
    raise serializers.ValidationError({"provider": "Proveedor de pago no disponible."})
