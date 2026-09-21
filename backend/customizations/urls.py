from django.urls import path

from .views import CustomizationCollectionAPI, CustomizationDetailAPI, BackgroundRemovalAPI
from .saved_designs import SavedDesignCollectionAPI, SavedDesignDetailAPI, SavedDesignDuplicateAPI, CustomizationImageAPI
from .generation_views import EditorConfigAPI, ImageGenerationAPI, GeneratedImageAPI

urlpatterns = [
    path('customizations/editor-config/', EditorConfigAPI.as_view(), name='editor-config'),
    path('customizations/generate-image/', ImageGenerationAPI.as_view(), name='generate-image'),
    path('customizations/generated/<uuid:pk>/', GeneratedImageAPI.as_view(), name='generated-image'),
    path('saved-designs/', SavedDesignCollectionAPI.as_view(), name='saved-design-list'),
    path('saved-designs/<uuid:pk>/', SavedDesignDetailAPI.as_view(), name='saved-design-detail'),
    path('saved-designs/<uuid:pk>/duplicate/', SavedDesignDuplicateAPI.as_view(), name='saved-design-duplicate'),
    path('customizations/<uuid:pk>/assets/<uuid:asset_id>/', CustomizationImageAPI.as_view(), name='customization-asset'),
    path('customizations/<uuid:pk>/previews/<str:side>/', CustomizationImageAPI.as_view(), name='customization-preview'),
    path("customizations/remove-background/", BackgroundRemovalAPI.as_view(), name="background-removal"),
    path("customizations/", CustomizationCollectionAPI.as_view(), name="customization-list"),
    path("customizations/<uuid:pk>/", CustomizationDetailAPI.as_view(), name="customization-detail"),
]
