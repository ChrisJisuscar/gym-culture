from django.db import migrations

from products.services import normalize_color, normalize_size


def normalize_lab_catalog(apps, schema_editor):
    """Corrige de forma definitiva los datos que alimentan la selección del Custom Lab.

    - Normaliza nombres de color y talla (p. ej. "GRIS" pasa a "Gris") para que la
      paleta central del frontend pueda resolver label/hex en vez de crear valores
      duplicados accidentales ("negro"/"Negro"/"BLACK").
    - Mantiene UN producto activo por tipo de prenda (tshirt/oversized/hoodie),
      conservando el de menor id: desactiva los duplicados activos.
    - Garantiza la combinación comercial exigida: Remera Oversize Blanco/XL (stock 0)
      existe y es seleccionable, aunque el stock sea cero.
    """
    db = schema_editor.connection.alias
    Product = apps.get_model("products", "Product")
    Variant = apps.get_model("products", "ProductVariant")

    for variant in Variant.objects.using(db).iterator():
        color = normalize_color(variant.color)
        size = normalize_size(variant.size)
        if color != variant.color or size != variant.size:
            variant.color = color
            variant.size = size
            variant.save(using=db, update_fields=["color", "size"])

    for garment_type in ("tshirt", "oversized", "hoodie"):
        products = list(Product.objects.using(db).filter(garment_type=garment_type).order_by("id"))
        if not products:
            continue
        for extra in products[1:]:
            if extra.active:
                extra.active = False
                extra.save(using=db, update_fields=["active"])

    oversized = (
        Product.objects.using(db).filter(garment_type="oversized", active=True).order_by("id").first()
    )
    if oversized and not Variant.objects.using(db).filter(
        product=oversized, color__iexact="Blanco", size__iexact="XL"
    ).exists():
        Variant.objects.using(db).create(product=oversized, color="Blanco", size="XL", stock=0)


class Migration(migrations.Migration):
    dependencies = [("products", "0012_normalize_categories")]
    operations = [migrations.RunPython(normalize_lab_catalog, migrations.RunPython.noop)]