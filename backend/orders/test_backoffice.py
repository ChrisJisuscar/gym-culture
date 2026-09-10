from decimal import Decimal
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from products.models import Category, Product, ProductVariant, StockMovement
from payments.models import Payment
from users.models import User
from .models import Order, OrderItem, OrderStatusHistory


class BackofficeCommercialTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="commercial-admin", email="admin@commercial.test", role="ADMIN")
        self.customer = User.objects.create_user(username="commercial-client", email="client@commercial.test")
        self.client.force_authenticate(self.admin)
        category = Category.objects.create(name="Commercial test")
        self.variants = []
        for kind, name in [("tshirt", "Remera Clásica"), ("oversized", "Remera Oversize"), ("hoodie", "Hoodie")]:
            product = Product.objects.create(name=name, garment_type=kind, category=category, price=100)
            self.variants.append(ProductVariant.objects.create(product=product, color="Blanco", size="XL", stock=0))

    def order(self, variant=None, quantity=1, **kwargs):
        variant = variant or self.variants[1]
        order = Order.objects.create(user=self.customer, total=100, shipping_city="Asunción", **kwargs)
        OrderItem.objects.create(order=order, product=variant.product, variant=variant, product_name=variant.product.name, quantity=quantity, unit_price=100, size=variant.size, color=variant.color)
        return order

    def test_stock_all_three_garments_zero_and_filters(self):
        data = self.client.get("/api/backoffice/stock/").data
        ids = {row["id"] for row in data["results"]}
        self.assertTrue({v.id for v in self.variants}.issubset(ids))
        for variant in self.variants:
            rows = self.client.get(f"/api/backoffice/stock/?garment_type={variant.product.garment_type}&stock=out").data["results"]
            self.assertIn(variant.id, [row["id"] for row in rows])
            self.assertTrue(all(row["garment_type"] == variant.product.garment_type and row["stock"] == 0 for row in rows))

    def test_identity_uses_real_product_preserving_snapshot(self):
        order = self.order()
        item = order.items.get()
        item.product_name = "Hoodie"
        item.save()
        data = self.client.get(f"/api/backoffice/orders/{order.id}/").data
        self.assertEqual(data["items"][0]["product_name"], "Remera Oversize")
        self.assertEqual(data["items"][0]["product_name_snapshot"], "Hoodie")
        self.assertIn("Remera Oversize", data["description"])
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Hoodie")

    def test_restock_recalculates_demand_and_audits_fifo(self):
        variant = self.variants[1]
        first, second = self.order(quantity=2), self.order(quantity=2)
        url = f"/api/backoffice/stock/{variant.id}/adjust/"
        pending = self.client.get(f"/api/backoffice/stock/?stock=pending&variant={variant.id}").data["results"][0]
        self.assertEqual((pending["pending_demand"], pending["pending_orders"]), (4, 2))
        response = self.client.post(url, {"movement_type": "RESTOCK", "quantity": 3, "reason": "Reposición"}, format="json")
        self.assertEqual(response.status_code, 200)
        updated = response.data["updated_variant"]
        self.assertEqual((updated["stock"], updated["pending_demand"], updated["pending_orders"]), (0, 1, 1))
        self.assertEqual(first.items.get().allocated_quantity, 2)
        self.assertEqual(second.items.get().allocated_quantity, 1)
        movement = StockMovement.objects.get(variant=variant, movement_type="RESTOCK")
        self.assertEqual((movement.quantity, movement.previous_stock, movement.new_stock, movement.performed_by), (3, 0, 3, self.admin))
        self.assertEqual(movement.reason, "Reposición")
        self.assertIsNotNone(movement.created_at)
        self.assertEqual(StockMovement.objects.filter(variant=variant, movement_type="ORDER").count(), 2)

    def test_archive_preserves_related_data_and_reservations(self):
        order = self.order(payment_status="PAID")
        payment = Payment.objects.create(order=order, provider="mock", amount=100, currency="PYG", status="PAID")
        item = order.items.get()
        item.customization_snapshot = {"configuration": {}, "assets": []}
        item.allocated_quantity = 1
        item.save()
        movement = StockMovement.objects.create(order=order, variant=item.variant, movement_type="ORDER", quantity=1, previous_stock=1, new_stock=0, performed_by=self.admin, reason="Reserva")
        history = OrderStatusHistory.objects.create(order=order, old_status="PENDING", new_status="CONFIRMED", changed_by=self.admin)
        url = f"/api/backoffice/orders/{order.id}/"
        self.assertEqual(self.client.patch(url, {"is_archived": True}, format="json").status_code, 200)
        order.refresh_from_db()
        stamp = order.archived_at
        self.assertEqual(order.archived_by, self.admin)
        self.assertIsNotNone(stamp)
        self.assertEqual(self.client.get("/api/backoffice/orders/").data["count"], 0)
        self.assertEqual(self.client.get("/api/backoffice/orders/?archived=true").data["count"], 1)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.patch(url, {"is_archived": True}, format="json")
        order.refresh_from_db()
        self.assertEqual(order.archived_at, stamp)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(StockMovement.objects.filter(pk=movement.pk).exists())
        self.assertTrue(OrderStatusHistory.objects.filter(pk=history.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.allocated_quantity, 1)
        self.assertIsNotNone(item.customization_snapshot)
        self.assertEqual(self.client.patch(f"{url}status/", {"status": "CONFIRMED"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"is_archived": False}, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/backoffice/orders/").data["count"], 1)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_customer_deactivation_and_permissions(self):
        order = self.order()
        url = f"/api/backoffice/customers/{self.customer.id}/"
        self.assertEqual(self.client.patch(url, {"is_active": False}, format="json").status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertEqual(self.client.get("/api/backoffice/customers/").data["count"], 0)
        self.assertEqual(self.client.get("/api/backoffice/customers/?active=false").data["count"], 1)
        self.assertEqual(self.client.get(url).data["orders"][0]["id"], order.id)
        self.assertEqual(self.client.get(f"/api/backoffice/orders/{order.id}/").status_code, 200)
        self.assertEqual(self.client.patch(url, {"is_active": True}, format="json").status_code, 200)
        staff = User.objects.create_user(username="staff", email="staff@commercial.test", is_staff=True)
        self.assertEqual(self.client.patch(f"/api/backoffice/customers/{staff.id}/", {"is_active": False}, format="json").status_code, 404)
        self.client.force_authenticate(self.customer)
        for endpoint, payload in [(url, {"is_active": False}), (f"/api/backoffice/orders/{order.id}/", {"is_archived": True})]:
            self.assertEqual(self.client.patch(endpoint, payload, format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/backoffice/dashboard/").status_code, 403)

    def test_dashboard_financials_city_status_products_and_critical(self):
        paid = self.order(payment_status="PAID", quantity=2)
        archived = self.order(payment_status="PAID", is_archived=True)
        Order.objects.filter(pk=archived.pk).update(total=300, shipping_city=" asunción ")
        self.order(status="CANCELLED", payment_status="PAID")
        self.order(status="PREPARING", payment_status="PENDING", variant=self.variants[2])
        self.order(payment_status="REFUNDED")
        # Two payment attempts must never multiply order revenue.
        for state in ["FAILED", "PAID"]:
            Payment.objects.create(order=paid, provider="mock", amount=100, currency="PYG", status=state)
        data = self.client.get("/api/backoffice/dashboard/?period=7").data
        k = data["kpis"]
        self.assertEqual(Decimal(k["total_sales"]), 400)
        self.assertEqual(Decimal(k["average_ticket"]), 200)
        self.assertEqual(k["total_orders"], 5)
        self.assertEqual(k["pending_orders"], 2)
        self.assertEqual(k["production_orders"], 1)
        self.assertEqual(k["awaiting_stock"], 2)
        self.assertEqual(k["customers"], 1)
        self.assertEqual(data["orders_by_city"], [{"city": "Asunción", "orders": 5}])
        self.assertEqual(sum(row["orders"] for row in data["orders_by_status"]), 4)
        self.assertEqual(data["top_products"][0]["product__name"], "Remera Oversize")
        self.assertEqual(data["top_products"][0]["quantity"], 4)
        self.assertGreaterEqual(k["low_stock_variants"], 3)
        self.assertTrue(any(row["pending_demand"] > 0 for row in data["low_stock"]))
        self.assertEqual(len(data["sales_over_time"]), 7)
        self.assertEqual(sum(row["sales"] for row in data["sales_over_time"]), 400)
        self.assertEqual(len(self.client.get("/api/backoffice/dashboard/?period=12m").data["sales_over_time"]), 12)
        Order.objects.filter(pk=paid.pk).update(created_at=timezone.now() - timedelta(days=40))
        self.assertEqual(sum(row["orders"] for row in self.client.get("/api/backoffice/dashboard/?period=30").data["sales_over_time"]), 4)

    def test_dashboard_empty_and_bounded_queries(self):
        data = self.client.get("/api/backoffice/dashboard/").data
        self.assertEqual(data["kpis"]["total_sales"], 0)
        self.assertEqual(data["kpis"]["average_ticket"], 0)
        self.assertEqual(data["orders_by_city"], [])
        self.assertEqual(data["top_products"], [])
        self.assertTrue(all(row["orders"] == 0 for row in data["sales_over_time"]))
        self.order()
        with CaptureQueriesContext(connection) as small:
            self.client.get("/api/backoffice/dashboard/")
        for _ in range(10):
            self.order()
        with CaptureQueriesContext(connection) as large:
            self.client.get("/api/backoffice/dashboard/")
        self.assertLessEqual(len(large), len(small) + 1)
        self.assertLess(len(large), 25)
        self.assertEqual(self.client.get("/api/backoffice/dashboard/?period=invalid").status_code, 400)

    def test_dashboard_period_summary_and_recent_activity(self):
        self.order(payment_status="PAID")
        older = self.order(payment_status="PAID")
        Order.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=45))
        for period, expected in [("7", 1), ("30", 1), ("90", 2)]:
            data = self.client.get(f"/api/backoffice/dashboard/?period={period}").data
            self.assertEqual(len(data["sales_over_time"]), int(period))
            self.assertEqual(data["period_summary"], {"orders": expected, "sales": Decimal(100 * expected)})
            self.assertEqual(data["kpis"]["sales_30_days"], 100)
            self.assertEqual(data["kpis"]["orders_today"], 1)
            self.assertEqual(data["kpis"]["orders_this_week"], 1)
