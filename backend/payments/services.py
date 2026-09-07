import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from orders.models import Order, OrderStatusHistory

from .models import Payment, PaymentEvent
from .providers import get_payment_provider

logger = logging.getLogger(__name__)

FINAL_SUCCESS_STATUSES = {
    Payment.Status.PAID,
    Payment.Status.REFUNDED,
    Payment.Status.PARTIALLY_REFUNDED,
}


class PaymentService:
    @transaction.atomic
    def create_payment(self, *, order, provider_name):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.Status.CANCELLED:
            raise serializers.ValidationError({"order": "El pedido está cancelado."})
        if order.total <= 0:
            raise serializers.ValidationError({"order": "El total del pedido no es válido."})
        if order.payments.filter(status__in=FINAL_SUCCESS_STATUSES).exists():
            raise serializers.ValidationError({"order": "El pedido ya está pagado."})

        provider = get_payment_provider(provider_name)
        payment = Payment.objects.create(
            order=order,
            provider=provider.name,
            amount=order.total,
            currency=settings.PAYMENT_CURRENCY,
        )
        provider_data = provider.create_payment(payment)
        payment.external_id = provider_data.get("external_id", "")
        payment.metadata = provider_data.get("metadata", {})
        payment.save(update_fields=["external_id", "metadata", "updated_at"])
        return payment

    @transaction.atomic
    def process_event(self, *, provider_name, payload):
        provider_event_id = str(payload.get("event_id", "")).strip()
        external_id = str(payload.get("external_id", "")).strip()
        event_type = str(payload.get("event_type", "")).strip()
        if not provider_event_id or not external_id or not event_type:
            raise serializers.ValidationError({"detail": "Evento de pago incompleto."})

        existing_event = PaymentEvent.objects.select_related("payment").filter(
            provider=provider_name, provider_event_id=provider_event_id
        ).first()
        if existing_event:
            return existing_event.payment, False

        payment = Payment.objects.select_for_update().select_related("order").filter(
            provider=provider_name, external_id=external_id
        ).first()
        if not payment:
            raise serializers.ValidationError({"detail": "Pago no encontrado."})

        try:
            with transaction.atomic():
                event = PaymentEvent.objects.create(
                    payment=payment,
                    provider=provider_name,
                    provider_event_id=provider_event_id,
                    event_type=event_type,
                )
        except IntegrityError:
            duplicate = PaymentEvent.objects.select_related("payment").get(
                provider=provider_name, provider_event_id=provider_event_id
            )
            return duplicate.payment, False
        try:
            amount = Decimal(str(payload.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            amount = None
        if amount != payment.amount:
            event.error = "Monto inválido."
            event.save(update_fields=["error"])
            logger.warning("Payment event rejected: amount mismatch", extra={"payment_id": str(payment.id)})
            raise serializers.ValidationError({"amount": "El monto no coincide con el pago."})
        if str(payload.get("currency", "")).upper() != payment.currency:
            event.error = "Moneda inválida."
            event.save(update_fields=["error"])
            logger.warning("Payment event rejected: currency mismatch", extra={"payment_id": str(payment.id)})
            raise serializers.ValidationError({"currency": "La moneda no coincide con el pago."})

        new_status = str(payload.get("status", "")).upper()
        if new_status not in Payment.Status.values:
            event.error = "Estado inválido."
            event.save(update_fields=["error"])
            raise serializers.ValidationError({"status": "Estado de pago inválido."})

        if payment.status == Payment.Status.PAID and new_status != Payment.Status.PAID:
            event.error = "Transición posterior a pago ignorada."
            event.processed = True
            event.save(update_fields=["error", "processed"])
            return payment, True

        payment.status = new_status
        payment.payment_method = str(payload.get("payment_method", ""))[:50]
        if new_status == Payment.Status.PAID and payment.paid_at is None:
            payment.paid_at = timezone.now()
        payment.save(
            update_fields=["status", "payment_method", "paid_at", "updated_at"]
        )
        self._sync_order(payment)
        event.processed = True
        event.save(update_fields=["processed"])
        return payment, True

    @staticmethod
    def _sync_order(payment):
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        statuses = set(order.payments.values_list("status", flat=True))
        if Payment.Status.PAID in statuses:
            order.payment_status = Order.PaymentStatus.PAID
        elif Payment.Status.PROCESSING in statuses:
            order.payment_status = Order.PaymentStatus.PROCESSING
        else:
            order.payment_status = payment.status
        update_fields = ["payment_status", "updated_at"]
        if payment.status == Payment.Status.PAID and order.status == Order.Status.PENDING:
            old_status = order.status
            order.status = Order.Status.CONFIRMED
            update_fields.append("status")
            order.save(update_fields=update_fields)
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=order.status,
                changed_by=None,
            )
            return
        order.save(update_fields=update_fields)

    def get_status(self, payment):
        return get_payment_provider(payment.provider).get_status(payment)

    def refund(self, payment, amount=None):
        return get_payment_provider(payment.provider).refund(payment, amount)
