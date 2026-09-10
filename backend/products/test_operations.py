from django.test import TestCase
from rest_framework.test import APIClient
from django.core.files.storage import default_storage
from products.models import Product, Category, ProductVariant
from products.services import normalize_color, normalize_size
from users.models import User

class OperationalCatalogTests(TestCase):
    def test_commercial_names_categories_and_images(self):
        for kind, name, category in (("tshirt", "Remera Clásica", "Remeras"), ("oversized", "Remera Oversize", "Remeras"), ("hoodie", "Hoodie", "Hoodies")):
            product = Product.objects.get(garment_type=kind, active=True)
            self.assertEqual(product.name, name)
            self.assertEqual(product.category.name, category)
            image = product.images.get(is_main=True)
            self.assertTrue(default_storage.exists(image.image.name))
        self.assertFalse(Category.objects.filter(name__icontains="test").exists())

    def test_normalization_and_category_case_duplicates(self):
        self.assertEqual({normalize_color(value) for value in ("Negro", "negro ", "BLACK")}, {"Negro"})
        self.assertEqual(normalize_size("xxl "), "2XL")
        client = APIClient()
        client.force_authenticate(User.objects.create_user(username="catalog-op", role=User.Role.ADMIN))
        response = client.post("/api/backoffice/categories/", {"name": "remeras"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_all_three_catalogs_expose_zero_stock_color_size_matrix(self):
        for kind in ("tshirt", "oversized", "hoodie"):
            product = Product.objects.get(garment_type=kind, active=True)
            for color, size, stock in (("Negro", "M", 5), ("Negro", "XL", 0), ("Blanco", "M", 0), ("Blanco", "XL", 4)):
                variant, _ = ProductVariant.objects.get_or_create(product=product, color=color, size=size)
                variant.stock = stock
                variant.save()
            response = self.client.get(f"/api/products/{product.pk}/")
            matrix = {(v["color"],v["size"]):v["stock"] for v in response.json()["variants"]}
            self.assertEqual(matrix[("Blanco", "M")], 0)
            self.assertEqual(matrix[("Negro", "XL")], 0)
