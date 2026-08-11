from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from django.core.cache import cache
from unittest.mock import patch

from .models import User


class AuthenticationAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = 'SecurePass123!'
        self.user = User.objects.create_user(
            username='member',
            email='member@example.com',
            password=self.password,
        )

    def login(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_login_successful(self):
        tokens = self.login()
        self.assertIn('access', tokens)
        self.assertIn('refresh', tokens)

    def test_login_with_invalid_credentials(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': 'invalid-password'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_valid_token(self):
        tokens = self.login()
        response = self.client.post(
            '/api/auth/refresh/',
            {'refresh': tokens['refresh']},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_me_requires_token(self):
        response = self.client.get('/api/users/me/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_authenticated_user_public_data(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get('/api/users/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                'id': self.user.id,
                'username': self.user.username,
                'email': self.user.email,
                'role': User.Role.CUSTOMER,
            },
        )
        self.assertNotIn('password', response.data)

    def test_register_creates_customer_with_hashed_password(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'newcustomer',
                'email': 'newcustomer@example.com',
                'password': 'AnotherSecurePass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='newcustomer')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password('AnotherSecurePass123!'))
        self.assertNotEqual(user.password, 'AnotherSecurePass123!')
        self.assertNotIn('password', response.data)

    def test_register_ignores_admin_role_from_request(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'attemptedadmin',
                'email': 'attemptedadmin@example.com',
                'password': 'AnotherSecurePass123!',
                'role': User.Role.ADMIN,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='attemptedadmin')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertEqual(response.data['role'], User.Role.CUSTOMER)

    def test_register_validates_password_against_user_attributes(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'passwordmatch',
                'email': 'passwordmatch@example.com',
                'password': 'passwordmatch123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    @patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'register': '1/minute'})
    def test_register_is_throttled(self):
        payload = {
            'username': 'throttledcustomer',
            'email': 'throttledcustomer@example.com',
            'password': 'AnotherSecurePass123!',
        }
        first_response = self.client.post('/api/auth/register/', payload, format='json')
        second_payload = {
            **payload,
            'username': 'throttledcustomertwo',
            'email': 'throttledcustomertwo@example.com',
        }
        second_response = self.client.post('/api/auth/register/', second_payload, format='json')

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
