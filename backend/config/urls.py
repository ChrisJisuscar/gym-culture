from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import api_home, create_tshirt, home


urlpatterns = [
    path('', home, name='home'),
    path('crear-mi-remera/', create_tshirt, name='create-tshirt'),
    path('api/', api_home, name='api-home'),

    path('admin/', admin.site.urls),

    path('api/', include('products.urls')),
    path('api/', include('users.urls')),

    path(
        'api/auth/login/',
        TokenObtainPairView.as_view(),
        name='token_obtain_pair'
    ),

    path(
        'api/auth/refresh/',
        TokenRefreshView.as_view(),
        name='token_refresh'
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
