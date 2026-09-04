from django.urls import path

from .views import CustomizationCollectionAPI, CustomizationDetailAPI

urlpatterns = [
    path("customizations/", CustomizationCollectionAPI.as_view(), name="customization-list"),
    path("customizations/<uuid:pk>/", CustomizationDetailAPI.as_view(), name="customization-detail"),
]
