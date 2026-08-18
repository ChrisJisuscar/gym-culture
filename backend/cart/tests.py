from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from products.models import Category, Product, ProductVariant
from users.models import User
from .models import Cart, CartItem


class CartApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(username="user_a", email="a@example.com", password="StrongPass123!")
        self.user_b = User.objects.create_user(username="user_b", email="b@example.com", password="StrongPass123!")
        category = Category.objects.create(name="Tops")
        self.product_x = Product.objects.create(name="Camiseta X", description="", price=Decimal("1200.00"), category=category)
        self.product_y = Product.objects.create(name="Camiseta Y", description="", price=Decimal("1500.00"), category=category)
        self.variant_x = ProductVariant.objects.create(product=self.product_x, size="M", color="Negro", stock=5)
        self.variant_y = ProductVariant.objects.create(product=self.product_y, size="L", color="Blanco", stock=3)

    def test_cart_created_and_item_added_for_user(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/cart/items/', {'product': self.product_x.id, 'variant': self.variant_x.id, 'quantity': 2}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cart.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user_a).count(), 1)

    def test_user_a_does_not_see_user_b_cart(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post('/api/cart/items/', {'product': self.product_x.id, 'variant': self.variant_x.id, 'quantity': 2}, format='json')
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get('/api/cart/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'], [])

    def test_stock_validation_and_quantity_increment(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/cart/items/', {'product': self.product_x.id, 'variant': self.variant_x.id, 'quantity': 6}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.post('/api/cart/items/', {'product': self.product_x.id, 'variant': self.variant_x.id, 'quantity': 2}, format='json')
        response = self.client.post('/api/cart/items/', {'product': self.product_x.id, 'variant': self.variant_x.id, 'quantity': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CartItem.objects.get(cart__user=self.user_a, product=self.product_x).quantity, 3)
