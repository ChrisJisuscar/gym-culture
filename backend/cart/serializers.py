from django.db import models, transaction
from rest_framework import serializers

from products.models import Product, ProductVariant
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(source="product.price", read_only=True, max_digits=12, decimal_places=2)
    variant_size = serializers.CharField(source="variant.size", read_only=True, allow_null=True)
    variant_color = serializers.CharField(source="variant.color", read_only=True, allow_null=True)
    variant_stock = serializers.IntegerField(source="variant.stock", read_only=True, allow_null=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_price",
            "variant",
            "variant_size",
            "variant_color",
            "variant_stock",
            "quantity",
            "created_at",
            "updated_at",
        ]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "user", "item_count", "subtotal", "items", "created_at", "updated_at"]

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_subtotal(self, obj):
        return sum((item.product.price * item.quantity) for item in obj.items.all())


class AddCartItemSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    variant = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product(self, value):
        if not Product.objects.filter(pk=value, active=True).exists():
            raise serializers.ValidationError("El producto no existe o no está disponible.")
        return value

    def validate_variant(self, value):
        if value is None:
            return value
        if not ProductVariant.objects.filter(pk=value).exists():
            raise serializers.ValidationError("La variante seleccionada no existe.")
        return value

    def validate(self, attrs):
        product = Product.objects.get(pk=attrs["product"])
        variant_id = attrs.get("variant")
        if variant_id is not None:
            variant = ProductVariant.objects.get(pk=variant_id)
            if variant.product_id != product.id:
                raise serializers.ValidationError({"variant": "La variante no pertenece al producto indicado."})
            if attrs["quantity"] > variant.stock:
                raise serializers.ValidationError({"quantity": f"Stock insuficiente. Disponible: {variant.stock}"})
        else:
            if product.variants.exists():
                min_stock = product.variants.aggregate(stock__min=models.Min("stock"))["stock__min"]
                if min_stock is not None and attrs["quantity"] > min_stock:
                    raise serializers.ValidationError({"quantity": "Stock insuficiente para la variante seleccionada."})
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=self.context["request"].user)
        product = Product.objects.get(pk=self.validated_data["product"])
        variant_id = self.validated_data.get("variant")
        variant = ProductVariant.objects.filter(pk=variant_id).first() if variant_id else None

        if variant is not None:
            item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=variant)
            if not created:
                item.quantity += self.validated_data["quantity"]
                if item.quantity > variant.stock:
                    raise serializers.ValidationError({"quantity": f"Stock insuficiente. Disponible: {variant.stock}"})
                item.save(update_fields=["quantity", "updated_at"])
                return item
            item.quantity = self.validated_data["quantity"]
            item.save()
            return item

        item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=None)
        if not created:
            item.quantity += self.validated_data["quantity"]
            item.save(update_fields=["quantity", "updated_at"])
            return item
        item.quantity = self.validated_data["quantity"]
        item.save()
        return item
