from django.db import migrations


def normalize_categories(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("products", "Category")
    Product = apps.get_model("products", "Product")

    def get_or_create(name):
        category = Category.objects.using(db).filter(name__iexact=name).first()
        if category is None:
            category = Category.objects.using(db).create(name=name, description="")
        return category

    remeras = get_or_create("Remeras")
    hoodies = get_or_create("Hoodies")

    for product in Product.objects.using(db).filter(garment_type__in=("tshirt", "oversized")):
        if product.category_id != remeras.id:
            product.category = remeras
            product.save(using=db, update_fields=["category"])

    for product in Product.objects.using(db).filter(garment_type="hoodie"):
        if product.category_id != hoodies.id:
            product.category = hoodies
            product.save(using=db, update_fields=["category"])

    # Disable leftover test/placeholder categories once nothing references them.
    Product = apps.get_model("products", "Product")
    for category in Category.objects.using(db).filter(active=True).exclude(name__iexact="Remeras").exclude(name__iexact="Hoodies"):
        if not Product.objects.using(db).filter(category=category).exists():
            category.active = False
            category.save(using=db, update_fields=["active"])


class Migration(migrations.Migration):
    dependencies = [("products", "0011_hoodie_image")]
    operations = [migrations.RunPython(normalize_categories, migrations.RunPython.noop)]