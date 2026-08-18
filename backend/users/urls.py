from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import LogoutView, MeView, RegisterView, UserViewSet

router = DefaultRouter()

router.register("users", UserViewSet, basename="user")


urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="api_register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("", include(router.urls)),
]
