import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from products.models import Product, ProductVariant
from products.services import adjust_stock
from users.models import User
from cart.models import Cart, CartItem
from orders.models import Order
from orders.services import create_order_from_cart

class OperationalOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operator-customer", first_name="Current", last_name="Name", role=User.Role.ADMIN)
        self.product = Product.objects.get(garment_type="hoodie", active=True)
        self.variant = self.product.variants.get(color="Negro", size="XL")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.cart = Cart.objects.create(user=self.user)

    def create(self, quantity=3):
        CartItem.objects.create(cart=self.cart, product=self.product, variant=self.variant, quantity=quantity)
        return create_order_from_cart(user=self.user, checkout_data=dict(idempotency_key=uuid.uuid4(), first_name="Ana", last_name="Historica", email="checkout@example.com", phone="123", address="Direccion historica", city="Asuncion", department="Central", reference="Porton"))[0]

    def test_historical_customer_description_and_product_preview(self):
        order = self.create()
        self.user.first_name = "Changed"
        self.user.save()
        response = self.client.get(f"/api/backoffice/orders/{order.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("Hoodie", response.data["description"])
        self.assertEqual(response.data["customer"]["first_name"], "Ana")
        self.assertEqual(response.data["customer"]["email"], "checkout@example.com")
        self.assertEqual(response.data["shipping"]["reference"], "Porton")
        self.assertTrue(response.data["items"][0]["product_image"])

    def test_focused_stock_refresh_returns_updated_fifo_demand(self):
        first, second = self.create(3), self.create(2)
        response = self.client.get(f"/api/backoffice/stock/?variant={self.variant.pk}")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["pending_demand"], 5)
        self.assertEqual(response.data["results"][0]["pending_orders"], 2)
        response = self.client.post(f"/api/backoffice/stock/{self.variant.pk}/adjust/", dict(movement_type="RESTOCK", quantity=4, reason="Reposicion"), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["updated_variant"]["pending_demand"], 1)
        self.assertEqual(response.data["updated_variant"]["pending_orders"], 1)
        self.assertEqual(response.data["updated_variant"]["stock"], 0)
        self.assertEqual(first.availability, "AVAILABLE")
        self.assertEqual(second.items.get().allocated_quantity, 1)

    def test_mixed_order_description(self):
        classic = Product.objects.get(garment_type="tshirt", active=True)
        CartItem.objects.create(cart=self.cart, product=classic, variant=classic.variants.first(), quantity=1)
        order = self.create(2)
        self.assertIn("3", order.description)

    def test_customized_preview_and_production_snapshot(self):
        order = self.create(1)
        item = order.items.get()
        item.customization_snapshot = {"configuration": {"garment": {"type": "hoodie", "hoodState": "up"}, "designs": []}, "previewFront": "previews/front.webp", "previewBack": "previews/back.webp", "assets": []}
        item.save()
        response = self.client.get(f"/api/backoffice/orders/{order.pk}/")
        self.assertIn("personalizada", response.data["description"])
        self.assertTrue(response.data["items"][0]["customization"]["preview_front_url"].endswith("previews/front.webp"))
        production = self.client.get("/api/backoffice/production/")
        self.assertEqual(production.data[0]["items"][0]["availability"], "AWAITING_STOCK")
