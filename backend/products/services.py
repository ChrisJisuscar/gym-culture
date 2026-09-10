from django.db import transaction
from rest_framework import serializers

from .models import ProductVariant, StockMovement


ADMIN_STOCK_MOVEMENT_TYPES = {
    StockMovement.Type.RESTOCK,
    StockMovement.Type.REMOVE,
    StockMovement.Type.SET,
}

SIZE_ALIASES = {
    "XS": "XS", "S": "S", "M": "M", "L": "L", "XL": "XL",
    "2XL": "2XL", "XXL": "2XL", "3XL": "3XL", "XXXL": "3XL", "4XL": "4XL",
}


def garment_color_hex(color):
    from PIL import ImageColor
    known = {"Negro": "#111015", "Blanco": "#ebe9e4", "Gris": "#7a7780", "Azul": "#244a8f", "Rojo": "#9f233d", "Verde": "#276749"}
    canonical = normalize_color(color)
    if canonical in known:
        return known[canonical]
    try:
        return "#%02x%02x%02x" % ImageColor.getrgb(color)
    except (ValueError, TypeError):
        return "#777777"


def normalize_color(value):
    """Normalizá el nombre de un color a la forma de catálogo (p. ej. 'GRIS ' -> 'Gris')."""
    key = " ".join(str(value or "").strip().lower().split())
    aliases = {"black": "Negro", "white": "Blanco", "gray": "Gris", "grey": "Gris", "blue": "Azul", "red": "Rojo", "green": "Verde"}
    return aliases.get(key, key.title()) or "Sin color"


def normalize_size(value):
    """Normalizá una talla respetando la grilla canónica S/M/L/XL/2XL y sus alias."""
    key = str(value or "").strip().upper()
    return SIZE_ALIASES.get(key, key)


@transaction.atomic
def adjust_stock(*, variant, movement_type, quantity, reason, performed_by):
    variant = ProductVariant.objects.select_for_update().select_related("product").get(pk=variant.pk)
    if movement_type not in ADMIN_STOCK_MOVEMENT_TYPES:
        raise serializers.ValidationError({"movement_type": "Tipo de movimiento administrativo inválido."})
    if quantity < 0 or (movement_type != StockMovement.Type.SET and quantity == 0):
        raise serializers.ValidationError({"quantity": "La cantidad no es válida."})

    previous_stock = variant.stock
    if movement_type == StockMovement.Type.RESTOCK:
        new_stock = previous_stock + quantity
    elif movement_type == StockMovement.Type.REMOVE:
        new_stock = previous_stock - quantity
    else:
        new_stock = quantity
    if new_stock < 0:
        raise serializers.ValidationError({"quantity": "El stock no puede quedar negativo."})

    variant.stock = new_stock
    variant.save(update_fields=["stock"])
    movement = StockMovement.objects.create(
        variant=variant,
        movement_type=movement_type,
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        reason=reason,
        performed_by=performed_by,
    )
    if new_stock > previous_stock:
        from orders.services import allocate_variant_stock
        allocate_variant_stock(variant=variant, performed_by=performed_by)
    return movement


def stock_queryset():
    from django.db.models import Count, F, IntegerField, OuterRef, Subquery, Sum
    from django.db.models.functions import Coalesce
    from orders.models import Order, OrderItem
    pending = OrderItem.objects.filter(
        variant=OuterRef("pk"), allocated_quantity__lt=F("quantity"),
        order__status__in=[Order.Status.PENDING, Order.Status.CONFIRMED],
    ).order_by().values("variant")
    demand = pending.annotate(total=Sum(F("quantity") - F("allocated_quantity"))).values("total")
    count = pending.annotate(total=Count("order", distinct=True)).values("total")
    return ProductVariant.objects.select_related("product").annotate(
        pending_demand=Coalesce(Subquery(demand, output_field=IntegerField()), 0),
        pending_orders=Coalesce(Subquery(count, output_field=IntegerField()), 0),
    ).order_by("product__name", "color", "size")


def main_product_image(product, request=None):
    images = list(product.images.all())
    for image in sorted(images, key=lambda item: not item.is_main):
        if image.image and image.image.storage.exists(image.image.name):
            return request.build_absolute_uri(image.image.url) if request else image.image.url
    return None
