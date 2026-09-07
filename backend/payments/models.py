import uuid

from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PROCESSING = "PROCESSING", "Procesando"
        PAID = "PAID", "Pagado"
        FAILED = "FAILED", "Fallido"
        CANCELLED = "CANCELLED", "Cancelado"
        REFUNDED = "REFUNDED", "Reembolsado"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Reembolso parcial"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="payments"
    )
    provider = models.CharField(max_length=50)
    external_id = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING
    )
    payment_method = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "external_id"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.provider} - {self.status}"


class PaymentEvent(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="events"
    )
    provider = models.CharField(max_length=50)
    provider_event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    processed = models.BooleanField(default=False)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                name="unique_payment_event_per_provider",
            )
        ]

    def __str__(self):
        return f"{self.provider_event_id} - {self.event_type}"
