from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework_simplejwt.views import TokenRefreshView

from users.serializers import EmailTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .views import api_home, cart, create_tshirt, home, login, register


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer

urlpatterns = [
    path("", home, name="home"),
    path("login/", login, name="login_page"),
    path("register/", register, name="register_page"),
    path("registro/", register, name="registro"),
    path("cart/", cart, name="cart"),
    path("crear-mi-remera/", create_tshirt, name="create-tshirt"),
    path("api/", api_home, name="api-home"),
    path("admin/", admin.site.urls),
    path("api/", include("products.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("users.urls")),
    path("api/", include("cart.urls")),
    path("api/auth/login/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
