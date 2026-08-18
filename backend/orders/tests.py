from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Product, ProductVariant
from users.models import User

from .models import Order, OrderItem


class OrderApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", email="member@example.com", password="StrongPass123!")
        self.other_user = User.objects.create_user(username="other", email="other@example.com", password="StrongPass123!")
        category = Category.objects.create(name="Tops")
        product = Product.objects.create(name="Oversized GYM", description="", price=Decimal("150000.00"), category=category)
        variant = ProductVariant.objects.create(product=product, size="XL", color="Negro", stock=3)
        self.order = Order.objects.create(user=self.user, total=Decimal("150000.00"))
        OrderItem.objects.create(order=self.order, product=product, variant=variant, size="XL", color="Negro", quantity=1, unit_price=Decimal("150000.00"))
        self.other_order = Order.objects.create(user=self.other_user)

    def test_customer_only_sees_own_orders(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([order["id"] for order in response.data], [self.order.id])
        self.assertEqual(response.data[0]["items"][0]["unit_price"], "150000.00")

    def test_anonymous_cannot_list_orders(self):
        self.assertEqual(self.client.get("/api/orders/").status_code, status.HTTP_401_UNAUTHORIZED)
