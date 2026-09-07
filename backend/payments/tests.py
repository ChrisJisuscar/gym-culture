import hashlib
import hmac
import json
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from orders.models import Order, OrderStatusHistory
from products.models import Category, Product, ProductVariant
from users.models import User

from .models import Payment, PaymentEvent


@override_settings(
    DEBUG=True,
    PAYMENT_PROVIDER="mock",
    PAYMENT_CURRENCY="PYG",
    PAYMENT_WEBHOOK_SECRET="test-webhook-secret",
)
class PaymentApiTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="payer", email="payer@example.com", password="StrongPass123!"
        )
        self.other = User.objects.create_user(
            username="other-payer",
            email="other-payer@example.com",
            password="StrongPass123!",
        )
        self.admin = User.objects.create_user(
            username="payment-admin",
            email="payment-admin@example.com",
            password="StrongPass123!",
            role=User.Role.ADMIN,
        )
        self.order = Order.objects.create(
            user=self.customer,
            subtotal=Decimal("150000.00"),
            total=Decimal("150000.00"),
        )
        self.other_order = Order.objects.create(
            user=self.other,
            subtotal=Decimal("90000.00"),
            total=Decimal("90000.00"),
        )

    def create_payment(self, order=None):
        self.client.force_authenticate(self.customer)
        return self.client.post(
            f"/api/orders/{(order or self.order).id}/payments/",
            {"provider": "mock", "amount": "1.00", "status": "PAID"},
            format="json",
        )

    def webhook(self, payment, *, event_id="evt-1", payment_status="PAID", amount=None, currency="PYG"):
        payload = {
            "event_id": event_id,
            "event_type": f"payment.{payment_status.lower()}",
            "external_id": payment.external_id,
            "status": payment_status,
            "amount": str(amount if amount is not None else payment.amount),
            "currency": currency,
            "payment_method": "mock",
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"test-webhook-secret", body, hashlib.sha256).hexdigest()
        return self.client.generic(
            "POST",
            "/api/payments/webhook/mock/",
            body,
            content_type="application/json",
            HTTP_X_PAYMENT_SIGNATURE=signature,
        )

    def test_payment_uses_backend_order_total_and_exposes_no_secrets(self):
        response = self.create_payment()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, self.order.total)
        self.assertEqual(payment.currency, "PYG")
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertNotIn("metadata", response.data)
        self.assertNotIn("secret", json.dumps(response.data).lower())

    def test_checkout_with_real_jwt_creates_order_and_mock_payment_once(self):
        category = Category.objects.create(name="JWT checkout")
        product = Product.objects.create(
            name="Remera JWT",
            description="",
            price=Decimal("175000.00"),
            category=category,
        )
        variant = ProductVariant.objects.create(
            product=product, size="M", color="Negro", stock=2
        )
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(
            cart=cart, product=product, variant=variant, quantity=1
        )
        login = self.client.post(
            "/api/auth/login/",
            {"email": self.customer.email, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        checkout_payload = {
            "idempotency_key": "6ec12143-75a0-4c6f-8f8d-37f68a333a83",
            "first_name": "JWT",
            "last_name": "Customer",
            "email": self.customer.email,
            "phone": "0981123456",
            "address": "Av. Test 123",
            "city": "Asunción",
            "department": "Capital",
            "payment_provider": "mock",
        }
        created = self.client.post("/api/orders/", checkout_payload, format="json")
        retried = self.client.post("/api/orders/", checkout_payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(retried.status_code, status.HTTP_200_OK, retried.data)
        self.assertEqual(created.data["id"], retried.data["id"])
        self.assertTrue(created.data["order_number"].startswith("GC-"))
        self.assertEqual(created.data["payment"]["status"], Payment.Status.PENDING)
        self.assertEqual(created.data["payment"]["id"], retried.data["payment"]["id"])
        self.assertEqual(Payment.objects.filter(order_id=created.data["id"]).count(), 1)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 1)

    def test_payment_creation_error_rolls_back_checkout(self):
        category = Category.objects.create(name="Failed payment")
        product = Product.objects.create(
            name="Remera rollback",
            description="",
            price=Decimal("120000.00"),
            category=category,
        )
        variant = ProductVariant.objects.create(
            product=product, size="L", color="Blanco", stock=2
        )
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)
        self.client.force_authenticate(self.customer)
        orders_before = Order.objects.count()
        response = self.client.post(
            "/api/orders/",
            {
                "idempotency_key": "6d56fb8d-5fe3-45a3-8678-a48e0fedb214",
                "payment_provider": "unavailable",
                "first_name": "Pago",
                "last_name": "Fallido",
                "email": self.customer.email,
                "phone": "0981123456",
                "address": "Av. Test 123",
                "city": "Asunción",
                "department": "Capital",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), orders_before)
        self.assertTrue(CartItem.objects.filter(cart=cart).exists())
        self.assertFalse(Payment.objects.filter(order__user=self.customer).exists())
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 2)

    def test_anonymous_checkout_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.client.credentials()
        response = self.client.post("/api/orders/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_multiple_attempts_are_allowed_until_paid(self):
        self.assertEqual(self.create_payment().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.create_payment().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.order.payments.count(), 2)

    def test_ownership_cancelled_paid_and_invalid_total_are_rejected(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.post(f"/api/orders/{self.other_order.id}/payments/", {}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["status"])
        self.assertEqual(self.create_payment().status_code, status.HTTP_400_BAD_REQUEST)
        self.order.status = Order.Status.PENDING
        self.order.total = Decimal("0.00")
        self.order.save(update_fields=["status", "total"])
        self.assertEqual(self.create_payment().status_code, status.HTTP_400_BAD_REQUEST)
        self.order.total = Decimal("150000.00")
        self.order.save(update_fields=["total"])
        payment = Payment.objects.create(
            order=self.order,
            provider="mock",
            amount=self.order.total,
            currency="PYG",
            status=Payment.Status.PAID,
        )
        self.assertEqual(self.create_payment().status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(payment)

    def test_customer_and_admin_payment_access(self):
        payment = Payment.objects.create(
            order=self.other_order,
            provider="mock",
            amount=self.other_order.total,
            currency="PYG",
        )
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.get(f"/api/payments/{payment.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(f"/api/payments/{payment.id}/").status_code,
            status.HTTP_200_OK,
        )

    def test_paid_webhook_confirms_order_once(self):
        payment = Payment.objects.get(id=self.create_payment().data["id"])
        first = self.webhook(payment)
        duplicate = self.webhook(payment)
        repeated_paid = self.webhook(payment, event_id="evt-paid-again")
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertTrue(first.data["processed"])
        self.assertFalse(duplicate.data["processed"])
        self.assertTrue(repeated_paid.data["processed"])
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(PaymentEvent.objects.count(), 2)
        self.assertEqual(OrderStatusHistory.objects.count(), 1)
        self.assertIsNone(OrderStatusHistory.objects.get().changed_by)

    def test_webhook_rejected_pending_and_invalid_signature(self):
        payment = Payment.objects.get(id=self.create_payment().data["id"])
        self.assertEqual(
            self.webhook(payment, event_id="evt-failed", payment_status="FAILED").status_code,
            status.HTTP_200_OK,
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(
            self.webhook(payment, event_id="evt-pending", payment_status="PENDING").status_code,
            status.HTTP_200_OK,
        )
        unsigned = self.client.post(
            "/api/payments/webhook/mock/", {}, format="json"
        )
        self.assertEqual(unsigned.status_code, status.HTTP_400_BAD_REQUEST)

    def test_webhook_rejects_wrong_amount_and_currency(self):
        payment = Payment.objects.get(id=self.create_payment().data["id"])
        wrong_amount = self.webhook(payment, event_id="evt-amount", amount="1.00")
        wrong_currency = self.webhook(payment, event_id="evt-currency", currency="USD")
        self.assertEqual(wrong_amount.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong_currency.status_code, status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_mock_can_simulate_all_outcomes_in_debug(self):
        for outcome, expected in (
            ("pending", Payment.Status.PENDING),
            ("rejected", Payment.Status.FAILED),
            ("approved", Payment.Status.PAID),
        ):
            payment = Payment.objects.get(id=self.create_payment().data["id"])
            response = self.client.post(
                f"/api/payments/{payment.id}/mock/", {"outcome": outcome}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["status"], expected)

    @override_settings(DEBUG=False, PAYMENT_PROVIDER="")
    def test_mock_is_disabled_outside_debug(self):
        response = self.create_payment()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payment = Payment.objects.create(
            order=self.order,
            provider="mock",
            amount=self.order.total,
            currency="PYG",
        )
        self.assertEqual(
            self.client.post(
                f"/api/payments/{payment.id}/mock/",
                {"outcome": "approved"},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post("/api/payments/webhook/mock/", {}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
