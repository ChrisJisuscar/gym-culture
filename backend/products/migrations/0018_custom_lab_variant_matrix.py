from django.db import migrations, models
from django.db.models.functions import Lower


LAB_COLORS = {
    "Negro": "#111015",
    "Blanco": "#ebe9e4",
    "Gris": "#7a7780",
    "Azul": "#244a8f",
    "Rojo": "#9f233d",
    "Verde": "#276749",
}
LAB_SIZES = ("S", "M", "L", "XL", "2XL")

COLOR_ALIASES = {
    "black": "Negro", "white": "Blanco", "gray": "Gris", "grey": "Gris",
    "blue": "Azul", "red": "Rojo", "green": "Verde",
}
SIZE_ALIASES = {"XXL": "2XL", "XXXL": "3XL"}


def normalize_value(value, aliases, title=True):
    key = " ".join(str(value or "").strip().lower().split())
    if key in aliases:
        return aliases[key]
    return key.title() if title else key.upper()


def ensure_matrix(apps, schema_editor):
    db = schema_editor.connection.alias
    Product = apps.get_model("products", "Product")
    Variant = apps.get_model("products", "ProductVariant")

    for variant in Variant.objects.using(db).iterator():
        color = normalize_value(variant.color, COLOR_ALIASES)
        size = normalize_value(variant.size, SIZE_ALIASES, title=False)
        color_hex = LAB_COLORS.get(color, variant.color_hex or "")
        if variant.color != color or variant.size != size or variant.color_hex != color_hex:
            variant.color = color
            variant.size = size
            variant.color_hex = color_hex
            variant.save(using=db, update_fields=["color", "size", "color_hex"])

    # Remove duplicate (product, color, size) rows. Legacy catalogs contained
    # redundant variants; keep the preferred one and delete unreferenced twins.
    preferred = {}
    for variant in Variant.objects.using(db).order_by("product_id", "-active", "-stock", "id"):
        key = (variant.product_id, normalize_value(variant.color, COLOR_ALIASES), normalize_value(variant.size, SIZE_ALIASES, title=False))
        if key not in preferred:
            preferred[key] = variant
    redundant = []
    seen = set()
    for variant in Variant.objects.using(db).order_by("product_id", "id"):
        key = (variant.product_id, normalize_value(variant.color, COLOR_ALIASES), normalize_value(variant.size, SIZE_ALIASES, title=False))
        if key in seen:
            redundant.append(variant.id)
        else:
            seen.add(key)
    Variant.objects.using(db).filter(pk__in=redundant).delete()

    for product in Product.objects.using(db).filter(garment_type__in=("tshirt", "oversized", "hoodie"), active=True):
        for color, color_hex in LAB_COLORS.items():
            for size in LAB_SIZES:
                Variant.objects.using(db).get_or_create(
                    product=product, color=color, size=size,
                    defaults={"color_hex": color_hex, "stock": 0, "active": True},
                )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("products", "0017_productvariant_color_hex"),
    ]

    operations = [
        migrations.RunPython(ensure_matrix, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                Lower("color"), Lower("size"), "product",
                name="unique_product_color_size_ci",
            ),
        ),
    ]