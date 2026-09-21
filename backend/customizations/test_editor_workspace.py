import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from PIL import Image

from cart.models import Cart, CartItem
from .models import Customization, GeneratedImage, SavedDesign
from . import tests as customization_tests
from .image_generation import ImageGenerationService, HttpImageProvider, GenerationError, GenerationTimeout, GenerationUnavailable
from .print_quality import estimate_print_quality


class WorkspaceAPITests(TestCase):
    image = customization_tests.CustomizationApiTests.image
    configuration = customization_tests.CustomizationApiTests.configuration
    payload = customization_tests.CustomizationApiTests.payload

    def setUp(self):
        customization_tests.CustomizationApiTests.setUp(self)
        temporary = tempfile.TemporaryDirectory(prefix='gc-workspace-')
        self.addCleanup(temporary.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=Path(temporary.name) / 'public', PRIVATE_MEDIA_ROOT=Path(temporary.name) / 'private'))
        self.client.force_authenticate(self.user)
        cache.clear()

    def save_design(self):
        data = self.payload(with_image=True)
        state = json.loads(data['configuration'])
        for index, design in enumerate(state['designs']):
            design.update(layerOrder=index, visibility=index == 1, flipX=True, flipY=False)
        data.update(name='Mi diseño privado', configuration=json.dumps(state))
        response = self.client.post('/api/saved-designs/', data, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_save_reuses_one_customization_without_a_cart(self):
        saved = self.save_design()
        self.assertEqual(Customization.objects.count(), 1)
        self.assertEqual(SavedDesign.objects.count(), 1)
        self.assertFalse(Cart.objects.exists())
        self.assertFalse(CartItem.objects.exists())
        self.assertEqual(saved['garment_type'], 'tshirt')
        state = saved['customization_state']
        self.assertFalse(state['designs'][0]['visibility'])
        self.assertTrue(state['designs'][1]['flipX'])
        self.assertEqual(state['designs'][1]['imageWidth'], 64)
        self.assertIn('dpi', state['designs'][1]['printQuality'])
        self.assertEqual(self.client.get(f"/api/saved-designs/{saved['id']}/").data['customization_state'], state)

    def test_library_and_files_are_private(self):
        saved = self.save_design()
        owner_list = self.client.get('/api/saved-designs/').data
        self.assertEqual(owner_list['count'], 1)
        self.assertNotIn('customization_state', owner_list['results'][0])
        customization = SavedDesign.objects.get().customization
        self.assertTrue(customization.private_assets)
        self.assertIn('private', customization.preview_front.path)
        preview = self.client.get(saved['preview_image'])
        self.assertEqual(preview.status_code, 200)
        b''.join(preview.streaming_content)
        asset_url = saved['customization_state']['designs'][1]['assetUrl']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/saved-designs/').data['count'], 0)
        for url in [f"/api/saved-designs/{saved['id']}/", saved['preview_image'], asset_url]:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/saved-designs/{saved['id']}/", {'name': 'Hacked'}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/saved-designs/{saved['id']}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/saved-designs/{saved['id']}/duplicate/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/saved-designs/').status_code, 401)
        self.assertEqual(self.client.get(asset_url).status_code, 401)

    def test_edit_and_duplicate_are_independent(self):
        saved = self.save_design()
        data = self.payload(with_image=True)
        data['name'] = 'Actualizado'
        edited = self.client.patch(f"/api/saved-designs/{saved['id']}/", data, format='multipart')
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(Customization.objects.count(), 1)
        original = SavedDesign.objects.get()
        copied = self.client.post(f"/api/saved-designs/{saved['id']}/duplicate/")
        self.assertEqual(copied.status_code, 201, copied.data)
        duplicate = SavedDesign.objects.exclude(pk=original.pk).get()
        self.assertNotEqual(duplicate.customization_id, original.customization_id)
        old_asset, new_asset = original.customization.assets.get(), duplicate.customization.assets.get()
        self.assertNotEqual(old_asset.pk, new_asset.pk)
        with old_asset.file.open('rb') as left, new_asset.file.open('rb') as right:
            self.assertEqual(left.read(), right.read())
        self.assertEqual(self.client.delete(f'/api/saved-designs/{original.pk}/').status_code, 204)
        self.assertTrue(Path(new_asset.file.path).exists())
        self.assertFalse(Path(old_asset.file.path).exists())
        self.assertEqual(SavedDesign.objects.count(), 1)

    def test_missing_private_image_has_a_safe_not_found_response(self):
        saved = self.save_design()
        asset = SavedDesign.objects.get().customization.assets.get()
        Path(asset.file.path).unlink()
        self.assertEqual(self.client.get(saved['customization_state']['designs'][1]['assetUrl']).status_code, 404)

    def test_draft_cannot_be_linked_to_cart_but_commercial_copy_survives_delete(self):
        saved = self.save_design()
        data = self.payload(with_image=True); data.update(name='Cart attempt', add_to_cart='true')
        self.assertEqual(self.client.patch(f"/api/saved-designs/{saved['id']}/", data, format='multipart').status_code, 400)
        data = self.payload(with_image=True); data['add_to_cart'] = 'true'
        commercial = self.client.post('/api/customizations/', data, format='multipart')
        self.assertEqual(commercial.status_code, 201, commercial.data)
        self.client.delete(f"/api/saved-designs/{saved['id']}/")
        self.assertEqual(CartItem.objects.get().customization_id, Customization.objects.get().pk)
        self.assertFalse(Customization.objects.get().private_assets)

    def test_invalid_name_and_layer_fields_are_rejected(self):
        data = self.payload(); data['name'] = ' '
        self.assertEqual(self.client.post('/api/saved-designs/', data, format='multipart').status_code, 400)
        for field, value in [('visibility', 'false'), ('flipX', 1), ('flipY', None), ('layerOrder', -1), ('layerOrder', 1.5)]:
            data = self.payload(); config = json.loads(data['configuration']); config['designs'][0][field] = value
            data.update(name='Invalid', configuration=json.dumps(config))
            self.assertEqual(self.client.post('/api/saved-designs/', data, format='multipart').status_code, 400)
        self.assertFalse(Customization.objects.exists())

    @override_settings(IMAGE_GENERATION_PROVIDER='disabled')
    def test_generation_disabled_and_permissions(self):
        self.assertFalse(self.client.get('/api/customizations/editor-config/').data['generation']['enabled'])
        response = self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre'} , format='json')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(GeneratedImage.objects.exists())
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre'}, format='json').status_code, 401)

    def test_generated_asset_is_private_normal_image_and_metadata_is_saved(self):
        payload = self.image().read()
        with patch.object(ImageGenerationService, 'generate_image', return_value=(payload, 'test-provider')):
            response = self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre violeta', 'format': 'vertical'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        generated = GeneratedImage.objects.get()
        self.assertEqual(generated.prompt, 'Tigre violeta')
        self.assertEqual(generated.provider, 'test-provider')
        image = self.client.get(response.data['url'])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(b''.join(image.streaming_content), payload)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(response.data['url']).status_code, 404)

    def test_generation_error_timeout_and_rate_limit(self):
        for exception, status in [(GenerationError('invalid'), 502), (GenerationTimeout('timeout'), 504)]:
            with patch.object(ImageGenerationService, 'generate_image', side_effect=exception):
                response = self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre'}, format='json')
            self.assertEqual(response.status_code, status)
        with patch.object(ImageGenerationService, 'generate_image', side_effect=GenerationUnavailable('disabled')):
            self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre'}, format='json')
            self.assertEqual(self.client.post('/api/customizations/generate-image/', {'prompt': 'Tigre'}, format='json').status_code, 429)
        self.assertFalse(GeneratedImage.objects.exists())


