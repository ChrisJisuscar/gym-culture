from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    api_home,
    backoffice_dashboard,
    backoffice_order_detail,
    backoffice_orders,
    backoffice_production,
    backoffice_products,
    backoffice_product_detail,
    backoffice_product_create,
    backoffice_stock,
    backoffice_customers,
    backoffice_customer_detail,
    cart,
    checkout,
    create_tshirt,
    home,
    login,
    my_order_detail,
    my_orders,
    order_confirmation,
    register,
)
from users.serializers import EmailTokenObtainPairSerializer


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


urlpatterns = [
    path("", home, name="home"),
    path("login/", login, name="login_page"),
    path("register/", register, name="register_page"),
    path("registro/", register, name="registro"),
    path("cart/", cart, name="cart"),
    path("checkout/", checkout, name="checkout"),
    path("pedido/<str:order_number>/confirmacion/", order_confirmation, name="order-confirmation"),
    path("mis-pedidos/", my_orders, name="my-orders"),
    path("mis-pedidos/<int:pk>/", my_order_detail, name="my-order-detail"),
    path("backoffice/", backoffice_dashboard, name="backoffice-dashboard-page"),
    path("backoffice/orders/", backoffice_orders, name="backoffice-orders-page"),
    path("backoffice/orders/<int:pk>/", backoffice_order_detail, name="backoffice-order-detail-page"),
    path("backoffice/production/", backoffice_production, name="backoffice-production-page"),
    path("backoffice/products/", backoffice_products, name="backoffice-products-page"),
    path("backoffice/products/new/", backoffice_product_create, name="backoffice-product-create-page"),
    path("backoffice/products/<int:pk>/", backoffice_product_detail, name="backoffice-product-detail-page"),
    path("backoffice/stock/", backoffice_stock, name="backoffice-stock-page"),
    path("backoffice/customers/", backoffice_customers, name="backoffice-customers-page"),
    path("backoffice/customers/<int:pk>/", backoffice_customer_detail, name="backoffice-customer-detail-page"),
    path("crear-mi-remera/", create_tshirt, name="create-tshirt"),
    path("api/", api_home, name="api-home"),
    path("admin/", admin.site.urls),
    path("api/", include("products.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("users.urls")),
    path("api/", include("cart.urls")),
    path("api/", include("customizations.urls")),
    path(
        "api/auth/login/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"
    ),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
