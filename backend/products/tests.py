import io
import json
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from orders.models import Order, OrderItem
from users.models import User

from .models import Category, Product, ProductImage, ProductVariant, StockMovement


class BackofficeProductAndStockTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = tempfile.TemporaryDirectory(prefix="gym-culture-products-", ignore_cleanup_errors=True)
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
        self.admin = User.objects.create_user(username="catalog-admin", email="catalog@example.com", password="StrongPass123!", role=User.Role.ADMIN)
        self.customer = User.objects.create_user(username="catalog-customer", email="customer@example.com", password="StrongPass123!")
        self.category = Category.objects.create(name="Remeras")
        self.product = Product.objects.create(name="Oversize", description="Base", price=Decimal("100000"), category=self.category)
        self.normal = ProductVariant.objects.create(product=self.product, size="XL", color="Negro", stock=10)
        self.low = ProductVariant.objects.create(product=self.product, size="M", color="Negro", stock=3)
        self.out = ProductVariant.objects.create(product=self.product, size="S", color="Blanco", stock=0)

    def image(self):
        stream = io.BytesIO()
        Image.new("RGB", (80, 80), "purple").save(stream, "JPEG")
        return SimpleUploadedFile("product.jpg", stream.getvalue(), content_type="image/jpeg")

    def authenticate_admin(self):
        self.client.force_authenticate(self.admin)

    def test_customer_cannot_access_product_or_stock_admin_apis(self):
        self.client.force_authenticate(self.customer)
        for url in ("/api/backoffice/products/", "/api/backoffice/categories/", "/api/backoffice/stock/", "/api/backoffice/stock/history/"):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/products/", {"name": "Hack"}, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_backoffice_pages_exist(self):
        for url in ("/backoffice/products/", "/backoffice/stock/", "/backoffice/customers/"):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_public_product_reads_stay_available_and_hide_inactive_variants(self):
        self.out.active = False
        self.out.save(update_fields=["active"])
        response = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.out.id, [variant["id"] for variant in response.data["variants"]])

    def test_admin_lists_creates_product_category_variants_and_image(self):
        self.authenticate_admin()
        category_response = self.client.post("/api/backoffice/categories/", {"name": "Buzos", "description": "", "active": True}, format="json")
        self.assertEqual(category_response.status_code, status.HTTP_201_CREATED)
        payload = {
            "name": "Buzo Custom", "description": "Nuevo", "price": "180000",
            "category": str(category_response.data["id"]), "active": "true",
            "variants": json.dumps([{"size": "L", "color": "Violeta", "stock": 7, "active": True}]),
            "images": self.image(),
        }
        created = self.client.post("/api/backoffice/products/", payload, format="multipart")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        product = Product.objects.get(name="Buzo Custom")
        self.assertEqual(product.variants.get().stock, 7)
        self.assertTrue(ProductImage.objects.filter(product=product, is_main=True).exists())
        self.assertTrue(StockMovement.objects.filter(variant__product=product, movement_type="SET").exists())
        listing = self.client.get("/api/backoffice/products/?search=Buzo&active=true")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)

    def test_admin_edits_and_deactivates_without_breaking_order_snapshot(self):
        order = Order.objects.create(user=self.customer, total=Decimal("100000"))
        item = OrderItem.objects.create(order=order, product=self.product, variant=self.normal, product_name="Oversize", size="XL", color="Negro", quantity=1, unit_price=Decimal("100000"))
        self.authenticate_admin()
        payload = {
            "name": "Oversize Nueva", "active": False,
            "variants": [{"id": self.normal.id, "size": "XL", "color": "Negro", "stock": 8, "active": False}],
        }
        response = self.client.patch(f"/api/backoffice/products/{self.product.id}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Oversize")
        self.assertEqual(item.unit_price, Decimal("100000"))
        self.assertTrue(OrderItem.objects.filter(pk=item.pk).exists())
        movement = StockMovement.objects.get(variant=self.normal)
        self.assertEqual((movement.previous_stock, movement.new_stock), (10, 8))

    def test_admin_uploads_and_deletes_product_image(self):
        self.authenticate_admin()
        uploaded = self.client.post(f"/api/backoffice/products/{self.product.id}/images/", {"image": self.image(), "is_main": "true"}, format="multipart")
        self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED, uploaded.data)
        image_id = uploaded.data["images"][0]["id"]
        deleted = self.client.delete(f"/api/backoffice/products/{self.product.id}/images/{image_id}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProductImage.objects.filter(pk=image_id).exists())

    def test_stock_list_filters_low_and_out(self):
        self.authenticate_admin()
        low = self.client.get("/api/backoffice/stock/?stock=low")
        out = self.client.get("/api/backoffice/stock/?stock=out")
        self.assertEqual([item["id"] for item in low.data["results"]], [self.low.id])
        self.assertEqual([item["id"] for item in out.data["results"]], [self.out.id])

    def test_restock_remove_set_and_history(self):
        self.authenticate_admin()
        url = f"/api/backoffice/stock/{self.normal.id}/adjust/"
        for movement_type, quantity, expected in (("RESTOCK", 5, 15), ("REMOVE", 4, 11), ("SET", 2, 2)):
            response = self.client.post(url, {"movement_type": movement_type, "quantity": quantity, "reason": "Conteo manual"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.normal.refresh_from_db()
            self.assertEqual(self.normal.stock, expected)
        self.assertEqual(StockMovement.objects.filter(variant=self.normal).count(), 3)
        self.assertFalse(StockMovement.objects.exclude(performed_by=self.admin).exists())
        history = self.client.get(f"/api/backoffice/stock/history/?variant={self.normal.id}")
        self.assertEqual(history.data["count"], 3)

    def test_remove_rejects_negative_result_without_movement(self):
        self.authenticate_admin()
        response = self.client.post(f"/api/backoffice/stock/{self.low.id}/adjust/", {"movement_type": "REMOVE", "quantity": 4, "reason": "Merma"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.low.refresh_from_db()
        self.assertEqual(self.low.stock, 3)
        self.assertFalse(StockMovement.objects.filter(variant=self.low).exists())
