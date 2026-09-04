from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BackofficeCustomerDetailAPI, BackofficeCustomersAPI, LogoutView, MeView, RegisterView, UserViewSet

router = DefaultRouter()

router.register("users", UserViewSet, basename="user")


urlpatterns = [
    path("backoffice/customers/", BackofficeCustomersAPI.as_view(), name="backoffice-customers"),
    path("backoffice/customers/<int:pk>/", BackofficeCustomerDetailAPI.as_view(), name="backoffice-customer-detail"),
    path("auth/register/", RegisterView.as_view(), name="api_register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("", include(router.urls)),
]
