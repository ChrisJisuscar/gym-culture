from django.urls import path

from .views import LoginView, MeView, RegisterView


urlpatterns = [
    path('users/me/', MeView.as_view(), name='users-me'),
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='token_obtain_pair'),
]
