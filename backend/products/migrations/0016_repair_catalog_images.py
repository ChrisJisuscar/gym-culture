from pathlib import Path
from django.core.files.base import ContentFile
from django.db import migrations
from PIL import Image, UnidentifiedImageError


def repair_images_and_demo_labels(apps, schema_editor):
    db = schema_editor.connection.alias
    ProductImage = apps.get_model("products", "ProductImage")
    OrderItem = apps.get_model("orders", "OrderItem")
    for record in ProductImage.objects.using(db).select_related("product"):
        try:
            with record.image.open("rb") as source:
                Image.open(source).verify()
        except (OSError, ValueError, UnidentifiedImageError):
            kind = record.product.garment_type
            path = Path(__file__).resolve().parent.parent / "assets" / f"{kind}.webp"
            if not path.exists():
                continue
            storage = record.image.storage
            filename = f"products/{kind}-catalog.webp"
            if not storage.exists(filename):
                filename = storage.save(filename, ContentFile(path.read_bytes()))
            record.image = filename
            record.save(using=db, update_fields=["image"])
    known_demo_names = {"remera gym culture test", "remera test", "remera test 2"}
    for item in OrderItem.objects.using(db).filter(product_name__icontains="test").select_related("product"):
        if item.product_name.strip().lower() in known_demo_names:
            item.product_name = item.product.name
            item.save(using=db, update_fields=["product_name"])


class Migration(migrations.Migration):
    dependencies = [("products", "0015_category_unique_category_name_ci")]
    operations = [migrations.RunPython(repair_images_and_demo_labels, migrations.RunPython.noop)]
