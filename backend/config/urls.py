from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.permissions import AllowAny
from .views import home

from rest_framework_simplejwt.views import (
    TokenRefreshView,
)


urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),

    path('api/', include('products.urls')),
    path('api/', include('users.urls')),

    path(
        'api/auth/refresh/',
        TokenRefreshView.as_view(permission_classes=[AllowAny]),
        name='token_refresh'
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
