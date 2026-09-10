from django.db import migrations


def normalize(apps, schema_editor):
    db = schema_editor.connection.alias
    Product = apps.get_model("products", "Product")
    Variant = apps.get_model("products", "ProductVariant")
    Category = apps.get_model("products", "Category")
    category, _ = Category.objects.using(db).get_or_create(name="Remeras")
    names = {"tshirt": "Remera Clásica", "oversized": "Remera Oversize", "hoodie": "Hoodie"}
    for kind, name in names.items():
        products = list(Product.objects.using(db).filter(garment_type=kind).order_by("id"))
        candidates = [p for p in products if "test" in p.name.lower() or p.name in (name, "Remera Oversize")]
        if not candidates:
            candidates = [Product.objects.using(db).create(name=name, description="Prenda personalizable", price=0, category=category, garment_type=kind)]
        for index, product in enumerate(candidates):
            product.name = name
            # Preserve references, differing prices and physical inventory of old test records.
            product.active = index == 0
            product.save(using=db, update_fields=["name", "active"])
        product = candidates[0]
        for size in ("S", "M", "L", "XL", "2XL"):
            if not Variant.objects.using(db).filter(product=product, color__iexact="Negro", size=size).exists():
                Variant.objects.using(db).create(product=product, color="Negro", size=size, stock=0)


class Migration(migrations.Migration):
    dependencies = [("products", "0009_stockmovement_order_alter_product_garment_type")]
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
