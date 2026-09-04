import io
import json
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from cart.models import CartItem
from products.models import Category, Product, ProductVariant
from users.models import User

from .models import Customization, CustomizationAsset


class CustomizationApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = tempfile.TemporaryDirectory(prefix="gym-culture-tests-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls.media_override.disable()
            cls.media_directory.cleanup()

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="owner", email="owner@example.com", password="StrongPass123!")
        self.other = User.objects.create_user(username="other", email="other@example.com", password="StrongPass123!")
        category = Category.objects.create(name="Custom")
        self.product = Product.objects.create(name="Remera", description="", price=Decimal("89000"), category=category)
        self.other_product = Product.objects.create(name="Otra", description="", price=Decimal("99000"), category=category)
        self.variant = ProductVariant.objects.create(product=self.product, size="XL", color="Negro", stock=5)
        self.other_variant = ProductVariant.objects.create(product=self.other_product, size="XL", color="Negro", stock=5)

    def image(self, image_format="PNG", name=None, size=(64, 64), content_type=None):
        stream = io.BytesIO()
        Image.new("RGBA" if image_format in {"PNG", "WEBP"} else "RGB", size, "red").save(stream, format=image_format)
        mime = content_type or ("image/jpeg" if image_format == "JPEG" else f"image/{image_format.lower()}")
        return SimpleUploadedFile(name or f"image.{image_format.lower()}", stream.getvalue(), content_type=mime)

    def configuration(self, with_image=False):
        designs = [{
            "id": "text-1", "type": "text", "text": "GYM CULTURE", "fontFamily": "Outfit", "color": "#FFFFFF", "fontSize": 280,
            "position": {"x": 0, "y": 1, "z": .2}, "normal": {"x": 0, "y": 0, "z": 1}, "rotation": 0, "scale": 1, "aspectRatio": 2, "width": .5, "height": .25,
        }]
        if with_image:
            designs.append({
                "id": "image-1", "type": "image", "assetKey": "upload-1", "position": {"x": 0, "y": 1, "z": .2}, "normal": {"x": 0, "y": 0, "z": 1},
                "rotation": 0, "scale": 1, "aspectRatio": 1, "width": .4, "height": .4,
            })
        return {"version": 1, "garment": {"type": "tshirt", "color": "Negro", "colorHex": "#111015", "size": "XL", "variantId": self.variant.id}, "designs": designs}

    def payload(self, with_image=False, image_format="PNG"):
        data = {
            "product": self.product.id,
            "variant": self.variant.id,
            "configuration": json.dumps(self.configuration(with_image)),
            "preview_front": self.image(name="front.webp", image_format="WEBP"),
            "preview_back": self.image(name="back.webp", image_format="WEBP"),
        }
        if with_image:
            data["asset_upload-1"] = self.image(image_format=image_format)
        return data

    def create(self, **kwargs):
        self.client.force_authenticate(self.user)
        return self.client.post("/api/customizations/", self.payload(**kwargs), format="multipart")

    def test_authenticated_user_creates_owned_customization(self):
        response = self.create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customization.objects.get().user, self.user)

    def test_anonymous_user_cannot_create(self):
        response = self.client.post("/api/customizations/", self.payload(), format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_png_jpeg_and_webp_assets_are_accepted(self):
        for image_format in ("PNG", "JPEG", "WEBP"):
            response = self.create(with_image=True, image_format=image_format)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(CustomizationAsset.objects.count(), 3)

    def test_non_image_and_mime_mismatch_are_rejected(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        payload["asset_upload-1"] = SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)
        payload = self.payload(with_image=True)
        payload["asset_upload-1"] = self.image(content_type="image/jpeg")
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_is_rejected(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        payload["asset_upload-1"] = SimpleUploadedFile("large.png", b"x" * (10 * 1024 * 1024 + 1), content_type="image/png")
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_configuration_and_wrong_variant_are_rejected(self):
        self.client.force_authenticate(self.user)
        payload = self.payload()
        payload["configuration"] = json.dumps({"version": 99})
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)
        payload = self.payload()
        payload["variant"] = self.other_variant.id
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_retrieve_update_and_delete(self):
        created = self.create()
        customization_id = created.data["id"]
        self.assertEqual(self.client.get(f"/api/customizations/{customization_id}/").status_code, status.HTTP_200_OK)
        payload = self.payload()
        config = self.configuration()
        config["designs"][0]["text"] = "EDITED"
        payload["configuration"] = json.dumps(config)
        updated = self.client.patch(f"/api/customizations/{customization_id}/", payload, format="multipart")
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        self.assertEqual(updated.data["configuration"]["designs"][0]["text"], "EDITED")
        self.assertEqual(self.client.delete(f"/api/customizations/{customization_id}/").status_code, status.HTTP_204_NO_CONTENT)

    def test_other_user_cannot_read_update_or_delete(self):
        created = self.create()
        url = f"/api/customizations/{created.data['id']}/"
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(url, self.payload(), format="multipart").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_create_can_atomically_add_customization_to_cart(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        payload["add_to_cart"] = "true"
        response = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        item = CartItem.objects.get(cart__user=self.user)
        self.assertEqual(str(item.customization_id), response.data["id"])
        self.assertIsNone(item.customization_data)

    def test_normal_cart_item_still_works(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/cart/items/", {"product": self.product.id, "variant": self.variant.id, "quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["is_customized"])

    def test_configuration_never_contains_data_url_after_upload(self):
        response = self.create(with_image=True)
        serialized = json.dumps(response.data["configuration"])
        self.assertNotIn("base64", serialized)
        self.assertIn("assetId", serialized)
        self.assertIn("assetUrl", serialized)

    def test_data_url_inside_configuration_is_rejected(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        configuration = self.configuration(with_image=True)
        configuration["designs"][1]["source"] = {"dataUrl": "data:image/png;base64,AAAA"}
        payload["configuration"] = json.dumps(configuration)
        response = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
