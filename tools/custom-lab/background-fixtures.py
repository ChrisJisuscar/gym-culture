"""Generate all acceptance cases and a visual report of the real algorithm."""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'backend'))
from customizations.background_removal import BackgroundRemovalRejected, BackgroundRemovalService

output = repo / '.venv/custom-lab-artifacts/background'
output.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 110)
small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)


def badge(bg='white', ink='black', enclosed=False):
    image = Image.new('RGBA', (384, 384), bg)
    draw = ImageDraw.Draw(image)
    if enclosed:
        draw.rounded_rectangle((64, 56, 320, 304), radius=38, fill=ink)
        draw.text((192, 180), 'GC', font=font, fill='white', anchor='mm')
        draw.ellipse((178, 252, 206, 280), fill='white')
    else:
        draw.text((192, 188), 'GC', font=font, fill=ink, anchor='mm')
        draw.line((80, 265, 304, 265), fill=ink, width=2)
    return image


gradient = np.zeros((384, 384, 3), dtype=np.uint8)
gradient[..., 0] = np.linspace(20, 220, 384, dtype=np.uint8)
gradient[..., 1] = np.linspace(230, 30, 384, dtype=np.uint8)[:, None]
gradient[..., 2] = 115
fixtures = [
    ('A', 'Logo negro / blanco', badge(), 'PNG'),
    ('B', 'Blanco interior cerrado', badge(enclosed=True), 'PNG'),
    ('C', 'Negro / casi negro', badge('black', '#121212'), 'PNG'),
    ('D', 'JPEG comprimido', badge(enclosed=True).convert('RGB'), 'JPEG'),
    ('E', 'Fondo complejo', Image.fromarray(gradient), 'PNG'),
    ('F', 'PNG transparente', badge((0, 0, 0, 0), enclosed=True), 'PNG'),
    ('G', 'Imagen de 64 px', badge(enclosed=True).resize((64, 64)), 'PNG'),
    ('H', 'WebP comprimido', badge(enclosed=True).convert('RGB'), 'WEBP'),
    ('I', 'Fondo gris', badge('#a0a0a0'), 'PNG'),
    ('J', 'Fondo de color', badge('#9060ca'), 'PNG'),
]
noisy = np.array(badge(enclosed=True).convert('RGB')).astype(float)
noise = np.random.default_rng(42).normal(0, 3, noisy.shape[:2])
noisy += noise[..., None] - np.linspace(0, 8, 384)[None, :, None]
fixtures.append(('K', 'Ruido y variacion leves', Image.fromarray(noisy.clip(0, 255).astype(np.uint8)), 'PNG'))
report = Image.new('RGB', (960, len(fixtures) * 290 + 40), '#100c18')
labels = ImageDraw.Draw(report)
for row, (key, name, original, fmt) in enumerate(fixtures):
    stream = io.BytesIO(); original.save(stream, fmt, **({'quality': 45} if fmt in ('JPEG', 'WEBP') else {}))
    payload = stream.getvalue()
    extension = {'JPEG': 'jpg', 'WEBP': 'webp'}.get(fmt, 'png')
    (output / f'{key}.{extension}').write_bytes(payload)
    try:
        service = BackgroundRemovalService()
        processed = service.remove(io.BytesIO(payload))
        (output / f'{key}-result.png').write_bytes(processed)
        after = Image.open(io.BytesIO(processed)).convert('RGBA')
        status = f'{service.confidence_level} / confianza {service.background_confidence:.2f}'
    except BackgroundRemovalRejected as error:
        after = original
        status = f'SIN CAMBIOS / {error.reason}'
    labels.text((22, row * 290 + 18), f'{key}. {name}', font=small, fill='#d7b0ff')
    labels.text((22, row * 290 + 48), status, font=small, fill='#f3ebff')
    for column, image in enumerate((original, after)):
        tile = Image.new('RGBA', (220, 220), '#50475b')
        draw = ImageDraw.Draw(tile)
        for y in range(0, 220, 16):
            for x in range(0, 220, 16):
                if (x // 16 + y // 16) % 2: draw.rectangle((x, y, x + 15, y + 15), fill='#746982')
        resized = image.convert('RGBA').resize((220, 220), Image.Resampling.LANCZOS)
        tile.alpha_composite(resized)
        report.paste(tile.convert('RGB'), (480 + column * 236, row * 290 + 20))
    print(key, status)
report.save(repo / 'tools/custom-lab/background-removal-cases.png')
