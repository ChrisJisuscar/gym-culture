from django.db import migrations


def seed_oversized(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Category = apps.get_model("products", "Category")
    Variant = apps.get_model("products", "ProductVariant")
    db = schema_editor.connection.alias
    products = Product.objects.using(db)
    # Reuse an explicitly named existing catalog item without changing price or stock.
    product = products.filter(name__iexact="Remera Oversize").first()
    if product:
        product.garment_type = "oversized"
        product.save(using=db, update_fields=["garment_type"])
    else:
        category, _ = Category.objects.using(db).get_or_create(name="Remeras")
        product = products.create(name="Remera Oversize", description="Remera de corte oversize personalizable.",
                                  price=0, category=category, active=False, garment_type="oversized")
    for size in ("S", "M", "L", "XL", "2XL"):
        Variant.objects.using(db).get_or_create(product=product, color="Negro", size=size, defaults={"stock": 0})


class Migration(migrations.Migration):
    dependencies = [("products", "0006_product_garment_type")]
    operations = [migrations.RunPython(seed_oversized, migrations.RunPython.noop)]
