import json
import math
import re

from PIL import Image, UnidentifiedImageError
from products.services import normalize_color, normalize_size
from rest_framework import serializers

from .constants import (
    ALLOWED_FONTS,
    ALLOWED_IMAGE_FORMATS,
    ALLOWED_IMAGE_MIME_TYPES,
    CUSTOMIZATION_SCHEMA_VERSION,
    MAX_ASSETS_PER_CUSTOMIZATION,
    MAX_CUSTOMIZATION_FILE_SIZE,
    MAX_CONFIGURATION_SIZE,
    MAX_DESIGNS_PER_CUSTOMIZATION,
    MAX_IMAGE_DIMENSION,
    MIN_IMAGE_DIMENSION,
)

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
ID_VALUE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def validate_uploaded_image(upload, label="image"):
    if upload.size > MAX_CUSTOMIZATION_FILE_SIZE:
        raise serializers.ValidationError({label: "La imagen supera el límite de 10 MB."})
    if upload.content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise serializers.ValidationError({label: "Solo se permiten imágenes PNG, JPG o WebP."})
    try:
        image = Image.open(upload)
        image.verify()
        upload.seek(0)
        image = Image.open(upload)
        width, height, image_format = image.width, image.height, image.format
        upload.seek(0)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise serializers.ValidationError({label: "El archivo no contiene una imagen válida."}) from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise serializers.ValidationError({label: "El formato real de la imagen no está permitido."})
    if not (MIN_IMAGE_DIMENSION <= min(width, height) and max(width, height) <= MAX_IMAGE_DIMENSION):
        raise serializers.ValidationError({label: "Las dimensiones deben estar entre 64 y 8192 px."})
    expected_mime = "image/jpeg" if image_format == "JPEG" else f"image/{image_format.lower()}"
    if upload.content_type != expected_mime:
        raise serializers.ValidationError({label: "El MIME declarado no coincide con el formato real."})
    return {"width": width, "height": height, "format": image_format, "extension": ALLOWED_IMAGE_FORMATS[image_format]}


def _number(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise serializers.ValidationError({label: "Valor numérico inválido."})


def _vector(value, label):
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise serializers.ValidationError({label: "Debe contener x, y y z."})
    for axis in ("x", "y", "z"):
        _number(value[axis], -1000, 1000, f"{label}.{axis}")


def validate_configuration(value, variant, available_asset_ids=None, allow_asset_keys=False):
    if not isinstance(value, dict) or value.get("version") != CUSTOMIZATION_SCHEMA_VERSION:
        raise serializers.ValidationError({"configuration": "La versión de configuración no es válida."})
    if len(json.dumps(value, separators=(",", ":")).encode("utf-8")) > MAX_CONFIGURATION_SIZE:
        raise serializers.ValidationError({"configuration": "La configuración supera el tamaño permitido."})
    garment = value.get("garment")
    if not isinstance(garment, dict) or garment.get("type") not in ("tshirt", "oversized", "hoodie"):
        raise serializers.ValidationError({"configuration": "La prenda no es válida."})
    if garment["type"] == "hoodie" and garment.get("hoodState", "down") not in ("down", "up"):
        raise serializers.ValidationError({"configuration": "Estado de capucha invalido."})
    if garment["type"] != variant.product.garment_type or garment.get("productId", variant.product_id) != variant.product_id:
        raise serializers.ValidationError({"configuration": "La prenda no coincide con el producto."})
    if garment.get("variantId") != variant.id or normalize_size(garment.get("size")) != normalize_size(variant.size) or normalize_color(garment.get("color", "")) != normalize_color(variant.color):
        raise serializers.ValidationError({"configuration": "La configuración no coincide con la variante."})
    if not HEX_COLOR.fullmatch(str(garment.get("colorHex", ""))):
        raise serializers.ValidationError({"configuration": "El color de la prenda no es válido."})
    designs = value.get("designs")
    if not isinstance(designs, list) or len(designs) > MAX_DESIGNS_PER_CUSTOMIZATION:
        raise serializers.ValidationError({"configuration": "La lista de diseños no es válida."})
    seen = set()
    available_asset_ids = {str(item) for item in (available_asset_ids or [])}
    asset_keys = set()
    for design in designs:
        if not isinstance(design, dict) or design.get("type") not in {"image", "text"}:
            raise serializers.ValidationError({"configuration": "Cada elemento debe ser imagen o texto."})
        if "source" in design or "originalSource" in design or "dataUrl" in design or any(
            isinstance(item, str) and item.strip().lower().startswith("data:")
            for item in design.values()
        ):
            raise serializers.ValidationError({"configuration": "Los datos binarios deben enviarse como archivos."})
        design_id = str(design.get("id", ""))
        if not ID_VALUE.fullmatch(design_id) or design_id in seen:
            raise serializers.ValidationError({"configuration": "Los IDs de diseño deben ser únicos y válidos."})
        seen.add(design_id)
        _vector(design.get("position"), "position")
        _vector(design.get("normal"), "normal")
        for key, minimum, maximum in (("rotation", -180, 180), ("scale", .35, 2.5), ("aspectRatio", .01, 100), ("width", .001, 100), ("height", .001, 100)):
            _number(design.get(key), minimum, maximum, key)
        if design["type"] == "text":
            if not isinstance(design.get("text"), str) or not 1 <= len(design["text"]) <= 50:
                raise serializers.ValidationError({"configuration": "El texto no es válido."})
            if design.get("fontFamily") not in ALLOWED_FONTS or not HEX_COLOR.fullmatch(str(design.get("color", ""))):
                raise serializers.ValidationError({"configuration": "Fuente o color de texto inválido."})
            _number(design.get("fontSize"), 32, 1024, "fontSize")
        else:
            original_id = design.get("originalAssetId")
            original_key = design.get("originalAssetKey")
            if original_id is not None and str(original_id) not in available_asset_ids:
                raise serializers.ValidationError({"configuration": "El original no pertenece a esta personalización."})
            if original_key is not None:
                if not allow_asset_keys or not ID_VALUE.fullmatch(str(original_key)):
                    raise serializers.ValidationError({"configuration": "Referencia al original inválida."})
                asset_keys.add(str(original_key))
            if design.get("backgroundRemoved") and original_id is None and original_key is None:
                raise serializers.ValidationError({"configuration": "La imagen procesada debe conservar su original."})
            asset_id = design.get("assetId")
            asset_key = design.get("assetKey")
            if asset_id is not None and str(asset_id) not in available_asset_ids:
                raise serializers.ValidationError({"configuration": "El asset no pertenece a esta personalización."})
            if asset_id is None and (not allow_asset_keys or not ID_VALUE.fullmatch(str(asset_key or ""))):
                raise serializers.ValidationError({"configuration": "La imagen no referencia un asset válido."})
            if asset_key:
                asset_keys.add(str(asset_key))
    if len(asset_keys) > MAX_ASSETS_PER_CUSTOMIZATION:
        raise serializers.ValidationError({"configuration": "Se superó el máximo de assets."})
    return value
