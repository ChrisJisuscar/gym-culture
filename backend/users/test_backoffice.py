from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import User


class BackofficeSessionTests(TestCase):
    pages = ['/backoffice/', '/backoffice/orders/', '/backoffice/orders/999/', '/backoffice/production/', '/backoffice/products/', '/backoffice/products/new/', '/backoffice/products/999/', '/backoffice/stock/', '/backoffice/customers/', '/backoffice/customers/999/', '/backoffice/recommendations/', '/backoffice/recommendations/new/', '/backoffice/recommendations/999/edit/']
    apis = ['/api/backoffice/dashboard/', '/api/backoffice/orders/', '/api/backoffice/orders/999/', '/api/backoffice/orders/999/status/', '/api/backoffice/production/', '/api/backoffice/products/', '/api/backoffice/products/999/', '/api/backoffice/products/999/images/', '/api/backoffice/products/999/images/999/', '/api/backoffice/categories/', '/api/backoffice/stock/', '/api/backoffice/stock/999/adjust/', '/api/backoffice/stock/history/', '/api/backoffice/customers/', '/api/backoffice/customers/999/', '/api/backoffice/recommendations/', '/api/backoffice/recommendations/999/', '/api/backoffice/recommendations/reorder/', '/api/backoffice/recommendations/cultures/', '/api/backoffice/recommendations/cultures/999/']

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='session-admin', email='session-admin@example.com', password='AdminTest123!', role=User.Role.ADMIN)
        cls.staff = User.objects.create_user(username='session-staff', email='staff@example.com', password='AdminTest123!', is_staff=True)
        cls.customer = User.objects.create_user(username='session-customer', email='customer-session@example.com', password='CustomerTest123!')

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def login(self, username='session-admin', password='AdminTest123!', next_url='/backoffice/'):
        self.client.get('/backoffice/login/')
        return self.client.post('/backoffice/login/', {'username': username, 'password': password, 'next': next_url}, HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_admin_username_email_and_staff_login(self):
        for username in [self.admin.username, self.admin.email, self.staff.username]:
            self.client.logout()
            response = self.login(username)
            self.assertRedirects(response, '/backoffice/', fetch_redirect_response=False)
            self.assertIn('_auth_user_id', self.client.session)
            self.assertTrue(self.client.cookies['sessionid']['httponly'])
            self.assertEqual(self.client.cookies['sessionid']['samesite'], 'Lax')

    def test_customer_inactive_and_wrong_password_are_rejected(self):
        self.admin.is_active = False; self.admin.save(update_fields=['is_active'])
        for username, password in [(self.customer.username, 'CustomerTest123!'), (self.staff.username, 'wrong'), (self.admin.username, 'AdminTest123!')]:
            response = self.login(username, password)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'No pudimos iniciar sesión')
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_every_admin_page_requires_session_and_role(self):
        for url in self.pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertTrue(self.client.get(url)['Location'].startswith('/backoffice/login/?next='))
        self.client.force_login(self.customer)
        for url in self.pages:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        for url in self.pages:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 200)

    def test_editor_has_only_session_helper_and_no_second_identity_check(self):
        self.login()
        response = self.client.get('/backoffice/recommendations/new/')
        self.assertContains(response, 'backoffice-session.js')
        self.assertNotContains(response, 'auth-session.js')
        self.assertNotContains(response, 'name="sort_order"')
        self.assertEqual(response['Cache-Control'], 'no-store, private')

    def test_every_admin_api_ignores_even_admin_jwt_and_rejects_customer_session(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.admin)}')
        for url in self.apis:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.customer)
        for url in self.apis:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)

    def test_session_auth_ignores_expired_or_customer_bearer_header(self):
        self.login()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer expired.invalid.token')
        self.assertEqual(self.client.get('/api/backoffice/recommendations/').status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.customer)}')
        self.assertEqual(self.client.get('/api/backoffice/recommendations/').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me/').data['id'], self.customer.id)

    def test_post_patch_delete_enforce_csrf_even_with_jwt(self):
        self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.admin)}')
        url = '/api/backoffice/recommendations/cultures/'
        data = {'slug': 'session-csrf', 'name': 'Session CSRF'}
        self.assertEqual(self.client.post(url, data, format='json').status_code, 403)
        csrf = self.client.cookies['csrftoken'].value
        created = self.client.post(url, data, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(created.status_code, 201, created.data)
        # CultureWriteSerializer omits id; retrieve it from the session-only list.
        pk = next(item['id'] for item in self.client.get(url).data if item['slug'] == 'session-csrf')
        detail = f'{url}{pk}/'
        for method, payload in [('patch', {'name': 'Changed'}), ('delete', {})]:
            self.assertEqual(getattr(self.client, method)(detail, payload, format='json').status_code, 403)
            self.assertIn(getattr(self.client, method)(detail, payload, format='json', HTTP_X_CSRFTOKEN=csrf).status_code, (200, 204))

    def test_logout_requires_post_csrf_and_keeps_customer_jwt_valid(self):
        self.login()
        token = str(AccessToken.for_user(self.customer))
        self.assertEqual(self.client.get('/backoffice/logout/').status_code, 405)
        self.assertEqual(self.client.post('/backoffice/logout/').status_code, 403)
        response = self.client.post('/backoffice/logout/', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertRedirects(response, '/backoffice/login/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(self.client.get('/api/auth/me/').data['id'], self.customer.id)
        self.assertEqual(self.client.get('/api/backoffice/recommendations/').status_code, 403)

    def test_safe_return_path_and_login_csrf(self):
        self.assertEqual(self.client.post('/backoffice/login/', {'username': self.admin.username, 'password': 'AdminTest123!'}).status_code, 403)
        self.assertRedirects(self.login(next_url='https://example.com/steal'), '/backoffice/', fetch_redirect_response=False)
        self.client.logout()
        self.assertRedirects(self.login(next_url='/backoffice/recommendations/new/'), '/backoffice/recommendations/new/', fetch_redirect_response=False)

    def test_session_alone_does_not_authenticate_customer_api(self):
        self.login()
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
