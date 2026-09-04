import json
from pathlib import Path

from django.core.files.storage import default_storage
from django.db import transaction
from rest_framework import serializers

from cart.models import Cart, CartItem
from products.models import Product, ProductVariant

from .constants import MAX_ASSETS_PER_CUSTOMIZATION
from .models import Customization, CustomizationAsset
from .validators import validate_configuration, validate_uploaded_image


class CustomizationAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = CustomizationAsset
        fields = ["id", "url", "original_name", "mime_type", "width", "height", "file_size"]

    def get_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url


class CustomizationSerializer(serializers.ModelSerializer):
    assets = CustomizationAssetSerializer(many=True, read_only=True)
    preview_front_url = serializers.SerializerMethodField()
    preview_back_url = serializers.SerializerMethodField()

    class Meta:
        model = Customization
        fields = ["id", "product", "variant", "state", "frozen_at", "configuration", "preview_front_url", "preview_back_url", "assets", "created_at", "updated_at"]

    def _url(self, field):
        request = self.context.get("request")
        return request.build_absolute_uri(field.url) if request else field.url

    def get_preview_front_url(self, obj):
        return self._url(obj.preview_front)

    def get_preview_back_url(self, obj):
        return self._url(obj.preview_back)


class CustomizationWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(active=True))
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.filter(active=True))
    configuration = serializers.JSONField()
    preview_front = serializers.ImageField(required=True)
    preview_back = serializers.ImageField(required=True)
    add_to_cart = serializers.BooleanField(default=False)

    def to_internal_value(self, data):
        # QueryDict.copy() tries to deep-copy temporary upload streams.
        prepared = {
            key: data.get(key)
            for key in ("product", "variant", "preview_front", "preview_back", "add_to_cart")
            if key in data
        }
        configuration = data.get("configuration")
        if isinstance(configuration, str):
            try:
                configuration = json.loads(configuration)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({"configuration": "JSON inválido."}) from exc
        if configuration is not None:
            prepared["configuration"] = configuration
        return super().to_internal_value(prepared)

    def validate(self, attrs):
        if self.instance and self.instance.is_frozen:
            raise serializers.ValidationError({"detail": "Una personalización comprada ya no puede editarse."})
        product, variant = attrs["product"], attrs["variant"]
        if variant.product_id != product.id:
            raise serializers.ValidationError({"variant": "La variante no pertenece al producto."})
        if variant.stock < 1:
            raise serializers.ValidationError({"variant": "La variante no tiene stock."})
        validate_uploaded_image(attrs["preview_front"], "preview_front")
        validate_uploaded_image(attrs["preview_back"], "preview_back")
        instance = self.instance
        existing_ids = instance.assets.values_list("id", flat=True) if instance else []
        validate_configuration(attrs["configuration"], variant, existing_ids, allow_asset_keys=True)
        asset_uploads = [key for key in self.context["request"].FILES if key.startswith("asset_")]
        if len(asset_uploads) > MAX_ASSETS_PER_CUSTOMIZATION:
            raise serializers.ValidationError({"assets": "Se superó el máximo de 20 archivos."})
        referenced_keys = {str(item.get("assetKey")) for item in attrs["configuration"]["designs"] if item.get("type") == "image" and item.get("assetKey")}
        uploaded_keys = {key.removeprefix("asset_") for key in asset_uploads}
        if referenced_keys != uploaded_keys:
            raise serializers.ValidationError({"assets": "Los archivos no coinciden con las referencias de la configuración."})
        for field_name in asset_uploads:
            validate_uploaded_image(self.context["request"].FILES[field_name], field_name)
        return attrs

    def save(self, **kwargs):
        request = self.context["request"]
        data = self.validated_data
        saved_files = []
        old_previews = []
        stale_assets = []
        try:
            with transaction.atomic():
                if self.instance:
                    customization = Customization.objects.select_for_update().get(pk=self.instance.pk, user=request.user)
                    old_previews = [customization.preview_front.name, customization.preview_back.name]
                    customization.product = data["product"]
                    customization.variant = data["variant"]
                    customization.preview_front = data["preview_front"]
                    customization.preview_back = data["preview_back"]
                else:
                    customization = Customization(user=request.user, product=data["product"], variant=data["variant"], configuration={}, preview_front=data["preview_front"], preview_back=data["preview_back"])
                customization.save()
                saved_files.extend([customization.preview_front.name, customization.preview_back.name])

                key_to_asset = {}
                for field_name, upload in request.FILES.items():
                    if not field_name.startswith("asset_"):
                        continue
                    info = validate_uploaded_image(upload, field_name)
                    asset = CustomizationAsset(customization=customization, original_name=Path(upload.name).name[:255], mime_type=upload.content_type, width=info["width"], height=info["height"], file_size=upload.size)
                    asset.file.save(f"upload.{info['extension']}", upload, save=True)
                    saved_files.append(asset.file.name)
                    key_to_asset[field_name.removeprefix("asset_")] = asset

                configuration = json.loads(json.dumps(data["configuration"]))
                for design in configuration["designs"]:
                    key = design.pop("assetKey", None)
                    if key:
                        asset = key_to_asset[key]
                        design["assetId"] = str(asset.id)
                assets_by_id = {str(asset.id): asset for asset in customization.assets.all()}
                for design in configuration["designs"]:
                    if design.get("type") == "image":
                        design["assetUrl"] = assets_by_id[str(design["assetId"])].file.url
                valid_ids = set(customization.assets.values_list("id", flat=True))
                validate_configuration(configuration, data["variant"], valid_ids)
                customization.configuration = configuration
                customization.save(update_fields=["configuration", "updated_at"])

                referenced_ids = {item.get("assetId") for item in configuration["designs"] if item.get("type") == "image"}
                for asset in list(customization.assets.all()):
                    if str(asset.id) not in referenced_ids:
                        stale_assets.append(asset)

                if data.get("add_to_cart"):
                    cart, _ = Cart.objects.get_or_create(user=request.user)
                    cart = Cart.objects.select_for_update().get(pk=cart.pk)
                    CartItem.objects.create(cart=cart, product=data["product"], variant=data["variant"], quantity=1, customization=customization)
                    customization.state = Customization.State.IN_CART
                    customization.save(update_fields=["state", "updated_at"])
            for old_name in old_previews:
                if old_name and old_name not in saved_files:
                    default_storage.delete(old_name)
            for asset in stale_assets:
                asset.delete()
            return customization
        except Exception:
            for name in saved_files:
                default_storage.delete(name)
            raise
