from django.urls import path

from .views import (
    BackofficeCultureCollectionAPI,
    BackofficeCultureDetailAPI,
    BackofficeRecommendationCollectionAPI,
    BackofficeRecommendationDetailAPI,
    BackofficeRecommendationReorderAPI,
    CultureDetailAPI,
    CultureListAPI,
    DesignRecommendationListAPI,
)

urlpatterns = [
    path("design-recommendations/", DesignRecommendationListAPI.as_view(), name="design-recommendation-list"),
    path("recommendations/cultures/", CultureListAPI.as_view(), name="recommendation-cultures"),
    path("recommendations/cultures/<slug:slug>/", CultureDetailAPI.as_view(), name="recommendation-culture-detail"),
    path("recommendations/", DesignRecommendationListAPI.as_view(), name="recommendation-list"),
    path("backoffice/recommendations/cultures/", BackofficeCultureCollectionAPI.as_view(), name="backoffice-cultures"),
    path("backoffice/recommendations/cultures/<int:pk>/", BackofficeCultureDetailAPI.as_view(), name="backoffice-culture-detail"),
    path("backoffice/recommendations/reorder/", BackofficeRecommendationReorderAPI.as_view(), name="backoffice-recommendation-reorder"),
    path("backoffice/recommendations/", BackofficeRecommendationCollectionAPI.as_view(), name="backoffice-recommendations"),
    path("backoffice/recommendations/<int:pk>/", BackofficeRecommendationDetailAPI.as_view(), name="backoffice-recommendation-detail"),
]
