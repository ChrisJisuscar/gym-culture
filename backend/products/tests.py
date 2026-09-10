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
from .services import normalize_color, normalize_size


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
        self.category, _ = Category.objects.get_or_create(name="Remeras")
        self.product = Product.objects.create(garment_type="oversized", name="Oversize", description="Base", price=Decimal("100000"), category=self.category)
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

    def test_zero_stock_variants_are_selectable_and_stock_api_reports_pending(self):
        response = self.client.get(f"/api/products/{self.product.id}/")
        ids = [variant["id"] for variant in response.data["variants"]]
        self.assertIn(self.out.id, ids)
        self.assertEqual(next(v for v in response.data["variants"] if v["id"] == self.out.id)["stock"], 0)
        self.authenticate_admin()
        response = self.client.get(f"/api/backoffice/stock/?variant={self.out.id}&page_size=100")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = next(r for r in response.data["results"] if r["id"] == self.out.id)
        self.assertIn("pending_demand", row)
        self.assertEqual(row["pending_demand"], 0)

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
        low = self.client.get("/api/backoffice/stock/?stock=low&page_size=100")
        out = self.client.get(f"/api/backoffice/stock/?stock=out&variant={self.out.id}")
        self.assertEqual([item["id"] for item in low.data["results"]], [self.low.id])
        self.assertIn(self.out.id, [item["id"] for item in out.data["results"]])

    def test_restock_remove_and_history(self):
        self.authenticate_admin()
        url = f"/api/backoffice/stock/{self.normal.id}/adjust/"
        for movement_type, quantity, expected in (("RESTOCK", 5, 15), ("REMOVE", 4, 11)):
            response = self.client.post(url, {"movement_type": movement_type, "quantity": quantity, "reason": "Conteo manual"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.normal.refresh_from_db()
            self.assertEqual(self.normal.stock, expected)
        self.assertEqual(StockMovement.objects.filter(variant=self.normal).count(), 2)
        self.assertFalse(StockMovement.objects.exclude(performed_by=self.admin).exists())
        history = self.client.get(f"/api/backoffice/stock/history/?variant={self.normal.id}")
        self.assertEqual(history.data["count"], 2)
        rejected = self.client.post(url, {"movement_type": "SET", "quantity": 2, "reason": "Conteo"}, format="json")
        self.assertEqual(rejected.status_code, 400)

    def test_remove_rejects_negative_result_without_movement(self):
        self.authenticate_admin()
        response = self.client.post(f"/api/backoffice/stock/{self.low.id}/adjust/", {"movement_type": "REMOVE", "quantity": 4, "reason": "Merma"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.low.refresh_from_db()
        self.assertEqual(self.low.stock, 3)
        self.assertFalse(StockMovement.objects.filter(variant=self.low).exists())


class OversizedCatalogTests(APITestCase):
    def test_seed_is_editable_catalog_product_with_zero_stock_and_image(self):
        product = Product.objects.get(name="Remera Oversize", garment_type="oversized")
        self.assertEqual(product.price, 0)
        self.assertTrue(product.active)
        self.assertEqual(set(product.variants.values_list("size", flat=True)), {"S", "M", "L", "XL", "2XL"})
        self.assertFalse(product.variants.exclude(stock=0).exists())
        self.assertTrue(product.images.filter(is_main=True).exists())

    def test_lab_keeps_products_and_variants_separate(self):
        category = Category.objects.create(name="Lab integration")
        tshirt = Product.objects.create(name="Regular", description="", price=10, category=category)
        oversized = Product.objects.create(name="Oversized active", description="", price=20, category=category, garment_type="oversized")
        regular = ProductVariant.objects.create(product=tshirt, size="M", color="Negro", stock=3)
        large = ProductVariant.objects.create(product=oversized, size="M", color="Negro", stock=2)
        response = self.client.get("/crear-mi-remera/")
        products = {item["id"]: item for item in response.context["customizer_products"]}
        self.assertEqual([item["id"] for item in products[tshirt.pk]["variants"]], [regular.pk])
        self.assertEqual([item["id"] for item in products[oversized.pk]["variants"]], [large.pk])
        self.assertEqual(products[oversized.pk]["garment_type"], "oversized")


class CategoryNormalizationTests(APITestCase):
    def test_commercial_catalog_is_grouped_under_remeras_and_hoodies(self):
        """Probar que la migración 0012 dejó Remeras/Hoodies y desactivó la categoría de prueba."""
        remeras = Category.objects.get(name="Remeras")
        hoodies = Category.objects.get(name="Hoodies")
        self.assertTrue(remeras.active)
        self.assertTrue(hoodies.active)
        self.assertEqual(set(remeras.products.values_list("garment_type", flat=True)), {"tshirt", "oversized"})
        self.assertEqual(list(hoodies.products.values_list("garment_type", flat=True)), ["hoodie"])
        self.assertEqual(Product.objects.get(name="Remera Clásica", garment_type="tshirt", active=True).category, remeras)
        self.assertEqual(Product.objects.get(name="Hoodie").category, hoodies)
        self.assertFalse(Category.objects.filter(active=True, name__icontains="test").exists())


class CustomLabColorAndStockTests(APITestCase):
    """Fix definitivo del Custom Lab: colores/tallas normalizados por nombre, sin stock en la
    selección, paleta central resoluble y un solo producto activo por prenda."""

    def test_normalize_helpers_resolve_catalog_names(self):
        self.assertEqual(normalize_color("GRIS"), "Gris")
        self.assertEqual(normalize_color("  negro "), "Negro")
        self.assertEqual(normalize_color("azul  marino"), "Azul Marino")
        self.assertEqual(normalize_color(""), "Sin color")
        self.assertEqual(normalize_size("M"), "M")
        self.assertEqual(normalize_size("3xl"), "3XL")
        self.assertEqual(normalize_size("XXL"), "2XL")
        self.assertEqual(normalize_size("XXXL"), "3XL")
        self.assertEqual(normalize_size("4XL"), "4XL")
        self.assertEqual(normalize_size(" gr xl "), "GR XL")

    def test_admin_write_normalizes_color_and_size_on_create_and_patch(self):
        self.admin = User.objects.create_user(username="lab-admin", email="lab@example.com", password="StrongPass123!", role=User.Role.ADMIN)
        self.client.force_authenticate(self.admin)
        category = Category.objects.get(name="Remeras")
        stream = io.BytesIO()
        Image.new("RGB", (80, 80), "gray").save(stream, "JPEG")
        payload = {
            "name": "Remera Nuevas Tallas", "description": "Nueva", "price": "95000",
            "category": str(category.id), "active": "true",
            "variants": json.dumps([{"size": "3XL", "color": "  GRIS ", "stock": 0, "active": True}]),
            "images": SimpleUploadedFile("product.jpg", stream.getvalue(), content_type="image/jpeg"),
        }
        created = self.client.post("/api/backoffice/products/", payload, format="multipart")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        variant = ProductVariant.objects.get(product__name="Remera Nuevas Tallas")
        self.assertEqual((variant.color, variant.size, variant.stock), ("Gris", "3XL", 0))
        patched = self.client.patch(
            f"/api/backoffice/products/{variant.product.id}/",
            {"name": "Remera Nuevas Tallas", "active": True, "variants": [{"id": variant.id, "size": "XXL", "color": "  GRIS ", "stock": 0, "active": True}]},
            format="json",
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)
        variant.refresh_from_db()
        self.assertEqual((variant.color, variant.size), ("Gris", "2XL"))

    def test_custom_lab_json_keeps_zero_stock_variants_selectable(self):
        oversized = Product.objects.create(name="Oversize Lab", description="", price=0, garment_type="oversized", category=Category.objects.get(name="Remeras"))
        blanco_xl = ProductVariant.objects.create(product=oversized, size="XL", color="Blanco", stock=0)
        response = self.client.get("/crear-mi-remera/")
        products = {item["id"]: item for item in response.context["customizer_products"]}
        variants = products[oversized.pk]["variants"]
        self.assertIn(blanco_xl.id, [v["id"] for v in variants])
        self.assertEqual(next(v for v in variants if v["id"] == blanco_xl.id)["stock"], 0)
        self.assertTrue(next(v for v in variants if v["id"] == blanco_xl.id)["active"])

    def test_migrations_leave_one_active_product_per_garment_and_full_palette(self):
        for garment_type in ("tshirt", "oversized", "hoodie"):
            active = Product.objects.filter(garment_type=garment_type, active=True)
            self.assertEqual(active.count(), 1, f"un solo producto activo por {garment_type}")
        colors = set(ProductVariant.objects.filter(active=True, product__active=True).values_list("color", flat=True))
        self.assertEqual(colors, {"Negro", "Blanco", "Gris", "Azul", "Rojo", "Verde"})
        self.assertFalse(ProductVariant.objects.filter(active=True, color__in=["GRIS", "negro", "Blanco "]).exists())
        for garment_type in ("tshirt", "oversized", "hoodie"):
            product = Product.objects.get(garment_type=garment_type, active=True)
            matrix = {(v["color"], v["size"]) for v in product.variants.values("color", "size")}
            self.assertEqual(
                matrix,
                {(color, size) for color in ("Negro", "Blanco", "Gris", "Azul", "Rojo", "Verde") for size in ("S", "M", "L", "XL", "2XL")},
                f"matriz completa color x talla para {garment_type}",
            )
        oversized = Product.objects.get(garment_type="oversized", active=True)
        blanco_xl = ProductVariant.objects.filter(product=oversized, color="Blanco", size="XL", active=True)
        self.assertTrue(blanco_xl.exists())
        self.assertEqual(blanco_xl.get().stock, 0)
