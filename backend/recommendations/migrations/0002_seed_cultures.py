from django.db import migrations


def seed_cultures(apps, schema_editor):
    Culture = apps.get_model("recommendations", "Culture")
    default_image = "cultures/default.jpg"
    for sort_order, culture_data in enumerate([
        {
            "slug": "gymrat",
            "name": "GYMRAT",
            "tagline": "Ser gymrat no es una moda, es una obsesión.",
            "description": "La cultura gymrat hecha prenda.",
            "image": default_image,
        },
        {
            "slug": "anime",
            "name": "ANIME",
            "tagline": "Entrená como si tu historia dependiera de ello.",
            "description": "La cultura anime hecha prenda.",
            "image": default_image,
        },
        {
            "slug": "memes",
            "name": "MEMES",
            "tagline": "El humor como estilo de vida.",
            "description": "La cultura memes hecha prenda.",
            "image": default_image,
        },
        {
            "slug": "urban",
            "name": "URBANO",
            "tagline": "La calle también enseña.",
            "description": "La cultura urbana hecha prenda.",
            "image": default_image,
        },
    ], start=1):
        Culture.objects.get_or_create(
            slug=culture_data["slug"],
            defaults={**culture_data, "active": True, "sort_order": sort_order},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_cultures, noop),
    ]