from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from products.models import Product, ProductVariant


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="cart_items"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="cart_items",
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    customization_data = models.JSONField(null=True, blank=True)
    preview_front = models.ImageField(upload_to="cart-previews/", null=True, blank=True)
    preview_back = models.ImageField(upload_to="cart-previews/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = []

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "La cantidad debe ser mayor que 0."})
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError(
                {"variant": "La variante no pertenece al producto seleccionado."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        variant_text = f" - {self.variant}" if self.variant else ""
        return f"{self.product}{variant_text} x {self.quantity}"
