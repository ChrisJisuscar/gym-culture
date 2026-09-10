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

    def test_oversized_round_trip_with_assets_previews_and_cart(self):
        original_stock = self.variant.stock
        self.product.garment_type = "oversized"
        self.product.save()
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        configuration = json.loads(payload["configuration"])
        configuration["garment"]["type"] = "oversized"
        payload["configuration"] = json.dumps(configuration)
        payload["add_to_cart"] = "true"
        response = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        customization = Customization.objects.get(pk=response.data["id"])
        self.assertEqual(customization.configuration["garment"]["type"], "oversized")
        self.assertEqual(customization.variant_id, self.variant.id)
        self.assertTrue(customization.preview_front.name)
        self.assertTrue(customization.preview_back.name)
        self.assertEqual(customization.assets.count(), 1)
        self.assertEqual(CartItem.objects.get().customization_id, customization.id)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, original_stock)
        retrieved = self.client.get(f"/api/customizations/{customization.id}/")
        self.assertEqual(retrieved.data["configuration"]["garment"]["type"], "oversized")

    def test_existing_customization_can_switch_products_and_back(self):
        created = self.create()
        url = f"/api/customizations/{created.data['id']}/"
        other_type = "oversized" if self.product.garment_type == "tshirt" else "tshirt"
        self.other_product.garment_type = other_type
        self.other_product.save()
        for product, variant in ((self.other_product, self.other_variant), (self.product, self.variant)):
            payload = self.payload()
            configuration = self.configuration()
            configuration["garment"].update(type=product.garment_type, productId=product.pk, variantId=variant.pk)
            payload.update(product=product.pk, variant=variant.pk, configuration=json.dumps(configuration))
            response = self.client.patch(url, payload, format="multipart")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["configuration"]["garment"]["type"], product.garment_type)
            self.assertEqual(response.data["product"], product.pk)
            self.assertEqual(response.data["variant"], variant.pk)

    def test_unsupported_garments_and_oversized_variant_mismatch_are_rejected(self):
        self.client.force_authenticate(self.user)
        for garment_type in ("unknown", None, []):
            payload = self.payload()
            configuration = self.configuration()
            configuration["garment"]["type"] = garment_type
            payload["configuration"] = json.dumps(configuration)
            response = self.client.post("/api/customizations/", payload, format="multipart")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        for variant_id in (None, self.other_variant.id):
            payload = self.payload()
            configuration = self.configuration()
            configuration["garment"].update(type="oversized", variantId=variant_id)
            payload["configuration"] = json.dumps(configuration)
            response = self.client.post("/api/customizations/", payload, format="multipart")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

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


