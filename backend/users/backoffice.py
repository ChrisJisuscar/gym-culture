"""Administrative session boundary. Customer APIs keep their JWT authentication."""
from django import forms
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated
from rest_framework.views import APIView

from .models import User
from .permissions import IsAdminRole, is_administrator


class BackofficeAccessMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.startswith('/backoffice/') or request.path == reverse('backoffice-login'):
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('backoffice-login'))
        if not is_administrator(request.user):
            return render(request, 'backoffice/access_denied.html', status=403)

    def process_response(self, request, response):
        if request.path.startswith(('/backoffice/', '/api/backoffice/')):
            response['Cache-Control'] = 'no-store, private'
        return response


class BackofficeAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminRole]

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(exc, NotAuthenticated):
            response.data['code'] = 'session_required'
        return response


class BackofficeLoginForm(forms.Form):
    username = forms.CharField(label='Usuario o correo', max_length=254, widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True}))
    password = forms.CharField(label='Contraseña', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get('username') and data.get('password'):
            identifier = data['username'].strip()
            # Reuse the existing email backend while accepting admin usernames.
            email = User.objects.filter(username=identifier).values_list('email', flat=True).first() or identifier
            self.user = authenticate(self.request, username=email, password=data['password'])
            if not is_administrator(self.user):
                raise forms.ValidationError('No pudimos iniciar sesión. Verificá tus datos y que tu cuenta tenga acceso administrativo.')
        return data


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def backoffice_login(request):
    next_url = request.POST.get('next', request.GET.get('next', ''))
    if not next_url.startswith('/backoffice/') or next_url.startswith(('/backoffice/login/', '/backoffice/logout/')) or not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        next_url = reverse('backoffice-dashboard-page')
    if is_administrator(request.user):
        return redirect(next_url)
    form = BackofficeLoginForm(request, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.user)
        return redirect(next_url)
    return render(request, 'backoffice/login.html', {'form': form, 'next': next_url})


@never_cache
@csrf_protect
@require_POST
def backoffice_logout(request):
    logout(request)
    return redirect('backoffice-login')
