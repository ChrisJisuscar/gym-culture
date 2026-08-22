from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from products.models import Category, Product, ProductVariant
from users.models import User
from .models import Cart, CartItem


class CartApiTests(TestCase):
    preview_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(
            username="user_a", email="a@example.com", password="StrongPass123!"
        )
        self.user_b = User.objects.create_user(
            username="user_b", email="b@example.com", password="StrongPass123!"
        )
        category = Category.objects.create(name="Tops")
        self.product_x = Product.objects.create(
            name="Camiseta X",
            description="",
            price=Decimal("1200.00"),
            category=category,
        )
        self.product_y = Product.objects.create(
            name="Camiseta Y",
            description="",
            price=Decimal("1500.00"),
            category=category,
        )
        self.variant_x = ProductVariant.objects.create(
            product=self.product_x, size="M", color="Negro", stock=5
        )
        self.variant_y = ProductVariant.objects.create(
            product=self.product_y, size="L", color="Blanco", stock=3
        )

    def test_cart_created_and_item_added_for_user(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cart.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user_a).count(), 1)

    def test_user_a_does_not_see_user_b_cart(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 2},
            format="json",
        )
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])

    def test_stock_validation_and_quantity_increment(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 6},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 2},
            format="json",
        )
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            CartItem.objects.get(
                cart__user=self.user_a, product=self.product_x
            ).quantity,
            3,
        )

    def test_anonymous_cannot_add_to_cart(self):
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_can_change_quantity_and_delete_item(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 2},
            format="json",
        )
        item = CartItem.objects.get(cart__user=self.user_a)

        response = self.client.patch(
            f"/api/cart/items/{item.id}/", {"quantity": 3}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quantity"], 3)
        response = self.client.patch(
            f"/api/cart/items/{item.id}/", {"quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quantity"], 1)
        self.assertEqual(
            self.client.delete(f"/api/cart/items/{item.id}/").status_code,
            status.HTTP_204_NO_CONTENT,
        )

    def test_customer_can_empty_cart_and_count_is_total_units(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id, "quantity": 2},
            format="json",
        )
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_y.id, "variant": self.variant_y.id, "quantity": 3},
            format="json",
        )
        response = self.client.get("/api/cart/")
        self.assertEqual(response.data["item_count"], 5)
        self.assertEqual(
            self.client.delete("/api/cart/").status_code, status.HTTP_204_NO_CONTENT
        )
        self.assertEqual(self.client.get("/api/cart/").data["items"], [])

    def test_user_cannot_modify_another_users_item(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_x.id},
            format="json",
        )
        item = CartItem.objects.get(cart__user=self.user_a)
        self.client.force_authenticate(user=self.user_b)
        self.assertEqual(
            self.client.patch(
                f"/api/cart/items/{item.id}/", {"quantity": 2}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(f"/api/cart/items/{item.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_variant_from_another_product_is_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product_x.id, "variant": self.variant_y.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("variant", response.data)

    def test_product_with_variants_requires_variant(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/cart/items/", {"product": self.product_x.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["variant"][0],
            "Selecciona una variante antes de agregar el producto al carrito.",
        )

    def customization(self, content="GYM CULTURE"):
        element = {
            "id": "text-1",
            "type": "text",
            "content": content,
            "x": 50,
            "y": 50,
            "width": 55,
            "height": 18,
            "rotation": 15,
            "font": "Outfit",
            "bold": True,
        }
        return {
            "version": 1,
            "garment": "tshirt",
            "variant": {"color": "Negro", "size": "M"},
            "side": "front",
            "garments": {
                "tshirt": {"front": {"elements": [element]}, "back": {"elements": []}},
                "hoodie": {"front": {"elements": []}, "back": {"elements": []}},
            },
        }

    def customized_payload(self, content="GYM CULTURE"):
        return {
            "product": self.product_x.id,
            "variant": self.variant_x.id,
            "quantity": 1,
            "customization_data": self.customization(content),
            "preview_front": self.preview_data,
            "preview_back": self.preview_data,
        }

    def test_customized_item_saves_snapshot_and_previews(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/cart/items/", self.customized_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = CartItem.objects.get(cart__user=self.user_a)
        self.assertEqual(
            item.customization_data["garments"]["tshirt"]["front"]["elements"][0][
                "content"
            ],
            "GYM CULTURE",
        )
        self.assertTrue(item.preview_front.name)
        self.assertTrue(item.preview_back.name)
        self.assertTrue(response.data["is_customized"])
        self.assertIn("customization_data", response.data)
        self.assertIn("preview_front", response.data)
        self.assertIn("preview_back", response.data)

    def test_customization_image_is_persisted_as_media_reference(self):
        self.client.force_authenticate(user=self.user_a)
        payload = self.customized_payload()
        payload["customization_data"]["garments"]["tshirt"]["front"]["elements"].append(
            {
                "id": "image-1",
                "type": "image",
                "content": self.preview_data,
                "x": 40,
                "y": 40,
                "width": 30,
                "height": 30,
                "rotation": 0,
            }
        )
        response = self.client.post("/api/cart/items/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = CartItem.objects.get(cart__user=self.user_a)
        image_content = item.customization_data["garments"]["tshirt"]["front"][
            "elements"
        ][1]["content"]
        self.assertTrue(image_content.startswith("/media/cart-customizations/"))
        self.assertNotIn("base64,", image_content)

    def test_different_customizations_are_separate_and_same_is_reused(self):
        self.client.force_authenticate(user=self.user_a)
        first = self.client.post(
            "/api/cart/items/", self.customized_payload("GYM CULTURE"), format="json"
        )
        second = self.client.post(
            "/api/cart/items/",
            self.customized_payload("NO PAIN NO GAIN"),
            format="json",
        )
        same = self.client.post(
            "/api/cart/items/", self.customized_payload("GYM CULTURE"), format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(same.status_code, status.HTTP_201_CREATED)
        items = CartItem.objects.filter(cart__user=self.user_a).order_by("id")
        self.assertEqual(items.count(), 2)
        self.assertEqual(items.first().quantity, 2)
        self.assertEqual(items.last().quantity, 1)

    def test_customer_can_update_customization_without_duplicate(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post(
            "/api/cart/items/", self.customized_payload("GYM CULTURE"), format="json"
        )
        item = CartItem.objects.get(cart__user=self.user_a)
        response = self.client.patch(
            f"/api/cart/items/{item.id}/",
            self.customized_payload("EDITED"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user_a).count(), 1)
        self.assertEqual(
            CartItem.objects.get(pk=item.id).customization_data["garments"]["tshirt"][
                "front"
            ]["elements"][0]["content"],
            "EDITED",
        )

    def test_customer_cannot_read_or_update_another_users_customization(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.post("/api/cart/items/", self.customized_payload(), format="json")
        item = CartItem.objects.get(cart__user=self.user_a)
        self.client.force_authenticate(user=self.user_b)
        self.assertEqual(
            self.client.get(f"/api/cart/items/{item.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/cart/items/{item.id}/",
                self.customized_payload("HACKED"),
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_invalid_customization_and_image_are_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        invalid = self.customized_payload()
        invalid["customization_data"]["version"] = 99
        self.assertEqual(
            self.client.post("/api/cart/items/", invalid, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        invalid_image = self.customized_payload()
        invalid_image["preview_front"] = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="
        self.assertEqual(
            self.client.post(
                "/api/cart/items/", invalid_image, format="json"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