class OversizedCommerceTests(CustomizationApiTests):
    def setUp(self):
        super().setUp()
        self.product.garment_type = "oversized"
        self.product.name = "Remera Oversize"
        self.product.save()

    def configuration(self, with_image=False):
        data = super().configuration(with_image)
        data["garment"].update(type=self.product.garment_type, productId=self.product.pk)
        return data

    def test_garment_cannot_use_normal_product(self):
        payload = self.payload()
        config = self.configuration()
        config["garment"]["type"] = "tshirt"
        payload["configuration"] = json.dumps(config)
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_out_of_stock_and_cart_aggregate(self):
        self.client.force_authenticate(self.user)
        self.variant.stock = 1
        self.variant.save()
        payload = self.payload()
        payload["add_to_cart"] = "true"
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, 201)
        payload = self.payload()
        payload["add_to_cart"] = "true"
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, 201)
        self.variant.stock = 0
        self.variant.save()
        self.assertEqual(self.create().status_code, 201)

    def test_edit_updates_cart_variant(self):
        self.client.force_authenticate(self.user)
        payload = self.payload()
        payload["add_to_cart"] = "true"
        created = self.client.post("/api/customizations/", payload, format="multipart")
        variant = ProductVariant.objects.create(product=self.product, size="M", color="Negro", stock=2)
        self.variant = variant
        payload = self.payload()
        config = self.configuration()
        config["garment"]["size"] = "M"
        payload["configuration"] = json.dumps(config)
        response = self.client.patch(f"/api/customizations/{created.data['id']}/", payload, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(CartItem.objects.get().variant_id, variant.pk)


class HoodieCustomizationTests(CustomizationApiTests):
    def setUp(self):
        super().setUp()
        self.product.garment_type = "hoodie"
        self.product.save()
        self.variant.stock = 0
        self.variant.save()

    def configuration(self, with_image=False):
        value = super().configuration(with_image)
        value["garment"].update(type=self.product.garment_type, hoodState="up")
        return value

    def test_hood_state_and_assets_round_trip_without_stock(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        payload["add_to_cart"] = "true"
        response = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        saved = self.client.get(f"/api/customizations/{response.data['id']}/")
        self.assertEqual(saved.data["configuration"]["garment"]["hoodState"], "up")
        self.assertEqual(len(saved.data["assets"]), 1)
        self.assertTrue(CartItem.objects.get().customization_id)

    def test_invalid_hood_state_rejected(self):
        self.client.force_authenticate(self.user)
        payload = self.payload()
        config = self.configuration()
        config["garment"]["hoodState"] = "invalid"
        payload["configuration"] = json.dumps(config)
        self.assertEqual(self.client.post("/api/customizations/", payload, format="multipart").status_code, 400)

    def test_edit_from_cart_keeps_single_item_and_asset(self):
        self.client.force_authenticate(self.user)
        payload = self.payload(with_image=True)
        payload["add_to_cart"] = "true"
        created = self.client.post("/api/customizations/", payload, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        customization_id = created.data["id"]
        self.assertEqual(CartItem.objects.filter(customization_id=customization_id).count(), 1)
        self.assertEqual(CartItem.objects.count(), 1)

        saved = self.client.get(f"/api/customizations/{customization_id}/").data
        configuration = saved["configuration"]
        image = next(design for design in configuration["designs"] if design["type"] == "image")
        self.assertTrue(image.get("assetUrl"))
        self.assertTrue(image.get("assetId"))

        text = next(design for design in configuration["designs"] if design["type"] == "text")
        text["text"] = "GYM CULTURE 2"
        variant = ProductVariant.objects.create(product=self.product, size="M", color="Negro", stock=2)
        self.variant = variant
        configuration["garment"].update(size="M", variantId=variant.pk)
        updated = self.client.patch(
            f"/api/customizations/{customization_id}/",
            {"product": self.product.id, "variant": variant.pk, "configuration": json.dumps(configuration),
             "preview_front": self.image(name="front.webp", image_format="WEBP"),
             "preview_back": self.image(name="back.webp", image_format="WEBP")},
            format="multipart",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().variant_id, variant.pk)
        after = self.client.get(f"/api/customizations/{customization_id}/").data
        self.assertEqual(after["configuration"]["designs"][0]["text"], "GYM CULTURE 2")
        self.assertEqual(len(after["assets"]), 1)
        self.assertTrue(next(design for design in after["configuration"]["designs"] if design["type"] == "image").get("assetUrl"))


class AllGarmentsWithoutStockTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        CustomizationApiTests.setUp(self)

    image = CustomizationApiTests.image
    configuration = CustomizationApiTests.configuration
    payload = CustomizationApiTests.payload

    def test_each_garment_saves_text_images_previews_and_cart_without_stock(self):
        self.client.force_authenticate(self.user)
        self.variant.stock = 0
        self.variant.save()
        for kind in ("tshirt", "oversized", "hoodie"):
            with self.subTest(garment=kind):
                self.product.garment_type = kind
                self.product.save()
                payload = self.payload(with_image=True)
                config = json.loads(payload["configuration"])
                config["garment"].update(type=kind, hoodState="down")
                payload.update(configuration=json.dumps(config), add_to_cart="true")
                response = self.client.post("/api/customizations/", payload, format="multipart")
                self.assertEqual(response.status_code, 201, response.data)
                saved = self.client.get(f"/api/customizations/{response.data['id']}/")
                self.assertEqual(saved.data["configuration"]["garment"]["type"], kind)
                self.assertEqual(len(saved.data["configuration"]["designs"]), 2)
                self.assertTrue(saved.data["preview_front_url"])
                self.assertTrue(saved.data["preview_back_url"])
                self.assertEqual(len(saved.data["assets"]), 1)
        self.assertEqual(CartItem.objects.count(), 3)


class BackgroundRemovalEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        stream = io.BytesIO()
        Image.new("RGBA", (64, 64), "red").save(stream, format="PNG")
        self.image = SimpleUploadedFile("blob.png", stream.getvalue(), content_type="image/png")

    def background_removal(self, result=b"\x89PNG\r\n\x1a\n"):
        from unittest import mock

        from customizations import background_removal
        with mock.patch.object(background_removal.BackgroundRemovalService, "remove", return_value=result):
            return self.client.post("/api/customizations/remove-background/", {"image": self.image}, format="multipart")

    def test_missing_file_returns_400(self):
        response = self.client.post("/api/customizations/remove-background/", {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_background_removal_returns_png_with_no_store(self):
        response = self.background_removal()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_busy_service_returns_429(self):
        from unittest import mock

        from customizations import background_removal
        from customizations.background_removal import BackgroundRemovalBusy
        with mock.patch.object(background_removal.BackgroundRemovalService, "remove", side_effect=BackgroundRemovalBusy()):
            response = self.client.post("/api/customizations/remove-background/", {"image": self.image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_failing_service_returns_503(self):
        from unittest import mock

        from customizations import background_removal
        with mock.patch.object(background_removal.BackgroundRemovalService, "remove", side_effect=RuntimeError("boom")):
            response = self.client.post("/api/customizations/remove-background/", {"image": self.image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
