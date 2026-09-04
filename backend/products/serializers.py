from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant, StockMovement


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "active"]


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "stock", "active"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_main"]


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "price",
            "category",
            "active",
            "created_at",
            "updated_at",
            "variants",
            "images",
        ]


class AdminProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    main_image = serializers.SerializerMethodField()
    variant_count = serializers.IntegerField(read_only=True)
    total_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "price", "category", "active",
            "main_image", "variant_count", "total_stock", "variants", "images",
            "created_at", "updated_at",
        ]

    def get_main_image(self, obj):
        image = next((item for item in obj.images.all() if item.is_main), None)
        image = image or next(iter(obj.images.all()), None)
        if not image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(image.image.url) if request else image.image.url


class AdminProductWriteSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    variants = serializers.ListField(child=serializers.DictField(), required=False)

    class Meta:
        model = Product
        fields = ["name", "description", "price", "category", "active", "variants"]

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value

    def validate_variants(self, variants):
        if len(variants) > 100:
            raise serializers.ValidationError("Se permiten como máximo 100 variantes.")
        normalized = []
        seen = set()
        for variant in variants:
            try:
                variant_id = int(variant["id"]) if variant.get("id") not in (None, "") else None
                size = str(variant["size"]).strip()
                color = str(variant["color"]).strip()
                stock = int(variant.get("stock", 0))
            except (KeyError, TypeError, ValueError) as exc:
                raise serializers.ValidationError("Cada variante necesita talla, color y stock válidos.") from exc
            if not size or len(size) > 10 or not color or len(color) > 50 or stock < 0:
                raise serializers.ValidationError("Los datos de una variante no son válidos.")
            key = (size.lower(), color.lower())
            if key in seen:
                raise serializers.ValidationError("No se puede repetir la misma talla y color.")
            seen.add(key)
            normalized.append({"id": variant_id, "size": size, "color": color, "stock": stock, "active": bool(variant.get("active", True))})
        return normalized

    def create(self, validated_data):
        variants = validated_data.pop("variants", [])
        product = Product.objects.create(**validated_data)
        user = self.context["request"].user
        for data in variants:
            data.pop("id", None)
            variant = ProductVariant.objects.create(product=product, **data)
            if variant.stock:
                StockMovement.objects.create(
                    variant=variant, movement_type=StockMovement.Type.SET,
                    quantity=variant.stock, previous_stock=0, new_stock=variant.stock,
                    reason="Stock inicial del producto", performed_by=user,
                )
        return product

    def update(self, instance, validated_data):
        variants = validated_data.pop("variants", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if variants is not None:
            from .services import adjust_stock

            user = self.context["request"].user
            existing = {variant.id: variant for variant in instance.variants.all()}
            supplied_ids = {variant["id"] for variant in variants if variant["id"] is not None}
            if not supplied_ids.issubset(existing):
                raise serializers.ValidationError({"variants": "Una variante no pertenece a este producto."})
            for data in variants:
                variant_id = data.pop("id")
                if variant_id is None:
                    variant = ProductVariant.objects.create(product=instance, **data)
                    if variant.stock:
                        StockMovement.objects.create(
                            variant=variant, movement_type=StockMovement.Type.SET,
                            quantity=variant.stock, previous_stock=0, new_stock=variant.stock,
                            reason="Stock inicial de variante", performed_by=user,
                        )
                else:
                    variant = existing[variant_id]
                    requested_stock = data.pop("stock")
                    for field, value in data.items():
                        setattr(variant, field, value)
                    variant.save()
                    if requested_stock != variant.stock:
                        adjust_stock(
                            variant=variant, movement_type=StockMovement.Type.SET,
                            quantity=requested_stock, reason="Ajuste desde ficha de producto",
                            performed_by=user,
                        )
        return instance


class StockVariantSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ["id", "product", "product_name", "color", "size", "stock", "active", "stock_status"]

    def get_stock_status(self, obj):
        from .constants import LOW_STOCK_THRESHOLD

        if obj.stock == 0:
            return "OUT"
        if obj.stock <= LOW_STOCK_THRESHOLD:
            return "LOW"
        return "NORMAL"


class StockAdjustmentSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=["RESTOCK", "REMOVE", "SET"])
    quantity = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=255)

    def validate(self, attrs):
        attrs["reason"] = attrs["reason"].strip()
        if not attrs["reason"]:
            raise serializers.ValidationError({"reason": "El motivo es obligatorio."})
        if attrs["movement_type"] != "SET" and attrs["quantity"] == 0:
            raise serializers.ValidationError({"quantity": "La cantidad debe ser mayor que cero."})
        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    size = serializers.CharField(source="variant.size", read_only=True)
    color = serializers.CharField(source="variant.color", read_only=True)
    performed_by = serializers.EmailField(source="performed_by.email", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "variant", "product_name", "size", "color", "movement_type", "quantity", "previous_stock", "new_stock", "reason", "performed_by", "created_at"]
