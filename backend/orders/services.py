import json
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from cart.models import Cart
from cart.serializers import _validate_customization_structure
from customizations.models import Customization
from customizations.validators import validate_configuration
from products.models import Product, ProductVariant, StockMovement

from .models import Order, OrderItem, OrderStatusHistory


ALLOWED_STATUS_TRANSITIONS = {
    Order.Status.PENDING: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.PREPARING, Order.Status.CANCELLED},
    Order.Status.PREPARING: {Order.Status.SHIPPED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELLED: set(),
}


def _copy_json(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def customization_snapshot(customization):
    return {
        "version": 1,
        "customizationId": str(customization.id),
        "configuration": _copy_json(customization.configuration),
        "previewFront": customization.preview_front.name,
        "previewBack": customization.preview_back.name,
        "assets": [
            {
                "id": str(asset.id),
                "file": asset.file.name,
                "originalName": asset.original_name,
                "mimeType": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "fileSize": asset.file_size,
            }
            for asset in customization.assets.all()
        ],
    }


@transaction.atomic
def create_order_from_cart(*, user, checkout_data):
    idempotency_key = checkout_data["idempotency_key"]
    existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    cart = Cart.objects.select_for_update().filter(user=user).first()
    if not cart:
        raise serializers.ValidationError({"cart": "Tu carrito está vacío."})

    # A concurrent duplicate waits for the cart lock; re-check its token after it wakes.
    existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    items = list(
        cart.items.select_related("product", "variant", "customization")
        .prefetch_related("customization__assets")
        .order_by("id")
    )
    if not items:
        raise serializers.ValidationError({"cart": "Tu carrito está vacío."})

    locked_products = {
        product.id: product
        for product in Product.objects.select_for_update()
        .filter(id__in=sorted({item.product_id for item in items}))
        .order_by("id")
    }
    if len(locked_products) != len({item.product_id for item in items}):
        raise serializers.ValidationError({"cart": "Un producto del carrito ya no existe."})

    requested_by_variant = defaultdict(int)
    for item in items:
        if item.quantity < 1:
            raise serializers.ValidationError({"cart": "El carrito contiene una cantidad inválida."})
        product = locked_products[item.product_id]
        if not product.active:
            raise serializers.ValidationError({"cart": f"{product.name} ya no está disponible."})
        if item.variant_id:
            requested_by_variant[item.variant_id] += item.quantity
        elif item.product.variants.exists():
            raise serializers.ValidationError({"cart": f"Seleccioná una variante para {item.product.name}."})

    locked_variants = {
        variant.id: variant
        for variant in ProductVariant.objects.select_for_update()
        .select_related("product")
        .filter(id__in=sorted(requested_by_variant))
        .order_by("id")
    }
    if len(locked_variants) != len(requested_by_variant):
        raise serializers.ValidationError({"cart": "Una variante del carrito ya no existe."})

    for variant_id, requested in requested_by_variant.items():
        variant = locked_variants[variant_id]
        if not variant.active:
            raise serializers.ValidationError({"cart": f"La variante {variant.size}/{variant.color} ya no está activa."})
        related_product_ids = {item.product_id for item in items if item.variant_id == variant_id}
        if related_product_ids != {variant.product_id}:
            raise serializers.ValidationError({"cart": "Una variante no pertenece al producto indicado."})

    subtotal = sum((locked_products[item.product_id].price * item.quantity for item in items), Decimal("0.00"))
    shipping_cost = Decimal("0.00")
    order = Order.objects.create(
        user=user,
        idempotency_key=idempotency_key,
        contact_first_name=checkout_data["first_name"],
        contact_last_name=checkout_data["last_name"],
        contact_email=checkout_data["email"],
        shipping_phone=checkout_data["phone"],
        shipping_address=checkout_data["address"],
        shipping_city=checkout_data["city"],
        shipping_department=checkout_data["department"],
        shipping_reference=checkout_data.get("reference", ""),
        delivery_method=Order.DeliveryMethod.DELIVERY,
        payment_status=Order.PaymentStatus.PENDING,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=subtotal + shipping_cost,
    )

    order_items = []
    customizations_to_freeze = []
    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id)
        customization = item.customization
        snapshot = None
        if customization:
            if customization.user_id != user.id:
                raise serializers.ValidationError({"cart": "Una personalización no pertenece a tu cuenta."})
            if customization.is_frozen:
                raise serializers.ValidationError({"cart": "Una personalización ya fue utilizada en otro pedido."})
            if customization.product_id != item.product_id or customization.variant_id != item.variant_id:
                raise serializers.ValidationError({"cart": "Una personalización no coincide con su producto o variante."})
            validate_configuration(
                customization.configuration,
                variant,
                customization.assets.values_list("id", flat=True),
            )
            snapshot = customization_snapshot(customization)
            customizations_to_freeze.append(customization)
        elif item.customization_data is not None:
            _validate_customization_structure(item.customization_data)
            if item.customization_data["garment"] != product.garment_type:
                raise serializers.ValidationError({"cart": "La prenda personalizada no coincide con el producto real."})
            snapshot = {
                "version": 1,
                "legacy": True,
                "configuration": _copy_json(item.customization_data),
                "previewFront": item.preview_front.name if item.preview_front else "",
                "previewBack": item.preview_back.name if item.preview_back else "",
                "assets": [],
            }

        order_items.append(
            OrderItem(
                order=order,
                product=product,
                variant=variant,
                customization=customization,
                product_name=product.name,
                quantity=item.quantity,
                allocated_quantity=item.quantity if variant is None else 0,
                unit_price=product.price,
                subtotal=product.price * item.quantity,
                size=variant.size if variant else "",
                color=variant.color if variant else "",
                customization_snapshot=snapshot,
            )
        )

    OrderItem.objects.bulk_create(order_items)
    for variant in locked_variants.values():
        allocate_variant_stock(variant=variant, performed_by=user)
    for customization in customizations_to_freeze:
        customization.state = Customization.State.ORDERED
        customization.frozen_at = timezone.now()
        customization.save(update_fields=["state", "frozen_at", "updated_at"])
    cart.items.all().delete()
    return order, True


