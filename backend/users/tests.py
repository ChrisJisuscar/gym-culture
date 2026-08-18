from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class AuthenticationApiTests(APITestCase):
    def test_register_creates_customer_with_hashed_password(self):
        response = self.client.post("/api/auth/register/", {
            "username": "culture_member", "email": "member@example.com",
            "password": "StrongPass123!", "password_confirm": "StrongPass123!", "role": "ADMIN",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="member@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_register_rejects_duplicate_email_and_username(self):
        User.objects.create_user(username="member", email="member@example.com", password="StrongPass123!")
        response = self.client.post("/api/auth/register/", {
            "username": "member", "email": "member@example.com",
            "password": "StrongPass123!", "password_confirm": "StrongPass123!"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post("/api/auth/register/", {
            "username": "member2", "email": "member2@example.com",
            "password": "StrongPass123!", "password_confirm": "DifferentPass456!"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_by_email_and_me(self):
        User.objects.create_user(username="member", email="member@example.com", password="StrongPass123!")
        login = self.client.post("/api/auth/login/", {"email": "member@example.com", "password": "StrongPass123!"}, format="json")

        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertIn("access", login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "member@example.com")

    def test_me_rejects_anonymous_requests(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_and_logout_blacklists_the_refresh_token(self):
        User.objects.create_user(username="member", email="member@example.com", password="StrongPass123!")
        login = self.client.post("/api/auth/login/", {"email": "member@example.com", "password": "StrongPass123!"}, format="json")
        refresh = login.data["refresh"]

        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json").status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, status.HTTP_401_UNAUTHORIZED)
