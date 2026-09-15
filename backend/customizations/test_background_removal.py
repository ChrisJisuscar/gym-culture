import io

import numpy as np
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from .background_removal import BackgroundRemovalRejected, BackgroundRemovalService, SAFE_MESSAGE


def logo(background='white', ink='black', internal=True, size=256):
    image = Image.new('RGB', (size, size), background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((size // 4, size // 4, size * 3 // 4, size * 3 // 4), radius=size // 16, fill=ink)
    if internal:
        draw.rectangle((size * 3 // 8, size * 3 // 8, size * 5 // 8, size * 5 // 8), fill=background)
    return image


def encoded(image, fmt='PNG', **options):
    stream = io.BytesIO()
    image.save(stream, fmt, **options)
    stream.seek(0)
    return stream


class ConservativeBackgroundTests(SimpleTestCase):
    def process(self, image, fmt='PNG', **options):
        service = BackgroundRemovalService()
        stream = encoded(image, fmt, **options)
        before = stream.getvalue()
        result = Image.open(io.BytesIO(service.remove(stream)))
        self.assertEqual(stream.getvalue(), before, 'Original bytes must never change')
        self.assertGreaterEqual(service.background_confidence, .35)
        self.assertIn(service.confidence_level, ('HIGH', 'MEDIUM', 'LOW'))
        return result

    def test_a_black_logo_and_thin_lines_keep_ink(self):
        image = logo(internal=False)
        ImageDraw.Draw(image).line((50, 50, 200, 50), fill='black', width=1)
        result = self.process(image)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((128, 128)), (0, 0, 0, 255))
        self.assertEqual(result.getpixel((128, 50))[3], 255)

    def test_b_enclosed_white_is_not_removed(self):
        result = self.process(logo())
        self.assertEqual(result.getpixel((128, 128)), (255, 255, 255, 255))
        self.assertEqual(result.getpixel((5, 5))[3], 0)
        self.assertEqual(result.getpixel((75, 128))[3], 255)

    def test_c_dark_subject_on_black_rejected(self):
        for ink in ('black', '#151515'):
            with self.subTest(ink=ink), self.assertRaises(BackgroundRemovalRejected):
                self.process(logo('black', ink))

    def test_d_compressed_jpeg_preserves_logo_and_white_interior(self):
        result = self.process(logo(), 'JPEG', quality=65)
        self.assertEqual(result.getpixel((5, 5))[3], 0)
        self.assertEqual(result.getpixel((128, 128))[3], 255)
        self.assertEqual(result.getpixel((75, 128))[3], 255)

    def test_e_complex_border_noise_and_gradient_rejected(self):
        rng = np.random.default_rng(42)
        noise = Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))
        gradient = Image.fromarray(np.broadcast_to(np.arange(256, dtype=np.uint8)[None, :, None], (256, 256, 3)).copy())
        for image in (noise, gradient):
            with self.subTest(kind=image), self.assertRaises(BackgroundRemovalRejected) as error:
                self.process(image)
            self.assertEqual(str(error.exception), SAFE_MESSAGE)

    def test_f_existing_transparency_rejected_without_modification(self):
        image = logo().convert('RGBA')
        image.putpixel((0, 0), (255, 255, 255, 0))
        with self.assertRaises(BackgroundRemovalRejected) as error:
            self.process(image)
        self.assertEqual(error.exception.reason, 'already_transparent')

    def test_gray_black_and_colored_uniform_backgrounds(self):
        for background, ink in (('#888888', 'black'), ('black', 'white'), ('#7037bc', 'white')):
            with self.subTest(background=background):
                result = self.process(logo(background, ink))
                self.assertEqual(result.getpixel((5, 5))[3], 0)
                self.assertEqual(result.getpixel((75, 128))[3], 255)

    def test_low_resolution_and_imperfect_edges_are_supported(self):
        touching = logo()
        ImageDraw.Draw(touching).rectangle((0, 50, 255, 200), fill='black')
        for image in (logo(size=64), touching):
            result = self.process(image)
            self.assertEqual(result.size, image.size)
            self.assertEqual(result.getpixel((5, 5))[3], 0)
            self.assertEqual(result.getpixel((image.width // 4 + 2, image.height // 2))[3], 255)

    def test_small_compressed_jpeg_and_webp_keep_enclosed_details(self):
        for size in (64, 96, 160):
            for fmt in ('JPEG', 'WEBP'):
                with self.subTest(size=size, fmt=fmt):
                    result = self.process(logo(size=size), fmt, quality=35)
                    self.assertEqual(result.size, (size, size))
                    self.assertEqual(result.getpixel((size // 2, size // 2))[3], 255)
                    self.assertLess(result.getpixel((2, 2))[3], 20)

    def test_moderate_noise_shading_and_one_occupied_corner(self):
        rng = np.random.default_rng(27)
        noisy = np.asarray(logo()).astype(np.int16)
        noise = rng.normal(0, 4, noisy.shape).astype(np.int16)
        noisy = Image.fromarray(np.clip(noisy + noise, 0, 255).astype(np.uint8))
        shaded = logo()
        pixels = np.asarray(shaded).copy()
        pixels[:, 128:][np.all(pixels[:, 128:] == 255, axis=2)] = 243
        corner = logo(); ImageDraw.Draw(corner).rectangle((0, 0, 28, 28), fill='black')
        for image in (noisy, Image.fromarray(pixels), corner):
            result = self.process(image)
            self.assertEqual(result.getpixel((128, 128))[3], 255)
            self.assertLess(result.getpixel((250, 250))[3], 40)

    def test_single_pixel_compression_gap_does_not_empty_an_enclosed_region(self):
        image = Image.new('RGB', (256, 256), 'white')
        ImageDraw.Draw(image).rectangle((64, 64, 192, 192), outline='black', width=1)
        image.putpixel((64, 128), (255, 255, 255))
        result = self.process(image)
        self.assertEqual(result.getpixel((128, 128))[3], 255)
        self.assertEqual(result.getpixel((5, 5))[3], 0)

    def test_external_antialias_is_softened_without_eroding_stroke(self):
        image = logo(internal=False)
        ImageDraw.Draw(image).line((65, 128, 65, 160), fill='#eeeeee', width=1)
        # A light external matte next to a strong black stroke.
        ImageDraw.Draw(image).line((63, 100, 63, 150), fill='#eeeeee', width=1)
        result = self.process(image)
        self.assertGreater(result.getpixel((63, 120))[3], 0)
        self.assertLess(result.getpixel((63, 120))[3], 128)
        self.assertEqual(result.getpixel((64, 120)), (0, 0, 0, 255))
        self.assertEqual(result.getpixel((65, 140)), (238, 238, 238, 255), 'Interior detail must stay opaque')

    def test_reasonable_original_resolution_is_preserved(self):
        image = logo(size=2304)
        result = self.process(image)
        self.assertEqual(result.size, (2304, 2304))
        self.assertEqual(result.getpixel((1024, 1024))[3], 255)

    def test_endpoint_rejection_is_actionable_and_does_not_return_image(self):
        cache.clear()
        upload = SimpleUploadedFile('ambiguous.png', encoded(logo('black', 'black')).getvalue(), content_type='image/png')
        response = APIClient().post('/api/customizations/remove-background/', {'image': upload}, format='multipart')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['detail'], SAFE_MESSAGE)
        self.assertLess(response.data['backgroundConfidence'], .84)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_endpoint_returns_confidence_and_png(self):
        cache.clear()
        upload = SimpleUploadedFile('logo.png', encoded(logo()).getvalue(), content_type='image/png')
        response = APIClient().post('/api/customizations/remove-background/', {'image': upload}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(float(response['X-Background-Confidence']), .84)
        self.assertEqual(Image.open(io.BytesIO(response.content)).getpixel((128, 128))[3], 255)
