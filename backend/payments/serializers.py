from django.conf import settings
from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_simulate = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "provider",
            "external_id",
            "amount",
            "currency",
            "status",
            "status_display",
            "payment_method",
            "created_at",
            "updated_at",
            "paid_at",
            "can_simulate",
        ]
        read_only_fields = fields

    def get_can_simulate(self, obj):
        return settings.DEBUG and obj.provider == "mock"


class CreatePaymentSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=50, required=False)

    def validate_provider(self, value):
        return value.strip().lower()


class MockOutcomeSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["approved", "rejected", "pending"])
