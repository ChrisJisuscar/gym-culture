from datetime import date

from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from customizations.models import CustomizationAsset
from users.permissions import IsAdminRole

from .models import Order
from .serializers import (
    AdminOrderSerializer,
    BackofficeOrderListSerializer,
    CheckoutSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
)
from .services import create_order_from_cart, transition_order_status


def order_detail_queryset():
    return Order.objects.select_related("user").prefetch_related(
        "items__product",
        "items__variant",
        "items__customization",
        "status_history__changed_by",
    )


class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = order_detail_queryset()
        if self.request.user.role == self.request.user.Role.ADMIN or self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def get_serializer_class(self):
        return OrderSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().annotate(item_count=Count("items"))
        return Response(OrderSerializer(queryset, many=True, context={"request": request}).data)

    def create(self, request, *args, **kwargs):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, created = create_order_from_cart(user=request.user, checkout_data=serializer.validated_data)
        response = OrderSerializer(order_detail_queryset().get(pk=order.pk), context={"request": request})
        return Response(response.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderByNumberAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number):
        queryset = order_detail_queryset()
        if not (request.user.role == request.user.Role.ADMIN or request.user.is_staff):
            queryset = queryset.filter(user=request.user)
        order = get_object_or_404(queryset, order_number=order_number)
        return Response(OrderSerializer(order, context={"request": request}).data)


class BackofficePagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100


class BackofficeDashboardAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        counts = dict(Order.objects.values_list("status").annotate(total=Count("id")))
        recent = Order.objects.select_related("user").annotate(item_count=Count("items"))[:8]
        return Response({
            "counts": {
                "pending": counts.get(Order.Status.PENDING, 0),
                "confirmed": counts.get(Order.Status.CONFIRMED, 0),
                "preparing": counts.get(Order.Status.PREPARING, 0),
                "shipped": counts.get(Order.Status.SHIPPED, 0),
            },
            "recent_orders": BackofficeOrderListSerializer(recent, many=True).data,
        })


class BackofficeOrdersAPI(APIView):
    permission_classes = [IsAdminRole]
    pagination_class = BackofficePagination

    def get(self, request):
        queryset = Order.objects.select_related("user").annotate(item_count=Count("items")).order_by("-created_at")
        status_filter = request.query_params.get("status", "").upper()
        if status_filter:
            if status_filter not in Order.Status.values:
                return Response({"status": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(status=status_filter)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search)
                | Q(contact_first_name__icontains=search)
                | Q(contact_last_name__icontains=search)
                | Q(contact_email__icontains=search)
            )
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        try:
            if date_from:
                queryset = queryset.filter(created_at__date__gte=date.fromisoformat(date_from))
            if date_to:
                queryset = queryset.filter(created_at__date__lte=date.fromisoformat(date_to))
        except ValueError:
            return Response({"date": "La fecha debe usar el formato YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = BackofficeOrderListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class BackofficeOrderDetailAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, pk):
        order = get_object_or_404(order_detail_queryset(), pk=pk)
        data = AdminOrderSerializer(order, context={"request": request}).data
        items_by_id = {item.id: item for item in order.items.all()}
        for serialized_item in data["items"]:
            item = items_by_id[serialized_item["id"]]
            snapshot = item.customization_snapshot or {}
            serialized_item["production_assets"] = [
                {
                    "id": asset.get("id"),
                    "original_name": asset.get("originalName"),
                    "mime_type": asset.get("mimeType"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "file_size": asset.get("fileSize"),
                    "download_url": f"/api/backoffice/assets/{asset.get('id')}/download/",
                }
                for asset in snapshot.get("assets", [])
            ]
        return Response(data)


class BackofficeOrderStatusAPI(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = transition_order_status(order=order, new_status=serializer.validated_data["status"], changed_by=request.user)
        return Response(AdminOrderSerializer(order_detail_queryset().get(pk=order.pk), context={"request": request}).data)


class BackofficeProductionAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        orders = order_detail_queryset().filter(
            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING],
            items__customization_snapshot__isnull=False,
        ).distinct()
        return Response(AdminOrderSerializer(orders, many=True, context={"request": request}).data)


class BackofficeAssetDownloadAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, asset_id):
        asset = get_object_or_404(
            CustomizationAsset.objects.filter(customization__order_items__isnull=False).distinct(),
            pk=asset_id,
        )
        return FileResponse(asset.file.open("rb"), as_attachment=True, filename=asset.original_name)
