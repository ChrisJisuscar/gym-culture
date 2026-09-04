from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from .models import User
from orders.models import Order


class AuthenticationApiTests(APITestCase):
    def test_register_creates_customer_with_hashed_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "culture_member",
                "email": "member@example.com",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "role": "ADMIN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="member@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_register_rejects_duplicate_email_and_username(self):
        User.objects.create_user(
            username="member", email="member@example.com", password="StrongPass123!"
        )
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "member",
                "email": "member@example.com",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "member2",
                "email": "member2@example.com",
                "password": "StrongPass123!",
                "password_confirm": "DifferentPass456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_by_email_and_me(self):
        User.objects.create_user(
            username="member", email="member@example.com", password="StrongPass123!"
        )
        login = self.client.post(
            "/api/auth/login/",
            {"email": "member@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertIn("access", login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "member@example.com")
        self.assertEqual(
            me.data["date_joined"],
            User.objects.get(email="member@example.com")
            .date_joined.isoformat()
            .replace("+00:00", "Z"),
        )

    def test_me_rejects_anonymous_requests(self):
        self.assertEqual(
            self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_refresh_and_logout_blacklists_the_refresh_token(self):
        User.objects.create_user(
            username="member", email="member@example.com", password="StrongPass123!"
        )
        login = self.client.post(
            "/api/auth/login/",
            {"email": "member@example.com", "password": "StrongPass123!"},
            format="json",
        )
        refresh = login.data["refresh"]

        self.assertEqual(
            self.client.post(
                "/api/auth/refresh/", {"refresh": refresh}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(
            self.client.post(
                "/api/auth/logout/", {"refresh": refresh}, format="json"
            ).status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/refresh/", {"refresh": refresh}, format="json"
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class BackofficeCustomerTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="customer-admin", email="admin-customers@example.com", password="StrongPass123!", role=User.Role.ADMIN)
        self.customer = User.objects.create_user(username="juan", first_name="Juan", last_name="Pérez", email="juan@example.com", password="StrongPass123!")
        self.other = User.objects.create_user(username="maria", first_name="María", last_name="López", email="maria@example.com", password="StrongPass123!", is_active=False)
        self.order = Order.objects.create(user=self.customer, contact_first_name="Juan", contact_last_name="Pérez", contact_email=self.customer.email, total=Decimal("250000"), subtotal=Decimal("250000"))
        Order.objects.create(user=self.customer, status=Order.Status.CANCELLED, total=Decimal("90000"), subtotal=Decimal("90000"))

    def test_customer_receives_403(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/backoffice/customers/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(f"/api/backoffice/customers/{self.customer.id}/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_lists_searches_and_reads_customer_summary(self):
        self.client.force_authenticate(self.admin)
        listing = self.client.get("/api/backoffice/customers/?search=juan@example.com")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)
        row = listing.data["results"][0]
        self.assertEqual(row["order_count"], 2)
        self.assertEqual(row["total_spent"], "250000.00")
        self.assertNotIn("password", row)

        detail = self.client.get(f"/api/backoffice/customers/{self.customer.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.data["orders"]), 2)
        self.assertEqual(detail.data["last_order_at"], max(order.created_at for order in self.customer.orders.all()).isoformat().replace("+00:00", "Z"))
        self.assertNotIn("password", detail.data)
        self.assertNotIn("role", detail.data)

    def test_admin_customer_detail_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/backoffice/customers/999999/").status_code, status.HTTP_404_NOT_FOUND)
