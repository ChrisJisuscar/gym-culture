from django.urls import path

from .views import CustomizationCollectionAPI, CustomizationDetailAPI, BackgroundRemovalAPI

urlpatterns = [
    path("customizations/remove-background/", BackgroundRemovalAPI.as_view(), name="background-removal"),
    path("customizations/", CustomizationCollectionAPI.as_view(), name="customization-list"),
    path("customizations/<uuid:pk>/", CustomizationDetailAPI.as_view(), name="customization-detail"),
]
