from django.urls import path

from .views import (
    MockPaymentOutcomeAPI,
    OrderPaymentsAPI,
    PaymentDetailAPI,
    PaymentWebhookAPI,
)

urlpatterns = [
    path("orders/<int:order_id>/payments/", OrderPaymentsAPI.as_view(), name="order-payments"),
    path("payments/<uuid:payment_id>/", PaymentDetailAPI.as_view(), name="payment-detail"),
    path("payments/<uuid:payment_id>/mock/", MockPaymentOutcomeAPI.as_view(), name="mock-payment-outcome"),
    path("payments/webhook/<str:provider>/", PaymentWebhookAPI.as_view(), name="payment-webhook"),
]
