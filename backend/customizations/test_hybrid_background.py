import io
from unittest.mock import Mock

import numpy as np
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from .background_errors import BackgroundRemovalRejected, SegmentationUnavailable
from .background_removal import BackgroundRemovalService
from .foreground_mask import refine_mask, validate_mask
from .test_background_removal import encoded, logo


def detailed_subject():
    image = Image.new('RGB', (256, 256), 'white')
    drawing = ImageDraw.Draw(image)
    for y in range(40, 220):
        drawing.line((70, y, 185, y), fill=(y, 255 - y, y // 2), width=1)
    return image


class HybridBackgroundTests(SimpleTestCase):
    def test_flat_graphic_and_transparency_never_initialize_a_model(self):
        engine = Mock()
        service = BackgroundRemovalService(engine)
        result = Image.open(io.BytesIO(service.remove(encoded(logo()))))
        self.assertEqual(service.strategy, 'solid')
        self.assertEqual(result.getpixel((128, 128))[3], 255)
        image = logo().convert('RGBA'); image.putpixel((0, 0), (0, 0, 0, 0))
        with self.assertRaises(BackgroundRemovalRejected): service.remove(encoded(image))
        engine.predict.assert_not_called()

    def test_complex_subject_uses_semantic_mask_and_preserves_white_clothing(self):
        image = detailed_subject()
        ImageDraw.Draw(image).rectangle((110, 80, 150, 180), fill='white')
        mask = np.zeros((256, 256), dtype=np.float32); mask[40:220, 70:186] = 1
        engine = Mock(); engine.predict.return_value = mask
        stream = encoded(image); original = stream.getvalue()
        service = BackgroundRemovalService(engine)
        result = Image.open(io.BytesIO(service.remove(stream)))
        engine.predict.assert_called_once()
        self.assertEqual(service.strategy, 'semantic')
        self.assertEqual(result.getpixel((130, 130)), (255, 255, 255, 255))
        self.assertEqual(result.getpixel((5, 5))[3], 0)
        self.assertEqual(stream.getvalue(), original)

    def test_missing_model_fails_without_a_destructive_color_fallback(self):
        engine = Mock(); engine.predict.side_effect = SegmentationUnavailable('missing')
        with self.assertRaises(SegmentationUnavailable): BackgroundRemovalService(engine).remove(encoded(detailed_subject()))

    def test_tiny_fragmented_and_uncertain_masks_are_rejected(self):
        masks = [np.zeros((256, 256), dtype=np.float32), np.ones((256, 256), dtype=np.float32), np.full((256, 256), .5, dtype=np.float32)]
        fragments = np.zeros((256, 256), dtype=np.float32)
        for y in range(10, 230, 30):
            for x in range(10, 230, 30): fragments[y:y + 10, x:x + 10] = 1
        masks.append(fragments)
        for mask in masks:
            with self.subTest(), self.assertRaises(BackgroundRemovalRejected): validate_mask(mask)

    def test_real_holes_and_soft_hair_are_not_eroded(self):
        mask = np.zeros((256, 256), dtype=np.float32); mask[50:210, 60:200] = 1
        mask[110:140, 110:140] = 0  # A confident gap inside an illustration.
        mask[30:50, 115] = .6  # Fine hair, attached to the subject.
        validate_mask(mask)
        result = refine_mask(Image.new('RGB', (256, 256), '#a98147'), mask)
        self.assertEqual(result.getpixel((125, 125))[3], 0)
        self.assertGreater(result.getpixel((115, 40))[3], 100)
        self.assertEqual(result.getpixel((75, 125))[3], 255)

    def test_large_uncertain_holes_are_rejected(self):
        mask = np.zeros((256, 256), dtype=np.float32); mask[30:230, 30:230] = 1
        mask[80:180, 80:180] = .3
        with self.assertRaises(BackgroundRemovalRejected): validate_mask(mask)
