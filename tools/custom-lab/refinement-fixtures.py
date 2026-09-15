"""Technical print targets, not catalog assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[2] / '.venv/custom-lab-artifacts/projection'
root.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 64)
for name, size in [('square', (512, 512)), ('wide', (960, 240)), ('vertical', (256, 768)), ('transparent', (512, 512))]:
    image = Image.new('RGBA', size, (255, 255, 255, 0) if name == 'transparent' else '#fbf7ff')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size[0] - 9, size[1] - 9), radius=18, outline='#8b22dd', width=16)
    if name in ('square', 'wide'):
        for x in range(64, size[0], 64): draw.line((x, 24, x, size[1] - 24), fill='#b685d9', width=4)
        for y in range(64, size[1], 64): draw.line((24, y, size[0] - 24, y), fill='#b685d9', width=4)
    if name == 'vertical':
        draw.ellipse((60, 48, 196, 184), fill='#e68f55')
        draw.polygon([(75, 210), (182, 210), (230, 480), (30, 480)], fill='#722bc1')
        draw.line((96, 480, 80, 700), fill='#22202c', width=28)
        draw.line((160, 480, 176, 700), fill='#22202c', width=28)
    else:
        draw.text((size[0] / 2, size[1] / 2), 'GC / PRINT', font=font, anchor='mm', fill='#7817bf', stroke_width=2)
    image.save(root / f'{name}.png')
print('Four print fixtures generated.')