class PrintQualityTests(SimpleTestCase):
    def test_effective_resolution_depends_on_printed_size(self):
        design = {'type': 'image', 'width': .3, 'height': .3, 'scale': 1}
        for pixels, expected in [(3000, 'high'), (1600, 'medium'), (300, 'low')]:
            result = estimate_print_quality({**design, 'imageWidth': pixels, 'imageHeight': pixels}, 'oversized')
            self.assertEqual(result['level'], expected)
        image = {**design, 'imageWidth': 3000, 'imageHeight': 3000}
        small = estimate_print_quality(image, 'oversized')
        large = estimate_print_quality({**image, 'scale': 2}, 'oversized')
        self.assertAlmostEqual(small['dpi'], large['dpi'] * 2, delta=1)
        self.assertEqual(large['level'], 'medium')


class GenerationProviderTests(SimpleTestCase):
    def image_bytes(self):
        output = io.BytesIO(); Image.new('RGB', (128, 128), 'purple').save(output, 'PNG'); return output.getvalue()

    def test_provider_success_and_invalid_output(self):
        provider = Mock(name='provider'); provider.name = 'fake'; provider.generate_image.return_value = self.image_bytes()
        payload, name = ImageGenerationService(provider).generate_image('Tigre', {})
        self.assertEqual(Image.open(io.BytesIO(payload)).mode, 'RGBA')
        self.assertEqual(name, 'fake')
        provider.generate_image.return_value = b'not an image'
        with self.assertRaises(GenerationError): ImageGenerationService(provider).generate_image('Tigre', {})
        provider.generate_image.return_value = None
        with self.assertRaises(GenerationError): ImageGenerationService(provider).generate_image('Tigre', {})

    @override_settings(IMAGE_GENERATION_URL='http://127.0.0.1:9001/generate', IMAGE_GENERATION_API_KEY='', IMAGE_GENERATION_TIMEOUT=1)
    def test_http_timeout_and_bounded_response(self):
        opener = Mock(); opener.open.side_effect = TimeoutError()
        with patch('customizations.image_generation.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(GenerationTimeout): HttpImageProvider().generate_image('Tigre', {})
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        response.read1.side_effect = [json.dumps({'image_base64': base64.b64encode(self.image_bytes()).decode()}).encode(), b'']
        opener.open.side_effect = None; opener.open.return_value = response
        with patch('customizations.image_generation.urllib.request.build_opener', return_value=opener):
            self.assertEqual(HttpImageProvider().generate_image('Tigre', {}), self.image_bytes())
        response.read1.side_effect = [b'a' * 5000]
        with override_settings(IMAGE_GENERATION_MAX_BYTES=10), patch('customizations.image_generation.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(GenerationError): HttpImageProvider().generate_image('Tigre', {})
