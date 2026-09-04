import base64
import binascii
import hashlib
import io
import json
import math

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from PIL import Image
from rest_framework import serializers

from products.models import Product, ProductVariant
from .models import Cart, CartItem

MAX_CUSTOMIZATION_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def canonical_customization(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decode_image_data(value, label):
    if not isinstance(value, str) or not value.startswith("data:image/"):
        raise serializers.ValidationError(
            {label: "La imagen debe ser un Data URL válido."}
        )
    try:
        _, encoded = value.split(",", 1)
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise serializers.ValidationError(
            {label: "La imagen está dañada o no es válida."}
        ) from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise serializers.ValidationError(
            {label: "La imagen supera el tamaño máximo permitido."}
        )
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise serializers.ValidationError(
            {label: "El archivo no es una imagen válida."}
        ) from exc
    if (
        image.format not in ALLOWED_IMAGE_FORMATS
        or image.width > 4096
        or image.height > 4096
    ):
        raise serializers.ValidationError(
            {label: "La imagen no tiene un formato o tamaño permitido."}
        )
    digest = hashlib.sha256(raw).hexdigest()
    return raw, f"cart-customizations/{digest}.{ALLOWED_IMAGE_FORMATS[image.format]}"


def _persist_image_data(value, label):
    raw, name = _decode_image_data(value, label)
    if not default_storage.exists(name):
        default_storage.save(name, ContentFile(raw))
    return default_storage.url(name)


def _persist_preview(value, label):
    if not value:
        return None
    raw, name = _decode_image_data(value, label)
    return ContentFile(raw, name=name.rsplit("/", 1)[-1])


def _validate_customization_structure(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("customization_data debe ser un objeto JSON.")
    try:
        if (
            len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
            > MAX_CUSTOMIZATION_BYTES
        ):
            raise serializers.ValidationError(
                "customization_data supera el tamaño máximo permitido."
            )
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError(
            "customization_data contiene valores inválidos."
        ) from exc
    if (
        value.get("version") != 1
        or value.get("garment") not in ("tshirt", "hoodie")
        or value.get("side") not in ("front", "back")
    ):
        raise serializers.ValidationError("La versión, prenda o lado no son válidos.")
    variant = value.get("variant")
    if not isinstance(variant, dict) or not all(
        isinstance(variant.get(key), str) for key in ("color", "size")
    ):
        raise serializers.ValidationError("La variante personalizada no es válida.")
    garments = value.get("garments")
    if not isinstance(garments, dict):
        raise serializers.ValidationError("La estructura de prendas no es válida.")
    for garment_name in ("tshirt", "hoodie"):
        garment = garments.get(garment_name)
        if not isinstance(garment, dict):
            raise serializers.ValidationError("Falta una prenda en customization_data.")
        for side in ("front", "back"):
            side_data = garment.get(side)
            if (
                not isinstance(side_data, dict)
                or not isinstance(side_data.get("elements"), list)
                or len(side_data["elements"]) > 100
            ):
                raise serializers.ValidationError(
                    "Cada lado debe contener una lista válida de elementos."
                )
            for element in side_data["elements"]:
                if not isinstance(element, dict) or element.get("type") not in (
                    "text",
                    "image",
                ):
                    raise serializers.ValidationError(
                        "Cada elemento debe ser texto o imagen."
                    )
                if (
                    not isinstance(element.get("content"), str)
                    or len(element["content"]) > MAX_CUSTOMIZATION_BYTES
                ):
                    raise serializers.ValidationError(
                        "El contenido del elemento no es válido."
                    )
                for key, minimum, maximum in (
                    ("x", 0, 100),
                    ("y", 0, 100),
                    ("width", 1, 100),
                    ("height", 1, 100),
                    ("rotation", -360, 360),
                ):
                    number = element.get(key)
                    if (
                        isinstance(number, bool)
                        or not isinstance(number, (int, float))
                        or not math.isfinite(number)
                        or not minimum <= number <= maximum
                    ):
                        raise serializers.ValidationError(
                            {key: "El valor del elemento no es válido."}
                        )
                if element["type"] == "text" and (
                    not isinstance(element.get("font"), str)
                    or not isinstance(element.get("bold"), bool)
                ):
                    raise serializers.ValidationError(
                        "La configuración del texto no es válida."
                    )
                if (
                    element["type"] == "image"
                    and element["content"].startswith("data:")
                    and not element["content"].startswith("data:image/")
                ):
                    raise serializers.ValidationError(
                        "El formato de imagen no es válido."
                    )
    return value


def _persist_customization_images(value):
    data = json.loads(json.dumps(value, ensure_ascii=False))
    for garment in data["garments"].values():
        for side in garment.values():
            for element in side["elements"]:
                if element["type"] == "image" and element["content"].startswith(
                    "data:"
                ):
                    element["content"] = _persist_image_data(
                        element["content"], "customization_data"
                    )
    return data


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(
        source="product.price", read_only=True, max_digits=12, decimal_places=2
    )
    price = serializers.DecimalField(
        source="product.price", read_only=True, max_digits=12, decimal_places=2
    )
    product_image = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    is_customized = serializers.SerializerMethodField()
    variant_size = serializers.CharField(
        source="variant.size", read_only=True, allow_null=True
    )
    variant_color = serializers.CharField(
        source="variant.color", read_only=True, allow_null=True
    )
    variant_stock = serializers.IntegerField(
        source="variant.stock", read_only=True, allow_null=True
    )
    customization_detail = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_price",
            "price",
            "subtotal",
            "product_image",
            "variant",
            "variant_size",
            "variant_color",
            "variant_stock",
            "quantity",
            "customization_data",
            "customization",
            "customization_detail",
            "preview_front",
            "preview_back",
            "is_customized",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"customization": {"read_only": True}}

    def get_product_image(self, obj):
        image = (
            obj.product.images.filter(is_main=True).first()
            or obj.product.images.first()
        )
        if not image or not image.image:
            return None
        request = self.context.get("request")
        url = image.image.url
        return request.build_absolute_uri(url) if request else url

    def get_subtotal(self, obj):
        return obj.product.price * obj.quantity

    def get_is_customized(self, obj):
        return obj.customization_id is not None or obj.customization_data is not None

    def get_customization_detail(self, obj):
        if not obj.customization_id:
            return None
        request = self.context.get("request")
        front = obj.customization.preview_front.url
        back = obj.customization.preview_back.url
        return {
            "id": str(obj.customization_id),
            "preview_front_url": request.build_absolute_uri(front) if request else front,
            "preview_back_url": request.build_absolute_uri(back) if request else back,
        }


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "user",
            "item_count",
            "subtotal",
            "items",
            "created_at",
            "updated_at",
        ]

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_subtotal(self, obj):
        return sum((item.product.price * item.quantity) for item in obj.items.all())


class AddCartItemSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    variant = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    customization_data = serializers.JSONField(required=False, allow_null=True)
    preview_front = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, write_only=True
    )
    preview_back = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, write_only=True
    )

    def validate_product(self, value):
        if not Product.objects.filter(pk=value, active=True).exists():
            raise serializers.ValidationError(
                "El producto no existe o no está disponible."
            )
        return value

    def validate_variant(self, value):
        if value is None:
            return value
        if not ProductVariant.objects.filter(pk=value, active=True).exists():
            raise serializers.ValidationError("La variante seleccionada no existe.")
        return value

    def validate(self, attrs):
        product = Product.objects.get(pk=attrs["product"])
        variant_id = attrs.get("variant")
        if variant_id is not None:
            variant = ProductVariant.objects.get(pk=variant_id)
            if variant.product_id != product.id:
                raise serializers.ValidationError(
                    {"variant": "La variante no pertenece al producto indicado."}
                )
            if attrs["quantity"] > variant.stock:
                raise serializers.ValidationError(
                    {"quantity": f"Stock insuficiente. Disponible: {variant.stock}"}
                )
        elif product.variants.exists():
            raise serializers.ValidationError(
                {
                    "variant": "Selecciona una variante antes de agregar el producto al carrito."
                }
            )
        customization = attrs.get("customization_data")
        if customization is not None:
            _validate_customization_structure(customization)
            if variant_id is None:
                raise serializers.ValidationError(
                    {
                        "customization_data": "La personalización necesita una variante válida."
                    }
                )
            if (
                customization["variant"]["size"] != variant.size
                or customization["variant"]["color"].lower() != variant.color.lower()
            ):
                raise serializers.ValidationError(
                    {
                        "customization_data": "La variante no coincide con el diseño personalizado."
                    }
                )
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=self.context["request"].user)
        cart = Cart.objects.select_for_update().get(pk=cart.pk)
        product = Product.objects.get(pk=self.validated_data["product"])
        variant_id = self.validated_data.get("variant")
        variant = (
            ProductVariant.objects.filter(pk=variant_id).first() if variant_id else None
        )
        customization = self.validated_data.get("customization_data")
        if customization is not None:
            customization = _persist_customization_images(customization)
        front_preview = _persist_preview(
            self.validated_data.get("preview_front"), "preview_front"
        )
        back_preview = _persist_preview(
            self.validated_data.get("preview_back"), "preview_back"
        )
        existing_item = kwargs.get("existing_item")
        if existing_item is not None:
            existing_item.product = product
            existing_item.variant = variant
            existing_item.quantity = self.validated_data["quantity"]
            existing_item.customization_data = customization
            if front_preview is not None:
                existing_item.preview_front.save(
                    front_preview.name, front_preview, save=False
                )
            elif customization is None:
                existing_item.preview_front = None
            if back_preview is not None:
                existing_item.preview_back.save(
                    back_preview.name, back_preview, save=False
                )
            elif customization is None:
                existing_item.preview_back = None
            existing_item.save()
            return existing_item

        candidates = CartItem.objects.filter(
            cart=cart, product=product, variant=variant
        )
        item = None
        if customization is None:
            item = candidates.filter(customization_data__isnull=True).first()
        else:
            target = canonical_customization(customization)
            for candidate in candidates.exclude(customization_data__isnull=True):
                if canonical_customization(candidate.customization_data) == target:
                    item = candidate
                    break
        if item is None:
            item = CartItem(
                cart=cart,
                product=product,
                variant=variant,
                quantity=self.validated_data["quantity"],
                customization_data=customization,
            )
        else:
            item.quantity += self.validated_data["quantity"]
            if variant and item.quantity > variant.stock:
                raise serializers.ValidationError(
                    {"quantity": f"Stock insuficiente. Disponible: {variant.stock}"}
                )
        if front_preview is not None:
            item.preview_front.save(front_preview.name, front_preview, save=False)
        if back_preview is not None:
            item.preview_back.save(back_preview.name, back_preview, save=False)
        item.save()
        return item
