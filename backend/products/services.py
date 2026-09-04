from django.db import transaction
from rest_framework import serializers

from .models import ProductVariant, StockMovement


ADMIN_STOCK_MOVEMENT_TYPES = {
    StockMovement.Type.RESTOCK,
    StockMovement.Type.REMOVE,
    StockMovement.Type.SET,
}


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
    return movement