@transaction.atomic
def transition_order_status(*, order, new_status, changed_by):
    order = Order.objects.select_for_update(no_key=True).get(pk=order.pk)
    if order.is_archived:
        raise serializers.ValidationError({"status": "Restaurá el pedido antes de cambiar su estado."})
    if new_status not in ALLOWED_STATUS_TRANSITIONS[order.status]:
        raise serializers.ValidationError(
            {"status": f"No se puede cambiar de {order.status} a {new_status}."}
        )

    if new_status in {Order.Status.PREPARING, Order.Status.SHIPPED} and order.availability == "AWAITING_STOCK":
        raise serializers.ValidationError({"status": "Esperando reposicion de stock."})

    old_status = order.status
    if new_status == Order.Status.CANCELLED and order.stock_released_at is None:
        quantities = defaultdict(int)
        for item in order.items.exclude(variant_id=None):
            quantities[item.variant_id] = 0
        variants = {
            variant.id: variant
            for variant in ProductVariant.objects.select_for_update()
            .filter(id__in=sorted(quantities))
            .order_by("id")
        }
        for item in order.items.exclude(variant_id=None):
            quantities[item.variant_id] += item.allocated_quantity
        for variant_id, quantity in quantities.items():
            if not quantity:
                continue
            variant = variants[variant_id]
            previous_stock = variant.stock
            variant.stock += quantity
            variant.save(update_fields=["stock"])
            StockMovement.objects.create(
                variant=variant,
                movement_type=StockMovement.Type.CANCELLATION,
                quantity=quantity,
                previous_stock=previous_stock,
                new_stock=variant.stock,
                order=order,
                reason=f"Cancelación de {order.order_number}",
                performed_by=changed_by,
            )
        order.stock_released_at = timezone.now()

    order.status = new_status
    update_fields = ["status", "updated_at"]
    if order.stock_released_at:
        update_fields.append("stock_released_at")
    order.save(update_fields=update_fields)
    OrderStatusHistory.objects.create(
        order=order,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    )
    return order


@transaction.atomic
def allocate_variant_stock(*, variant, performed_by):
    """Allocate physical units FIFO; never change payment or production status.

    Lock the variant before reading pending items. Cancellation also reads allocated
    quantities after taking this lock, so it restores exactly what was consumed.
    """
    from django.db.models import F
    variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    if not variant.active or not variant.product.active or not variant.stock:
        return 0
    items = OrderItem.objects.select_for_update(of=("self",)).filter(
        variant=variant, allocated_quantity__lt=F("quantity"),
        order__status__in=[Order.Status.PENDING, Order.Status.CONFIRMED],
    ).select_related("order").order_by("order__created_at", "order_id", "id")
    allocated = 0
    for item in items:
        amount = min(item.shortage_quantity, variant.stock)
        if not amount:
            break
        previous = variant.stock
        variant.stock -= amount
        variant.save(update_fields=["stock"])
        item.allocated_quantity += amount
        item.save(update_fields=["allocated_quantity"])
        StockMovement.objects.create(
            variant=variant, order=item.order, movement_type=StockMovement.Type.ORDER,
            quantity=amount, previous_stock=previous, new_stock=variant.stock,
            reason=f"Asignacion al pedido {item.order.order_number}", performed_by=performed_by,
        )
        allocated += amount
    return allocated
