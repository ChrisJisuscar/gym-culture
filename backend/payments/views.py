from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order

from .models import Payment
from .providers import get_payment_provider
from .providers.mock import MockPaymentProvider
from .serializers import CreatePaymentSerializer, MockOutcomeSerializer, PaymentSerializer
from .services import PaymentService


def payments_for_user(user):
    queryset = Payment.objects.select_related("order")
    if user.is_staff or user.role == user.Role.ADMIN:
        return queryset
    return queryset.filter(order__user=user)


class OrderPaymentsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get_order(self, request, order_id):
        queryset = Order.objects.all()
        if not (request.user.is_staff or request.user.role == request.user.Role.ADMIN):
            queryset = queryset.filter(user=request.user)
        return get_object_or_404(queryset, pk=order_id)

    def get(self, request, order_id):
        order = self.get_order(request, order_id)
        payments = order.payments.all()
        return Response(PaymentSerializer(payments, many=True).data)

    def post(self, request, order_id):
        order = self.get_order(request, order_id)
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider_name = serializer.validated_data.get("provider") or settings.PAYMENT_PROVIDER
        payment = PaymentService().create_payment(
            order=order, provider_name=provider_name
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        payment = get_object_or_404(payments_for_user(request.user), pk=payment_id)
        return Response(PaymentSerializer(payment).data)


class PaymentWebhookAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, provider):
        if provider.lower() == "mock" and not settings.DEBUG:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payment_provider = get_payment_provider(provider.lower())
        payload = payment_provider.parse_webhook(request)
        payment, processed = PaymentService().process_event(
            provider_name=payment_provider.name, payload=payload
        )
        return Response({"received": True, "processed": processed, "payment_id": payment.id})


class MockPaymentOutcomeAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, payment_id):
        if not settings.DEBUG:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payment = get_object_or_404(payments_for_user(request.user), pk=payment_id, provider="mock")
        serializer = MockOutcomeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = MockPaymentProvider()
        payload = provider.build_event(payment, serializer.validated_data["outcome"])
        payment, _ = PaymentService().process_event(provider_name=provider.name, payload=payload)
        return Response(PaymentSerializer(payment).data)
