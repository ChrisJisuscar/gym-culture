import uuid
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from cart.models import Cart, CartItem
from products.models import Category, Product, ProductImage, ProductVariant, StockMovement
from products.services import adjust_stock
from users.models import User
from .models import Order, OrderItem
from .services import create_order_from_cart, transition_order_status, allocate_variant_stock


class AvailabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="allocation", role=User.Role.ADMIN)
        category = Category.objects.create(name="Allocation tests")
        self.product = Product.objects.create(name="Hoodie", category=category, price=500, description="", garment_type="hoodie")
        self.variant = ProductVariant.objects.create(product=self.product, size="XL", color="Negro", stock=0)

    def order(self, quantity):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, variant=self.variant, quantity=quantity)
        payload = dict(idempotency_key=uuid.uuid4(), first_name="A", last_name="B", email="a@example.com", phone="123", address="Street", city="City", department="State")
        return create_order_from_cart(user=self.user, checkout_data=payload)[0]

    def restock(self, quantity):
        return adjust_stock(variant=self.variant, movement_type="RESTOCK", quantity=quantity, reason="Reposicion", performed_by=self.user)

    def test_zero_stock_order_and_restock(self):
        order = self.order(2)
        self.assertEqual(order.availability, "AWAITING_STOCK")
        self.assertEqual(order.items.get().shortage_quantity, 2)
        self.assertFalse(StockMovement.objects.filter(movement_type="ORDER").exists())
        self.restock(10)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)
        self.assertEqual(order.availability, "AVAILABLE")
        self.assertEqual(order.items.get().allocated_quantity, 2)
        self.assertEqual(order.payment_status, "PENDING")
        movement = StockMovement.objects.get(movement_type="ORDER")
        self.assertEqual((movement.previous_stock, movement.quantity, movement.new_stock, movement.order_id), (10, 2, 8, order.pk))
        self.assertEqual(allocate_variant_stock(variant=self.variant, performed_by=self.user), 0)

    def test_partial_allocation_cancellation_restores_only_one_once(self):
        self.variant.stock = 1
        self.variant.save()
        order = self.order(3)
        item = order.items.get()
        self.assertEqual((item.quantity, item.allocated_quantity, item.shortage_quantity), (3, 1, 2))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)
        transition_order_status(order=order, new_status="CANCELLED", changed_by=self.user)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        with self.assertRaises(ValidationError):
            transition_order_status(order=order, new_status="CANCELLED", changed_by=self.user)
        self.assertEqual(StockMovement.objects.get(movement_type="CANCELLATION").quantity, 1)
        self.restock(5)
        item.refresh_from_db()
        self.assertEqual(item.allocated_quantity, 1)

    def test_fifo_and_partial_restock(self):
        first, second = self.order(2), self.order(3)
        self.restock(3)
        self.assertEqual(first.items.get().allocated_quantity, 2)
        self.assertEqual(second.items.get().allocated_quantity, 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)
        self.restock(2)
        self.assertEqual(second.availability, "AVAILABLE")

    def test_shortage_blocks_production_not_checkout_or_payment(self):
        order = self.order(2)
        order = transition_order_status(order=order, new_status="CONFIRMED", changed_by=self.user)
        with self.assertRaises(ValidationError):
            transition_order_status(order=order, new_status="PREPARING", changed_by=self.user)
        self.restock(2)
        order = transition_order_status(order=order, new_status="PREPARING", changed_by=self.user)
        self.assertEqual(order.status, "PREPARING")

    def test_backoffice_filter_and_adjustment(self):
        order = self.order(2)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/backoffice/orders/?availability=AWAITING_STOCK")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(order.pk, [row["id"] for row in response.data["results"]])
        response = client.post(f"/api/backoffice/stock/{self.variant.pk}/adjust/", dict(movement_type="RESTOCK", quantity=2, reason="Reposicion"), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get(f"/api/backoffice/orders/{order.pk}/")
        self.assertEqual(response.data["availability"], "AVAILABLE")
        self.assertEqual(response.data["items"][0]["shortage_quantity"], 0)

    def test_detail_exposes_shortage_block_fields_and_product_image(self):
        order = self.order(4)
        product_image = SimpleUploadedFile("hoodie.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9", content_type="image/jpeg")
        ProductImage.objects.create(product=self.product, image=product_image, is_main=True)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(f"/api/backoffice/orders/{order.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["items"][0]
        self.assertEqual(item["availability"], "AWAITING_STOCK")
        self.assertEqual(item["shortage_quantity"], 4)
        self.assertIsNotNone(item["product_image"])
        self.assertIn("/media/products/", item["product_image"])
        self.assertTrue(item["product_image"].endswith(".jpg"))

    def test_stock_api_reports_pending_demand(self):
        self.order(2)
        self.order(3)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(f"/api/backoffice/stock/?variant={self.variant.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        row = next(r for r in response.data["results"] if r["id"] == self.variant.pk)
        self.assertEqual(row["stock"], 0)
        self.assertEqual(row["pending_demand"], 5)

    def test_manual_adjustment_never_makes_negative_stock(self):
        with self.assertRaises(ValidationError):
            adjust_stock(variant=self.variant, movement_type="REMOVE", quantity=1, reason="Invalid", performed_by=self.user)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)


from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections
from django.test import TransactionTestCase
from threading import Barrier


class ConcurrentAllocationTests(TransactionTestCase):
    setUp = AvailabilityTests.setUp
    order = AvailabilityTests.order

    def test_two_allocators_cannot_use_the_same_unit(self):
        first, second = self.order(1), self.order(1)
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock=1)
        barrier = Barrier(2)
        def allocate():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return allocate_variant_stock(variant=self.variant, performed_by=self.user)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            result = list(executor.map(lambda _: allocate(), range(2)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(first.items.get().allocated_quantity, 1)
        self.assertEqual(second.items.get().allocated_quantity, 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)

    def test_restock_racing_cancellation_preserves_physical_units(self):
        order = self.order(3)
        barrier = Barrier(2)
        def action(cancel):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if cancel:
                    transition_order_status(order=order, new_status="CANCELLED", changed_by=self.user)
                else:
                    adjust_stock(variant=self.variant, movement_type="RESTOCK", quantity=2, reason="Concurrent restock", performed_by=self.user)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(action, [True, False]))
        self.variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.variant.stock, 2)
        self.assertEqual(order.status, "CANCELLED")
