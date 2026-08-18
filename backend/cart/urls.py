from django.urls import path

from .views import CartAPI, CartItemViewSet

urlpatterns = [
    path("cart/", CartAPI.as_view(), name="api-cart"),
    path("cart/items/", CartItemViewSet.as_view({"post": "create"}), name="api-cart-items-create"),
    path("cart/items/<int:pk>/", CartItemViewSet.as_view({"patch": "partial_update", "delete": "destroy"}), name="api-cart-item"),
]
