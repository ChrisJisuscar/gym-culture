from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Order
from .serializers import OrderSerializer


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Order.objects.select_related("user").prefetch_related(
            "items__product", "items__variant"
        )
        if self.request.user.role == self.request.user.Role.ADMIN:
            return queryset
        return queryset.filter(user=self.request.user)
