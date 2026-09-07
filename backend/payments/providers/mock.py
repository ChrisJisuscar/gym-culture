import hashlib
import hmac
import json
import uuid

from django.conf import settings
from rest_framework import serializers

from .base import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    name = "mock"

    def create_payment(self, payment):
        return {
            "external_id": f"mock_{uuid.uuid4().hex}",
            "metadata": {"environment": "development"},
        }

    def parse_webhook(self, request):
        secret = settings.PAYMENT_WEBHOOK_SECRET
        signature = request.headers.get("X-Payment-Signature", "")
        expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(signature, expected):
            raise serializers.ValidationError({"detail": "Firma de webhook inválida."})
        try:
            payload = json.loads(request.body)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"detail": "Payload inválido."}) from exc
        return payload

    @staticmethod
    def build_event(payment, outcome):
        status_map = {
            "approved": "PAID",
            "rejected": "FAILED",
            "pending": "PENDING",
        }
        if outcome not in status_map:
            raise serializers.ValidationError({"outcome": "Resultado mock inválido."})
        return {
            "event_id": f"mock_event_{uuid.uuid4().hex}",
            "event_type": f"payment.{status_map[outcome].lower()}",
            "external_id": payment.external_id,
            "status": status_map[outcome],
            "amount": str(payment.amount),
            "currency": payment.currency,
            "payment_method": "mock",
        }
