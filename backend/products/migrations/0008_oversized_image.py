from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations


def seed_image(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    ProductImage = apps.get_model("products", "ProductImage")
    db = schema_editor.connection.alias
    product = Product.objects.using(db).filter(name="Remera Oversize", garment_type="oversized").first()
    if not product or ProductImage.objects.using(db).filter(product=product).exists():
        return
    storage = ProductImage._meta.get_field("image").storage
    name = "products/oversized-catalog.webp"
    if not storage.exists(name):
        data = (Path(__file__).resolve().parent.parent / "assets" / "oversized.webp").read_bytes()
        name = storage.save(name, ContentFile(data))
    ProductImage.objects.using(db).create(product=product, image=name, is_main=True)


class Migration(migrations.Migration):
    dependencies = [("products", "0007_oversized_catalog")]
    operations = [migrations.RunPython(seed_image, migrations.RunPython.noop)]
