"""Real local inference against public rembg examples; no customer uploads leave the machine."""
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'backend'))
from customizations.background_removal import BackgroundRemovalService, BackgroundRemovalRejected

root = repo / '.venv/custom-lab-artifacts/semantic'
paths = sorted(root.glob('*.jpg'))
rows = []
report = Image.new('RGB', (1100, 380 * len(paths)), '#100b18')
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
labels = ImageDraw.Draw(report)
for index, path in enumerate(paths):
    original = Image.open(path).convert('RGBA')
    start = time.perf_counter()
    service = BackgroundRemovalService()
    try:
        payload = service.remove(io.BytesIO(path.read_bytes()))
        result = Image.open(io.BytesIO(payload))
        (root / f'{path.stem}-result.png').write_bytes(payload)
        status = f'{service.strategy} / {service.confidence_level} / {service.background_confidence:.3f}'
    except BackgroundRemovalRejected as error:
        result = original
        status = f'REJECT / {error.reason}'
    seconds = time.perf_counter() - start
    rows.append({'file': path.name, 'status': status, 'seconds': round(seconds, 2)})
    (root / 'qa.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(rows[-1], flush=True)
    labels.text((15, index * 380 + 20), path.name, fill='#d4a9fa', font=font)
    labels.text((15, index * 380 + 52), status, fill='white', font=font)
    labels.text((15, index * 380 + 80), f'{seconds:.1f} seconds', fill='white', font=font)
    for column, image in enumerate((original, result)):
        tile = Image.new('RGBA', (360, 340), '#52495d')
        draw = ImageDraw.Draw(tile)
        for y in range(0, 340, 16):
            for x in range(0, 360, 16):
                if (x // 16 + y // 16) % 2: draw.rectangle((x, y, x + 15, y + 15), fill='#756a82')
        image = image.copy(); image.thumbnail(tile.size)
        tile.alpha_composite(image, ((360 - image.width) // 2, (340 - image.height) // 2))
        report.paste(tile.convert('RGB'), (360 + column * 370, index * 380 + 20))
    report.save(repo / 'tools/custom-lab/semantic-comparison.png')
report.save(repo / 'tools/custom-lab/semantic-comparison.png')
(root / 'qa.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
