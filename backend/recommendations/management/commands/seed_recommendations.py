"""Create editable starter designs without overwriting the merchant's changes."""
import io
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont
from recommendations.models import Culture, DesignRecommendation

COLLECTIONS = {
    "gymrat": [("Iron Discipline", "IRON", "DISCIPLINE", "BUILT BY REPETITION", "#b989ff"), ("No Excuses", "NO", "EXCUSES", "ONE MORE REP / GC", "#c1f47f"), ("Strength Club", "STRENGTH", "CLUB", "EST. EVERY SINGLE DAY", "#bda0f9")],
    "anime": [("Limit Break", "LIMIT", "BREAK", "YOUR NEXT FORM AWAITS", "#bd94ff"), ("Power Level", "POWER", "LEVEL", "TRAIN BEYOND THE LIMIT", "#ffb377"), ("Final Form", "FINAL", "FORM", "THE TRAINING ARC / GC", "#c7e3ff")],
    "memes": [("Gym Then Pizza", "GYM THEN", "PIZZA", "A PERFECTLY BALANCED LIFE", "#eec28b"), ("Modo Bestia", "MODO", "BESTIA", "CARGANDO... 99%", "#be95ff"), ("Rest Day Club", "REST DAY", "CLUB", "MENTALLY AT THE GYM", "#b3e9c2")],
    "urban": [("Concrete Culture", "CONCRETE", "CULTURE", "FROM THE STREET TO THE GYM", "#b9a0ec"), ("After Hours", "AFTER", "HOURS", "THE CITY NEVER RESTS", "#b5e9ea"), ("Own Your Lane", "OWN YOUR", "LANE", "MOVE WITH PURPOSE / GC", "#efb2d4")],
}

def font(size):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)

def artwork(config):
    _, line1, line2, tagline, accent = config
    image = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((190, 30, 610, 450), outline=accent, width=5)
    draw.ellipse((225, 65, 575, 415), outline=accent, width=2)
    draw.polygon([(405, 95), (315, 248), (395, 248), (355, 360), (495, 193), (410, 193), (455, 95)], fill=accent)
    draw.line((70, 468, 730, 468), fill=accent, width=3)
    for text, y in ((line1, 512), (line2, 625)):
        size = 104
        while draw.textbbox((0, 0), text, font=font(size))[2] > 730:
            size -= 2
        draw.text((400, y), text, anchor="mm", fill=accent, font=font(size))
    draw.text((400, 727), tagline, anchor="mm", fill=accent, font=font(25))
    draw.text((400, 782), "G Y M   C U L T U R E", anchor="mm", fill=accent, font=font(18))
    return image

def preview(asset, garment, color):
    image = Image.new("RGBA", (600, 660), "#100c18")
    draw = ImageDraw.Draw(image)
    draw.ellipse((65, 568, 535, 610), fill="#281a39", outline="#644482", width=2)
    sleeve = 145 if garment == "hoodie" else 235
    points = [(220, 100), (155, 126), (65, 210), (105, 365 if garment == "hoodie" else 280), (sleeve, 260), (170, 552), (430, 552), (600-sleeve, 260), (495, 365 if garment == "hoodie" else 280), (535, 210), (445, 126), (380, 100)]
    draw.polygon(points, fill=color)
    draw.line(points + [points[0]], fill="#7d7189", width=2)
    if garment == "hoodie":
        draw.ellipse((215, 54, 385, 188), fill=color, outline="#7d7189", width=2)
    else:
        draw.arc((222, 56, 378, 152), 0, 180, fill="#7d7189", width=4)
    print_image = asset.resize((195, 195), Image.Resampling.LANCZOS)
    image.alpha_composite(print_image, (203, 205))
    return image

def content(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return ContentFile(buffer.getvalue())

class Command(BaseCommand):
    help = "Crea 36 recomendaciones iniciales editables (3 por cultura/prenda); se puede repetir sin duplicar ni sobrescribir."

    def handle(self, *args, **options):
        created = 0
        # Retire only the original generated rectangle previews, preserving any
        # sample whose merchant has replaced the image. The records stay editable.
        legacy = {"IRON LEGS": (124, 58, 237, 180), "SAITAMA POWER": (220, 120, 100, 180), "MOON MUSCLES": (200, 90, 150, 180), "CITY GRAFFITI": (50, 180, 200, 180)}
        for prefix, pixel in legacy.items():
            for item in DesignRecommendation.objects.filter(name__startswith=prefix + " — ", active=True):
                try:
                    with item.preview_image.open('rb') as source, Image.open(source) as old_preview:
                        if old_preview.size == (600, 600) and old_preview.getpixel((300, 300)) == pixel:
                            item.active = False
                            item.save(update_fields=['active', 'updated_at'])
                except (OSError, ValueError):
                    continue
        for slug, designs in COLLECTIONS.items():
            culture, _ = Culture.objects.get_or_create(slug=slug, defaults={"name": slug.upper()})
            for garment in ("tshirt", "oversized", "hoodie"):
                for order, config in enumerate(designs, 1):
                    key = f"starter-{slug}-{garment}-{order}"
                    DesignRecommendation.objects.filter(culture=culture, garment_type=garment, name=config[0], seed_key__isnull=True).update(seed_key=key)
                    item, is_new = DesignRecommendation.objects.get_or_create(
                        seed_key=key,
                        defaults={"culture": culture, "garment_type": garment, "name": config[0], "featured": order == 1, "sort_order": order * 10, "base_color": "Blanco" if order == 2 else "Negro", "default_scale": 1.4 if garment == "hoodie" else 1.8, "default_position": {"x": 0, "y": -.025 if garment == "hoodie" else .1, "z": 1}},
                    )
                    if not is_new:
                        continue
                    asset = artwork(config)
                    item.design_asset.save("design.png", content(asset), save=False)
                    item.preview_image.save("preview.png", content(preview(asset, garment, item.BASE_COLORS[item.base_color])), save=False)
                    item.save()
                    created += 1
        self.stdout.write(self.style.SUCCESS(f"Recomendaciones creadas: {created}. Las existentes se conservaron."))
