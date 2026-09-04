from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BackofficeCategoriesAPI,
    BackofficeProductDetailAPI,
    BackofficeProductImageAPI,
    BackofficeProductImageDetailAPI,
    BackofficeProductsAPI,
    BackofficeStockAdjustAPI,
    BackofficeStockAPI,
    BackofficeStockHistoryAPI,
    CategoryViewSet,
    ProductViewSet,
)

router = DefaultRouter()

router.register("categories", CategoryViewSet)
router.register("products", ProductViewSet)


urlpatterns = [
    path("backoffice/products/", BackofficeProductsAPI.as_view(), name="backoffice-products"),
    path("backoffice/products/<int:pk>/", BackofficeProductDetailAPI.as_view(), name="backoffice-product-detail"),
    path("backoffice/products/<int:pk>/images/", BackofficeProductImageAPI.as_view(), name="backoffice-product-image"),
    path("backoffice/products/<int:pk>/images/<int:image_id>/", BackofficeProductImageDetailAPI.as_view(), name="backoffice-product-image-detail"),
    path("backoffice/categories/", BackofficeCategoriesAPI.as_view(), name="backoffice-categories"),
    path("backoffice/stock/", BackofficeStockAPI.as_view(), name="backoffice-stock"),
    path("backoffice/stock/<int:variant_id>/adjust/", BackofficeStockAdjustAPI.as_view(), name="backoffice-stock-adjust"),
    path("backoffice/stock/history/", BackofficeStockHistoryAPI.as_view(), name="backoffice-stock-history"),
    path("", include(router.urls)),
]
