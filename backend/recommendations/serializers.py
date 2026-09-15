import json
import math

from rest_framework import serializers

from .models import Culture, DesignRecommendation
from customizations.validators import validate_configuration, validate_uploaded_image
from customizations.constants import MAX_ASSETS_PER_CUSTOMIZATION
from .state import save_recommendation_state


class CultureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Culture
        fields = ["id", "slug", "name", "tagline", "description", "active", "sort_order"]


class CultureWriteSerializer(serializers.ModelSerializer):
    def validate_slug(self, value):
        slug = value.strip().lower()
        if not slug or not all(character.isalnum() or character in "-_" for character in slug):
            raise serializers.ValidationError("Usá letras, números, guiones o guiones bajos.")
        return slug

    class Meta:
        model = Culture
        fields = ["slug", "name", "tagline", "description", "image", "active", "sort_order"]


class DesignRecommendationSerializer(serializers.ModelSerializer):
    culture_slug = serializers.CharField(source="culture.slug", read_only=True)
    culture_name = serializers.CharField(source="culture.name", read_only=True)
    garment_label = serializers.SerializerMethodField()
    preview_image_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField(method_name='get_preview_image_url')
    design_asset_url = serializers.SerializerMethodField()
    base_color_hex = serializers.SerializerMethodField()

    class Meta:
        model = DesignRecommendation
        fields = [
            "id",
            "name",
            "culture",
            "culture_slug",
            "culture_name",
            "garment_type",
            "garment_label",
            "base_color", "base_color_hex",
            "preview_image_url",
            "preview_url",
            "design_asset_url",
            "active",
            "featured",
            "sort_order",
            "default_position",
            "default_scale",
            "default_rotation",
            "customization_state", "created_at", "updated_at",
        ]

    def _url(self, request, field):
        if not request or not field or not field.name:
            return None
        return request.build_absolute_uri(field.url)

    def get_garment_label(self, obj):
        return dict(DesignRecommendation._meta.get_field("garment_type").choices).get(obj.garment_type, obj.garment_type)

    def get_base_color_hex(self, obj):
        return obj.BASE_COLORS[obj.base_color]

    def get_preview_image_url(self, obj):
        return self._url(self.context.get("request"), obj.preview_image)

    def get_design_asset_url(self, obj):
        return self._url(self.context.get("request"), obj.design_asset)


class DesignRecommendationWriteSerializer(serializers.ModelSerializer):
    sort_order = serializers.IntegerField(read_only=True)
    preview_image = serializers.ImageField(required=False)
    design_asset = serializers.ImageField(required=False)

    class Meta:
        model = DesignRecommendation
        fields = [
            "name",
            "culture",
            "garment_type",
            "base_color",
            "preview_image",
            "design_asset",
            "active",
            "featured",
            "sort_order",
            "default_position",
            "default_scale",
            "default_rotation",
            "customization_state",
        ]

    def validate_default_position(self, value):
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("La posición por defecto debe ser un objeto con x, y y z numéricas.") from exc
            value = parsed
        if value == {}:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("La posición por defecto debe ser un objeto con x, y y z numéricas.")
        for axis in ("x", "y", "z"):
            component = value.get(axis)
            if not isinstance(component, (int, float)) or isinstance(component, bool) or not math.isfinite(component) or abs(component) > 1:
                raise serializers.ValidationError("La posición por defecto debe contener x, y y z numéricas.")
        return value

    def validate(self, attrs):
        configuration = attrs.get('customization_state')
        has_configuration = bool(configuration or (self.instance and self.instance.customization_state))
        if configuration is not None:
            available = self.instance.assets.values_list('id', flat=True) if self.instance else []
            validate_configuration(configuration, available_asset_ids=available, allow_asset_keys=True)
            if attrs.get('garment_type', configuration['garment']['type']) != configuration['garment']['type']:
                raise serializers.ValidationError({'garment_type': 'La prenda debe coincidir con el estado del editor.'})
            if 'preview_image' not in attrs:
                raise serializers.ValidationError({'preview_image': 'Guardá la vista previa generada por el editor.'})
            uploads = {key.removeprefix('asset_'): upload for key, upload in self.context['request'].FILES.items() if key.startswith('asset_')}
            referenced = {str(design[key]) for design in configuration['designs'] if design['type'] == 'image' for key in ('assetKey', 'originalAssetKey') if design.get(key)}
            if len(uploads) > MAX_ASSETS_PER_CUSTOMIZATION or set(uploads) != referenced:
                raise serializers.ValidationError({'assets': 'Los archivos deben coincidir con los assets del estado.'})
            for key, upload in uploads.items():
                validate_uploaded_image(upload, key)
        for field in ("preview_image", "design_asset"):
            if field == 'design_asset' and has_configuration:
                continue
            upload = attrs.get(field)
            existing = getattr(self.instance, field, None) if self.instance else None
            if not upload and not existing:
                raise serializers.ValidationError({field: "Subí una imagen para esta recomendación."})
            if upload:
                if upload.size > 10 * 1024 * 1024 or upload.image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise serializers.ValidationError({field: "Usá PNG, JPG o WebP de hasta 10 MB."})
                width, height = upload.image.size
                if min(width, height) < 64 or max(width, height) > 8192:
                    raise serializers.ValidationError({field: "Cada lado debe medir entre 64 y 8192 px."})
        for field in ("default_scale", "default_rotation"):
            if field in attrs and not math.isfinite(attrs[field]):
                raise serializers.ValidationError({field: "Ingresá un número finito."})
        return attrs

    def create(self, validated_data):
        if 'customization_state' in validated_data:
            return save_recommendation_state(None, validated_data, self.context['request'].FILES)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'customization_state' in validated_data:
            return save_recommendation_state(instance, validated_data, self.context['request'].FILES)
        if instance.customization_state and 'garment_type' in validated_data and validated_data['garment_type'] != instance.garment_type:
            raise serializers.ValidationError({'garment_type': 'Cambiá la prenda desde el Custom Lab.'})
        return super().update(instance, validated_data)
