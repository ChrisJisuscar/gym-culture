import json
import tempfile
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from customizations.models import Customization, CustomizationAsset
from products.models import Category, Product, ProductVariant, StockMovement
from users.models import User

from .models import Order, OrderItem
from .services import create_order_from_cart


class OrderApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member", email="member@example.com", password="StrongPass123!"
        )
        self.other_user = User.objects.create_user(
            username="other", email="other@example.com", password="StrongPass123!"
        )
        category = Category.objects.create(name="Tops")
        product = Product.objects.create(
            name="Oversized GYM",
            description="",
            price=Decimal("150000.00"),
            category=category,
        )
        variant = ProductVariant.objects.create(
            product=product, size="XL", color="Negro", stock=3
        )
        self.order = Order.objects.create(user=self.user, total=Decimal("150000.00"))
        OrderItem.objects.create(
            order=self.order,
            product=product,
            variant=variant,
            size="XL",
            color="Negro",
            quantity=1,
            unit_price=Decimal("150000.00"),
        )
        self.other_order = Order.objects.create(user=self.other_user)

    def test_customer_only_sees_own_orders(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([order["id"] for order in response.data], [self.order.id])
        self.assertEqual(response.data[0]["items"][0]["unit_price"], "150000.00")

    def test_anonymous_cannot_list_orders(self):
        self.assertEqual(
            self.client.get("/api/orders/").status_code, status.HTTP_401_UNAUTHORIZED
        )


class CheckoutAndBackofficeTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = tempfile.TemporaryDirectory(prefix="gym-culture-orders-", ignore_cleanup_errors=True)
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
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="StrongPass123!", first_name="Ana", last_name="Gómez")
        self.other = User.objects.create_user(username="other-buyer", email="other-buyer@example.com", password="StrongPass123!")
        self.admin = User.objects.create_user(username="operator", email="operator@example.com", password="StrongPass123!", role=User.Role.ADMIN)
        category = Category.objects.create(name="Checkout")
        self.product = Product.objects.create(name="Remera Histórica", description="", price=Decimal("125000.00"), category=category)
        self.variant = ProductVariant.objects.create(product=self.product, size="XL", color="Negro", stock=5)
        self.other_product = Product.objects.create(name="Otra", description="", price=Decimal("99000.00"), category=category)
        self.other_variant = ProductVariant.objects.create(product=self.other_product, size="M", color="Blanco", stock=5)

    def checkout_payload(self, key=None):
        return {
            "idempotency_key": str(key or uuid.uuid4()),
            "first_name": "Ana",
            "last_name": "Gómez",
            "email": "ana@example.com",
            "phone": "0981123456",
            "address": "Av. España 123",
            "city": "Asunción",
            "department": "Capital",
            "reference": "Portón negro",
            "total": "1.00",
            "status": Order.Status.DELIVERED,
        }

    def add_normal_item(self, quantity=1):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        return CartItem.objects.create(cart=cart, product=self.product, variant=self.variant, quantity=quantity)

    def add_custom_item(self):
        preview = SimpleUploadedFile("preview.webp", b"preview", content_type="image/webp")
        customization = Customization.objects.create(
            user=self.user, product=self.product, variant=self.variant,
            preview_front=preview, preview_back=SimpleUploadedFile("back.webp", b"back", content_type="image/webp"),
            state=Customization.State.IN_CART,
        )
        asset = CustomizationAsset.objects.create(
            customization=customization,
            file=SimpleUploadedFile("logo.png", b"original-artwork", content_type="image/png"),
            original_name="logo_empresa.png", mime_type="image/png", width=2000, height=1200, file_size=16,
        )
        customization.configuration = {
            "version": 1,
            "garment": {"type": "tshirt", "color": "Negro", "colorHex": "#111015", "size": "XL", "variantId": self.variant.id},
            "designs": [{
                "id": "image-1", "type": "image", "assetId": str(asset.id), "assetUrl": asset.file.url,
                "position": {"x": 0, "y": 1, "z": .2}, "normal": {"x": 0, "y": 0, "z": 1},
                "rotation": 0, "scale": 1, "aspectRatio": 1, "width": .4, "height": .4,
            }],
        }
        customization.save(update_fields=["configuration", "updated_at"])
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, variant=self.variant, quantity=1, customization=customization)
        return customization, asset

    def post_checkout(self, payload=None):
        self.client.force_authenticate(self.user)
        return self.client.post("/api/orders/", payload or self.checkout_payload(), format="json")

    def test_empty_cart_cannot_create_order(self):
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_recalculates_price_snapshots_and_decrements_stock(self):
        self.add_normal_item(quantity=2)
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get()
        item = order.items.get()
        self.assertEqual(order.total, Decimal("250000.00"))
        self.assertEqual(item.product_name, "Remera Histórica")
        self.assertEqual(item.unit_price, Decimal("125000.00"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        movement = StockMovement.objects.get(movement_type=StockMovement.Type.ORDER)
        self.assertEqual((movement.quantity, movement.previous_stock, movement.new_stock), (2, 5, 3))
        self.assertEqual(movement.performed_by, self.user)
        self.assertFalse(CartItem.objects.exists())
        self.assertTrue(order.order_number.startswith("GC-"))
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.shipping_address, "Av. España 123")
        self.product.name = "Nombre nuevo"
        self.product.price = Decimal("1.00")
        self.product.save(update_fields=["name", "price"])
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Remera Histórica")
        self.assertEqual(item.unit_price, Decimal("125000.00"))

    def test_insufficient_stock_rolls_back_and_preserves_cart(self):
        self.add_normal_item(quantity=6)
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_unexpected_item_creation_error_rolls_back_everything(self):
        self.add_normal_item(quantity=2)
        payload = self.checkout_payload()
        payload["idempotency_key"] = uuid.UUID(payload["idempotency_key"])
        with patch("orders.services.OrderItem.objects.bulk_create", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                create_order_from_cart(user=self.user, checkout_data=payload)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_inactive_product_and_invalid_variant_are_rejected(self):
        item = self.add_normal_item()
        self.product.active = False
        self.product.save(update_fields=["active"])
        self.assertEqual(self.post_checkout().status_code, status.HTTP_400_BAD_REQUEST)
        self.product.active = True
        self.product.save(update_fields=["active"])
        CartItem.objects.filter(pk=item.pk).update(variant=self.other_variant)
        self.assertEqual(self.post_checkout().status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_customized_order_freezes_complete_snapshot(self):
        customization, asset = self.add_custom_item()
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        customization.refresh_from_db()
        item = OrderItem.objects.get()
        self.assertTrue(customization.is_frozen)
        self.assertEqual(item.customization_id, customization.id)
        self.assertEqual(item.customization_snapshot["assets"][0]["id"], str(asset.id))
        self.assertNotIn("assetUrl", json.dumps(response.data["items"][0]["customization"]))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(f"/api/customizations/{customization.id}/", {}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.delete(f"/api/customizations/{customization.id}/").status_code, status.HTTP_400_BAD_REQUEST)

    def test_customization_from_another_user_is_rejected(self):
        customization, _ = self.add_custom_item()
        customization.user = self.other
        customization.save(update_fields=["user"])
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_invalid_customization_configuration_is_rejected(self):
        customization, _ = self.add_custom_item()
        customization.configuration = {"version": 99}
        customization.save(update_fields=["configuration", "updated_at"])
        response = self.post_checkout()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.exists())

    def test_mixed_order_and_idempotent_retry(self):
        self.add_normal_item()
        customization, _ = self.add_custom_item()
        key = uuid.uuid4()
        first = self.post_checkout(self.checkout_payload(key))
        second = self.post_checkout(self.checkout_payload(key))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 2)
        customization.refresh_from_db()
        self.assertTrue(customization.is_frozen)

    def test_customer_reads_only_own_order_and_cannot_change_status(self):
        self.add_normal_item()
        created = self.post_checkout()
        order = Order.objects.get()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/orders/{order.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(f"/api/backoffice/orders/{order.id}/status/", {"status": "CONFIRMED"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.user)
        by_number = self.client.get(f"/api/orders/by-number/{created.data['order_number']}/")
        self.assertEqual(by_number.status_code, status.HTTP_200_OK)

    def test_admin_lists_details_and_dashboard_customer_gets_403(self):
        self.add_normal_item()
        self.post_checkout()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/backoffice/dashboard/").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/backoffice/dashboard/").status_code, status.HTTP_200_OK)
        listing = self.client.get("/api/backoffice/orders/?search=Ana&status=PENDING")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)
        order = Order.objects.get()
        self.assertEqual(self.client.get(f"/api/backoffice/orders/{order.id}/").status_code, status.HTTP_200_OK)

    def test_valid_transitions_are_audited_and_cancel_restores_stock_once(self):
        self.add_normal_item(quantity=2)
        self.post_checkout()
        order = Order.objects.get()
        self.client.force_authenticate(self.admin)
        confirmed = self.client.patch(f"/api/backoffice/orders/{order.id}/status/", {"status": "CONFIRMED"}, format="json")
        cancelled = self.client.patch(f"/api/backoffice/orders/{order.id}/status/", {"status": "CANCELLED"}, format="json")
        duplicate = self.client.patch(f"/api/backoffice/orders/{order.id}/status/", {"status": "CANCELLED"}, format="json")
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(order.status_history.count(), 2)
        cancellation = StockMovement.objects.get(movement_type=StockMovement.Type.CANCELLATION)
        self.assertEqual((cancellation.previous_stock, cancellation.new_stock), (3, 5))
        self.assertEqual(cancellation.performed_by, self.admin)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.Type.CANCELLATION).count(), 1)

    def test_invalid_status_transition_is_rejected(self):
        self.add_normal_item()
        self.post_checkout()
        order = Order.objects.get()
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/backoffice/orders/{order.id}/status/", {"status": "DELIVERED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_production_queue_and_asset_download_are_admin_only(self):
        _, asset = self.add_custom_item()
        self.post_checkout()
        self.client.force_authenticate(self.user)
        download_url = f"/api/backoffice/assets/{asset.id}/download/"
        self.assertEqual(self.client.get(download_url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        production = self.client.get("/api/backoffice/production/")
        self.assertEqual(production.status_code, status.HTTP_200_OK)
        self.assertEqual(len(production.data), 1)
        download = self.client.get(download_url)
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", download["Content-Disposition"])
