import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def generate_order_number():
    return f"GC-{uuid.uuid4().hex[:10].upper()}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PREPARING = "PREPARING", "Preparing"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PAID = "PAID", "Pagado"
        FAILED = "FAILED", "Fallido"
        REFUNDED = "REFUNDED", "Reembolsado"

    class DeliveryMethod(models.TextChoices):
        DELIVERY = "DELIVERY", "Entrega"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    order_number = models.CharField(max_length=20, unique=True, default=generate_order_number, editable=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    delivery_method = models.CharField(max_length=16, choices=DeliveryMethod.choices, default=DeliveryMethod.DELIVERY)
    contact_first_name = models.CharField(max_length=100, default="")
    contact_last_name = models.CharField(max_length=100, default="")
    contact_email = models.EmailField(default="")
    shipping_phone = models.CharField(max_length=30, default="")
    shipping_address = models.CharField(max_length=255, default="")
    shipping_city = models.CharField(max_length=100, default="")
    shipping_department = models.CharField(max_length=100, default="")
    shipping_reference = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    idempotency_key = models.UUIDField(null=True, blank=True)
    stock_released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="unique_order_idempotency_per_user")
        ]

    def __str__(self):
        return f"{self.order_number} - {self.user}"

    def recalculate_total(self):
        total = sum((item.subtotal for item in self.items.all()), Decimal("0.00"))
        self.subtotal = total
        self.total = total + self.shipping_cost
        self.save(update_fields=["subtotal", "total", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="order_items"
    )
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
    )
    customization = models.ForeignKey(
        "customizations.Customization",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=150, default="")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50)
    customization_snapshot = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    old_status = models.CharField(max_length=20, choices=Order.Status.choices)
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="order_status_changes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} -> {self.new_status}"
