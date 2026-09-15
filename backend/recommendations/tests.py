from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from PIL import Image
import io
import tempfile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from products.models import Product
from users.models import User

from .models import Culture, DesignRecommendation, RecommendationAsset

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def upload(name, content):
    return SimpleUploadedFile(name, content, content_type="image/png")


buffer = io.BytesIO()
Image.new("RGBA", (128, 128), "purple").save(buffer, format="PNG")
PNG_1PX = buffer.getvalue()  # Real editor-compatible fixture, 128 px per side.
test_media = None
media_override = None


def setUpModule():
    global test_media, media_override
    test_media = tempfile.TemporaryDirectory()
    media_override = override_settings(MEDIA_ROOT=test_media.name)
    media_override.enable()


def tearDownModule():
    media_override.disable()
    test_media.cleanup()


def make_admin():
    return User.objects.create_user(
        username="admin", email="admin@example.com", password="StrongPass123!", role=User.Role.ADMIN
    )


def make_user():
    return User.objects.create_user(username="user", email="user@example.com", password="StrongPass123!")


def jwt_headers(user):
    access = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {access}"}


def valid_payload(culture_id, name="VALIDO", **overrides):
    payload = {
        "name": name,
        "culture": culture_id,
        "garment_type": "tshirt",
        "preview_image": upload("preview.png", PNG_1PX),
        "design_asset": upload("design.png", PNG_1PX),
        "active": True,
        "featured": False,
        "sort_order": 1,
    }
    payload.update(overrides)
    return payload


class RecommendationsPublicApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.culture_active = Culture.objects.create(
            slug="test-active", name="ACTIVA", tagline="T", description="D", active=True, sort_order=1
        )
        self.culture_inactive = Culture.objects.create(
            slug="test-inactive", name="INACTIVA", tagline="T", description="D", active=False, sort_order=2
        )
        self.recommendation = DesignRecommendation.objects.create(
            name="IRON LEGS",
            culture=self.culture_active,
            garment_type="tshirt",
            preview_image=upload("preview.png", PNG_1PX),
            design_asset=upload("design.png", PNG_1PX),
            active=True,
            featured=True,
            sort_order=1,
        )
        DesignRecommendation.objects.create(
            name="INACTIVO",
            culture=self.culture_active,
            garment_type="tshirt",
            active=False,
            sort_order=2,
        )
        DesignRecommendation.objects.create(
            name="HOODIE",
            culture=self.culture_active,
            garment_type="hoodie",
            active=True,
            sort_order=3,
        )

    def test_culture_list_only_active(self):
        response = self.client.get("/api/recommendations/cultures/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item["slug"] for item in response.data}
        self.assertIn("gymrat", slugs)
        self.assertIn("test-active", slugs)
        self.assertNotIn("test-inactive", slugs)

    def test_recommendation_list_filters_by_culture_and_garment(self):
        response = self.client.get("/api/recommendations/", {"culture": "test-active", "garment_type": "tshirt"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in response.data["results"]]
        self.assertEqual(names, ["IRON LEGS"])

    def test_recommendation_list_only_active(self):
        response = self.client.get("/api/recommendations/", {"culture": "test-active"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_recommendation_list_invalid_garment(self):
        response = self.client.get("/api/recommendations/", {"culture": "test-active", "garment_type": "sombrero"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recommendation_serializer_builds_urls(self):
        response = self.client.get("/api/recommendations/", {"culture": "test-active", "garment_type": "tshirt"})
        item = response.data["results"][0]
        self.assertIn("http", item["preview_image_url"])
        self.assertIn("design_asset_url", item)
        self.assertEqual(item["garment_label"], "Remera")
        self.assertEqual(item["garment_type"], "tshirt")


class RecommendationsBackofficeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.culture = Culture.objects.create(
            slug="test-urban", name="URBANO", tagline="T", description="D", active=True, sort_order=1
        )

    def test_backoffice_requires_admin(self):
        self.client.force_authenticate(user=make_user())
        response = self.client.get("/api/backoffice/recommendations/cultures/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_backoffice_create_recommendation(self):
        self.client.force_authenticate(user=make_admin())
        response = self.client.post(
            "/api/backoffice/recommendations/",
            {
                "name": "NUEVO",
                "culture": self.culture.id,
                "garment_type": "tshirt",
                "preview_image": upload("preview.png", PNG_1PX),
                "design_asset": upload("design.png", PNG_1PX),
                "active": True,
                "featured": False,
                "sort_order": 1,
                "default_position": '{"x": 0.5, "y": 0.5, "z": 0.01}',
                "default_scale": 1.2,
                "default_rotation": 15,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DesignRecommendation.objects.filter(name="NUEVO").exists())

    def test_backoffice_create_recommendation_invalid_position(self):
        self.client.force_authenticate(user=make_admin())
        response = self.client.post(
            "/api/backoffice/recommendations/",
            {
                "name": "MAL",
                "culture": self.culture.id,
                "garment_type": "tshirt",
                "default_position": '{"x": "alto"}',
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_backoffice_reorder(self):
        self.client.force_authenticate(user=make_admin())
        first = DesignRecommendation.objects.create(name="A", culture=self.culture, garment_type="tshirt", sort_order=1)
        second = DesignRecommendation.objects.create(name="B", culture=self.culture, garment_type="hoodie", sort_order=2)
        response = self.client.post(
            "/api/backoffice/recommendations/reorder/",
            {"culture": self.culture.id, "ordered_ids": [second.id, first.id], "expected_order": [first.id, second.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DesignRecommendation.objects.get(pk=first.id).sort_order, 2)
        self.assertEqual(DesignRecommendation.objects.get(pk=second.id).sort_order, 1)


class RecommendationsCsrfApiTests(TestCase):
    """Valida el mecanismo CSRF de las vistas backoffice de recomendaciones.

    Las vistas requieren sesión Django y CSRF; un JWT no otorga acceso.
    """

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.culture = Culture.objects.create(
            slug="test-urban", name="URBANO", tagline="T", description="D", active=True, sort_order=1
        )

    def obtain_csrf_token(self):
        self.client.get("/backoffice/recommendations/")
        return self.client.cookies["csrftoken"].value

    def test_backoffice_page_sets_csrf_cookie_and_token(self):
        self.client.force_login(user=make_admin())
        response = self.client.get("/backoffice/recommendations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("csrftoken", response.cookies)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_backoffice_session_post_with_csrf_creates(self):
        self.client.force_login(user=make_admin())
        token = self.obtain_csrf_token()
        response = self.client.post(
            "/api/backoffice/recommendations/",
            valid_payload(self.culture.id, name="CSRF OK"),
            format="multipart",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DesignRecommendation.objects.filter(name="CSRF OK").exists())

    def test_backoffice_session_post_without_csrf_rejected(self):
        self.client.force_login(user=make_admin())
        response = self.client.post(
            "/api/backoffice/recommendations/",
            valid_payload(self.culture.id, name="SIN CSRF"),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DesignRecommendation.objects.filter(name="SIN CSRF").exists())

    def test_backoffice_session_patch_with_csrf_replaces_design_asset(self):
        admin = make_admin()
        self.client.force_login(user=admin)
        token = self.obtain_csrf_token()
        recommendation = DesignRecommendation.objects.create(
            name="ORIGINAL",
            culture=self.culture,
            garment_type="tshirt",
            preview_image=upload("preview.png", PNG_1PX),
            design_asset=upload("design.png", PNG_1PX),
        )
        old_asset = recommendation.design_asset.url
        response = self.client.patch(
            f"/api/backoffice/recommendations/{recommendation.id}/",
            {
                "name": "RENOMBRADA",
                "design_asset": upload("nuevo.png", PNG_1PX),
            },
            format="multipart",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recommendation.refresh_from_db()
        self.assertEqual(recommendation.name, "RENOMBRADA")
        self.assertNotEqual(recommendation.design_asset.url, old_asset)

    def test_backoffice_jwt_post_without_session_rejected(self):
        self.client.credentials(**jwt_headers(make_admin()))
        response = self.client.post(
            "/api/backoffice/recommendations/",
            valid_payload(self.culture.id, name="JWT SIN CSRF"),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DesignRecommendation.objects.filter(name="JWT SIN CSRF").exists())

    def test_backoffice_jwt_non_admin_rejected(self):
        self.client.credentials(**jwt_headers(make_user()))
        response = self.client.post(
            "/api/backoffice/recommendations/",
            valid_payload(self.culture.id, name="NO ADMIN"),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_backoffice_unauthenticated_rejected(self):
        response = self.client.post(
            "/api/backoffice/recommendations/",
            valid_payload(self.culture.id, name="ANONIMO"),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProductGarmentTypeSanityTests(TestCase):
    def test_garment_types_include_custom_lab_models(self):
        values = {choice[0] for choice in Product.GarmentType.choices}
        self.assertTrue({"tshirt", "oversized", "hoodie"}.issubset(values))


class ShowroomDataTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_admin())
        self.culture = Culture.objects.get(slug="gymrat")

    def create(self, **overrides):
        return self.client.post('/api/backoffice/recommendations/', valid_payload(self.culture.id, **overrides), format='multipart')

    def test_edit_without_files_preserves_assets_and_color(self):
        item = self.create().data
        response = self.client.patch(f"/api/backoffice/recommendations/{item['id']}/", {"name": "EDITADO", "base_color": "Blanco", "active": False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['design_asset_url'], item['design_asset_url'])
        self.assertEqual(response.data['base_color_hex'], '#ebe9e4')
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/recommendations/', {'culture': 'gymrat'}).data['count'], 0)

    def test_backoffice_filters_all_fields(self):
        self.create(name='Visible', garment_type='hoodie', active=True)
        self.create(name='Hidden', garment_type='tshirt', active=False)
        response = self.client.get('/api/backoffice/recommendations/', {'culture': self.culture.id, 'garment_type': 'hoodie', 'active': 'true', 'search': 'vis'})
        self.assertEqual([item['name'] for item in response.data['results']], ['Visible'])
        self.assertEqual(self.client.get('/api/backoffice/recommendations/', {'culture': 'wrong'}).status_code, 400)

    def test_invalid_geometry_settings_are_rejected(self):
        for values in ({'default_scale': 0}, {'default_scale': 3}, {'default_rotation': 181}, {'base_color': '#ffffff'}, {'default_position': '{"x": 2, "y": 0, "z": 1}'}):
            with self.subTest(values=values):
                self.assertEqual(self.create(**values).status_code, 400)

    def test_missing_or_tiny_assets_are_rejected(self):
        response = self.client.post('/api/backoffice/recommendations/', {'name': 'Broken', 'culture': self.culture.id, 'garment_type': 'tshirt'}, format='json')
        self.assertEqual(response.status_code, 400)
        image = io.BytesIO()
        Image.new('RGB', (8, 8)).save(image, format='PNG')
        self.assertEqual(self.create(design_asset=upload('tiny.png', image.getvalue())).status_code, 400)

    def test_inactive_culture_hides_recommendations(self):
        self.create()
        self.culture.active = False
        self.culture.save()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/recommendations/', {'culture': 'gymrat'}).data['count'], 0)

    def test_order_has_priority_over_featured(self):
        a = self.create(name='A', featured=True).data
        b = self.create(name='B').data
        response = self.client.post('/api/backoffice/recommendations/reorder/', {'culture': self.culture.id, 'ordered_ids': [b['id'], a['id']], 'expected_order': [a['id'], b['id']]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['name'] for item in self.client.get('/api/recommendations/', {'culture': 'gymrat'}).data['results']], ['B', 'A'])

    def test_seed_covers_every_combination_and_preserves_edits(self):
        call_command('seed_recommendations', stdout=io.StringIO())
        self.assertEqual(DesignRecommendation.objects.count(), 36)

        for culture in Culture.objects.filter(active=True):
            for garment in ('tshirt', 'oversized', 'hoodie'):
                self.assertEqual(culture.recommendations.filter(garment_type=garment).count(), 3)
        item = DesignRecommendation.objects.first()
        item.active = False
        item.base_color = 'Gris'
        item.name = 'Renombrado por el administrador'
        item.save()
        call_command('seed_recommendations', stdout=io.StringIO())
        item.refresh_from_db()
        self.assertFalse(item.active)
        self.assertEqual(item.base_color, 'Gris')
        self.assertEqual(DesignRecommendation.objects.count(), 36)


def recommendation_state(garment='hoodie', designs=None):
    return {'version': 1, 'garment': {'type': garment, 'color': 'Negro', 'colorHex': '#111015', 'size': 'XL', 'variantId': None, 'productId': None, 'hoodState': 'up'}, 'designs': designs or []}


def text_layer():
    return {'id': 'text-1', 'type': 'text', 'text': 'GYM CULTURE', 'fontFamily': 'Arial', 'fontSize': 280, 'color': '#ffffff', 'position': {'x': 0, 'y': .1, 'z': .1}, 'normal': {'x': 0, 'y': 0, 'z': 1}, 'rotation': 15, 'scale': 1.2, 'aspectRatio': 2, 'width': .2, 'height': .1, 'projectionVersion': 2, 'surface': 'Base'}


class RecommendationEditorStateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_admin())
        self.culture = Culture.objects.get(slug='gymrat')

    def create(self, state=None, **extra):
        import json
        return self.client.post('/api/backoffice/recommendations/', {'name': 'Custom Lab', 'culture': self.culture.id, 'active': True, 'garment_type': 'hoodie', 'customization_state': json.dumps(state or recommendation_state(designs=[text_layer()])), 'preview_image': upload('preview.webp.png', PNG_1PX), **extra}, format='multipart')

    def test_create_edit_keeps_identity_and_full_schema(self):
        import json
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data['id']
        state = response.data['customization_state']
        self.assertEqual(state['garment']['hoodState'], 'up')
        self.assertEqual(state['designs'][0]['rotation'], 15)
        state['garment'].update(type='oversized', size='M', color='Blanco', colorHex='#ebe9e4')
        state['designs'][0]['text'] = 'EDITADO'
        edited = self.client.patch(f'/api/backoffice/recommendations/{pk}/', {'name': 'Editada', 'garment_type': 'oversized', 'customization_state': json.dumps(state), 'preview_image': upload('new.png', PNG_1PX)}, format='multipart')
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(DesignRecommendation.objects.count(), 1)
        self.assertEqual(edited.data['id'], pk)
        self.assertEqual(edited.data['customization_state']['garment']['size'], 'M')
        self.assertNotEqual(edited.data['preview_image_url'], response.data['preview_image_url'])

    def test_assets_are_owned_and_urls_are_generated_on_server(self):
        layer = {**text_layer(), 'id': 'image-1', 'type': 'image', 'assetKey': 'upload-1', 'assetUrl': 'https://untrusted.invalid/image.png'}
        result = self.create(recommendation_state(designs=[layer]), **{'asset_upload-1': upload('art.png', PNG_1PX)})
        self.assertEqual(result.status_code, 201, result.data)
        design = result.data['customization_state']['designs'][0]
        self.assertNotIn('assetKey', design)
        self.assertTrue(design['assetUrl'].startswith('/media/recommendations/'))
        self.assertEqual(RecommendationAsset.objects.get(pk=design['assetId']).recommendation_id, result.data['id'])
        foreign = self.create(recommendation_state(designs=[design]))
        self.assertEqual(foreign.status_code, 400)

    def test_state_changes_require_generated_preview(self):
        item = self.create().data
        response = self.client.patch(f"/api/backoffice/recommendations/{item['id']}/", {'customization_state': item['customization_state']}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f"/api/backoffice/recommendations/{item['id']}/", {'active': False}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_background_versions_are_preserved_in_public_recommendation(self):
        from customizations.background_removal import BackgroundRemovalService
        from customizations.test_background_removal import encoded, logo
        original = encoded(logo()).getvalue()
        derived = BackgroundRemovalService().remove(io.BytesIO(original))
        layer = {**text_layer(), 'type': 'image', 'assetKey': 'derived', 'originalAssetKey': 'original', 'backgroundRemoved': True}
        response = self.create(recommendation_state(designs=[layer]), **{'asset_derived': upload('derived.png', derived), 'asset_original': upload('original.png', original)})
        self.assertEqual(response.status_code, 201, response.data)
        self.client.force_authenticate(user=None)
        item = self.client.get('/api/design-recommendations/', {'culture': 'gymrat', 'garment': 'hoodie'}).data['results'][0]
        restored = item['customization_state']['designs'][0]
        self.assertTrue(restored['backgroundRemoved'])
        self.assertNotEqual(restored['assetId'], restored['originalAssetId'])
        self.assertEqual(restored['position'], layer['position'])
        self.assertEqual((restored['rotation'], restored['scale']), (15, 1.2))
        with RecommendationAsset.objects.get(pk=restored['originalAssetId']).file.open('rb') as asset:
            self.assertEqual(asset.read(), original)
        with RecommendationAsset.objects.get(pk=restored['assetId']).file.open('rb') as asset:
            self.assertEqual(Image.open(asset).getpixel((0, 0))[3], 0)

    def test_schema_and_asset_validation_match_custom_lab(self):
        bad = recommendation_state(designs=[text_layer()]); bad['designs'][0]['scale'] = 9
        self.assertEqual(self.create(bad).status_code, 400)
        bad = recommendation_state(); bad['garment']['hoodState'] = 'invalid'
        self.assertEqual(self.create(bad).status_code, 400)
        layer = {**text_layer(), 'type': 'image', 'assetKey': 'missing'}
        self.assertEqual(self.create(recommendation_state(designs=[layer])).status_code, 400)
        layer = {**text_layer(), 'source': {'dataUrl': 'data:image/png;base64,abc'}}
        self.assertEqual(self.create(recommendation_state(designs=[layer])).status_code, 400)

    def test_public_alias_filters_and_returns_serializable_state(self):
        self.create()
        self.client.force_authenticate(user=None)
        result = self.client.get('/api/design-recommendations/', {'culture': 'gymrat', 'garment': 'hoodie'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['results'][0]['customization_state']['version'], 1)
        self.assertTrue(result.data['results'][0]['preview_url'])
        self.assertEqual(self.client.get('/api/design-recommendations/', {'culture': 'anime', 'garment': 'hoodie'}).data['count'], 0)

    def test_admin_page_reuses_editor_and_has_no_purchase_controls(self):
        self.client.force_login(User.objects.get(username='admin'))
        response = self.client.get('/backoffice/recommendations/new/')
        self.assertContains(response, 'data-customizer-mode="recommendation-admin"')
        self.assertContains(response, 'id="customizer-3d-container"')
        self.assertContains(response, 'id="save-recommendation"')
        self.assertNotContains(response, 'id="add-cart"')
        self.assertNotContains(response, 'id="recommendations-showroom"')
