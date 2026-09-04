from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BackofficeAssetDownloadAPI,
    BackofficeDashboardAPI,
    BackofficeOrderDetailAPI,
    BackofficeOrdersAPI,
    BackofficeOrderStatusAPI,
    BackofficeProductionAPI,
    OrderByNumberAPI,
    OrderViewSet,
)

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("orders/by-number/<str:order_number>/", OrderByNumberAPI.as_view(), name="order-by-number"),
    path("backoffice/dashboard/", BackofficeDashboardAPI.as_view(), name="backoffice-dashboard"),
    path("backoffice/orders/", BackofficeOrdersAPI.as_view(), name="backoffice-orders"),
    path("backoffice/orders/<int:pk>/", BackofficeOrderDetailAPI.as_view(), name="backoffice-order-detail"),
    path("backoffice/orders/<int:pk>/status/", BackofficeOrderStatusAPI.as_view(), name="backoffice-order-status"),
    path("backoffice/production/", BackofficeProductionAPI.as_view(), name="backoffice-production"),
    path("backoffice/assets/<uuid:asset_id>/download/", BackofficeAssetDownloadAPI.as_view(), name="backoffice-asset-download"),
    path("", include(router.urls)),
]
