from django.db import models
from django.db.models.functions import Lower
from django.core.validators import RegexValidator


class Category(models.Model):
    class Meta:
        constraints = [models.UniqueConstraint(Lower("name"), name="unique_category_name_ci")]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    class GarmentType(models.TextChoices):
        HOODIE = "hoodie", "Hoodie"
        TSHIRT = "tshirt", "Remera"
        OVERSIZED = "oversized", "Remera Oversize"

    garment_type = models.CharField(max_length=16, choices=GarmentType.choices, default=GarmentType.TSHIRT)
    name = models.CharField(max_length=150)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50)
    color_hex = models.CharField(max_length=7, blank=True, default="", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Usá un color hexadecimal válido.")])
    stock = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("color"), Lower("size"), "product", name="unique_product_color_size_ci"),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.size} - {self.color}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Imagen de {self.product.name}"


class StockMovement(models.Model):
    class Type(models.TextChoices):
        RESTOCK = "RESTOCK", "Ingreso"
        REMOVE = "REMOVE", "Retiro"
        SET = "SET", "Ajuste"
        ORDER = "ORDER", "Pedido"
        CANCELLATION = "CANCELLATION", "Cancelación"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=16, choices=Type.choices)
    quantity = models.PositiveIntegerField()
    previous_stock = models.PositiveIntegerField()
    new_stock = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    performed_by = models.ForeignKey("users.User", on_delete=models.PROTECT, related_name="stock_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["movement_type", "created_at"])]

    def __str__(self):
        return f"{self.variant} {self.movement_type}: {self.previous_stock} -> {self.new_stock}"
