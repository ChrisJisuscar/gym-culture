from pathlib import Path
from django.core.files.base import ContentFile
from django.db import migrations


def normalize_catalog(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("products", "Category")
    Product = apps.get_model("products", "Product")
    Variant = apps.get_model("products", "ProductVariant")
    ProductImage = apps.get_model("products", "ProductImage")
    categories = {}
    for category in Category.objects.using(db).order_by("id"):
        key = category.name.strip().casefold()
        if key in categories:
            Product.objects.using(db).filter(category=category).update(category=categories[key])
            category.delete(using=db)
        else:
            categories[key] = category
    for name in ("Remeras", "Hoodies"):
        category = categories.get(name.casefold())
        if category is None:
            category = Category.objects.using(db).create(name=name)
        category.name, category.active = name, True
        category.save(using=db, update_fields=["name", "active"])
        categories[name.casefold()] = category
    labels = {"tshirt": "Remera Clásica", "oversized": "Remera Oversize", "hoodie": "Hoodie"}
    for product in Product.objects.using(db).filter(garment_type__in=labels):
        product.name = labels[product.garment_type]
        product.category = categories["hoodies" if product.garment_type == "hoodie" else "remeras"]
        product.save(using=db, update_fields=["name", "category"])
        if product.garment_type in ("tshirt", "hoodie"):
            images = list(ProductImage.objects.using(db).filter(product=product))
            storage = ProductImage._meta.get_field("image").storage
            if not any(image.image and storage.exists(image.image.name) for image in images):
                filename = f"products/{product.garment_type}-catalog.webp"
                if not storage.exists(filename):
                    data = (Path(__file__).resolve().parent.parent / "assets" / f"{product.garment_type}.webp").read_bytes()
                    filename = storage.save(filename, ContentFile(data))
                ProductImage.objects.using(db).filter(product=product).update(is_main=False)
                ProductImage.objects.using(db).create(product=product, image=filename, is_main=True)
    aliases = {"black": "Negro", "white": "Blanco", "gray": "Gris", "grey": "Gris", "blue": "Azul", "red": "Rojo", "green": "Verde"}
    sizes = {"XXL": "2XL", "XXXL": "3XL"}
    for variant in Variant.objects.using(db).all():
        key = " ".join(variant.color.strip().lower().split())
        variant.color = aliases.get(key, key.title())
        variant.size = sizes.get(variant.size.strip().upper(), variant.size.strip().upper())
        variant.save(using=db, update_fields=["color", "size"])
    for category in Category.objects.using(db).all():
        if not Product.objects.using(db).filter(category=category).exists() and "test" in category.name.lower():
            category.delete(using=db)


class Migration(migrations.Migration):
    dependencies = [("products", "0013_normalize_custom_lab_colors")]
    operations = [migrations.RunPython(normalize_catalog, migrations.RunPython.noop)]
