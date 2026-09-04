import json

from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from customizations.validators import validate_uploaded_image
from users.permissions import IsAdminRole

from .constants import LOW_STOCK_THRESHOLD
from .models import Category, Product, ProductImage, ProductVariant, StockMovement
from .serializers import (
    AdminProductSerializer,
    AdminProductWriteSerializer,
    CategorySerializer,
    ProductSerializer,
    StockAdjustmentSerializer,
    StockMovementSerializer,
    StockVariantSerializer,
)
from .services import adjust_stock


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(active=True)
    serializer_class = CategorySerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method in ("GET", "HEAD", "OPTIONS") else [IsAdminRole()]

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        category.active = False
        category.save(update_fields=["active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(active=True).select_related("category").prefetch_related(
        Prefetch("variants", queryset=ProductVariant.objects.filter(active=True)), "images"
    )
    serializer_class = ProductSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method in ("GET", "HEAD", "OPTIONS") else [IsAdminRole()]

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        product.active = False
        product.save(update_fields=["active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackofficePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def product_queryset():
    return Product.objects.select_related("category").prefetch_related("variants", "images").annotate(
        variant_count=Count("variants", distinct=True),
        total_stock=Coalesce(Sum("variants__stock", filter=Q(variants__active=True)), 0),
    )


def prepared_product_data(data):
    prepared = {key: data.get(key) for key in ("name", "description", "price", "category", "active") if key in data}
    variants = data.get("variants")
    if isinstance(variants, str):
        try:
            variants = json.loads(variants)
        except ValueError as exc:
            raise serializers.ValidationError({"variants": "La lista de variantes no contiene JSON válido."}) from exc
    if variants is not None:
        prepared["variants"] = variants
    return prepared


def save_uploaded_images(request, product):
    uploads = request.FILES.getlist("images")
    if len(uploads) > 10:
        raise serializers.ValidationError({"images": "Se permiten como máximo 10 imágenes por operación."})
    for upload in uploads:
        validate_uploaded_image(upload, "images")
    has_main = product.images.filter(is_main=True).exists()
    for index, upload in enumerate(uploads):
        ProductImage.objects.create(product=product, image=upload, is_main=not has_main and index == 0)


class BackofficeProductsAPI(APIView):
    permission_classes = [IsAdminRole]
    pagination_class = BackofficePagination

    def get(self, request):
        queryset = product_queryset().order_by("name", "id")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        active = request.query_params.get("active")
        if active in {"true", "false"}:
            queryset = queryset.filter(active=active == "true")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AdminProductSerializer(page, many=True, context={"request": request}).data)

    @transaction.atomic
    def post(self, request):
        serializer = AdminProductWriteSerializer(data=prepared_product_data(request.data), context={"request": request})
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        save_uploaded_images(request, product)
        return Response(AdminProductSerializer(product_queryset().get(pk=product.pk), context={"request": request}).data, status=status.HTTP_201_CREATED)


class BackofficeProductDetailAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, pk):
        product = get_object_or_404(product_queryset(), pk=pk)
        return Response(AdminProductSerializer(product, context={"request": request}).data)

    @transaction.atomic
    def patch(self, request, pk):
        product = get_object_or_404(Product.objects.select_for_update(), pk=pk)
        serializer = AdminProductWriteSerializer(product, data=prepared_product_data(request.data), partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        save_uploaded_images(request, product)
        return Response(AdminProductSerializer(product_queryset().get(pk=product.pk), context={"request": request}).data)


class BackofficeProductImageAPI(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request, pk):
        product = get_object_or_404(Product.objects.select_for_update(), pk=pk)
        upload = request.FILES.get("image")
        if not upload:
            raise serializers.ValidationError({"image": "Seleccioná una imagen."})
        validate_uploaded_image(upload, "image")
        is_main = str(request.data.get("is_main", "false")).lower() == "true"
        if is_main:
            product.images.update(is_main=False)
        ProductImage.objects.create(
            product=product,
            image=upload,
            is_main=is_main or not product.images.exists(),
        )
        return Response(AdminProductSerializer(product_queryset().get(pk=product.pk), context={"request": request}).data, status=status.HTTP_201_CREATED)


class BackofficeProductImageDetailAPI(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def delete(self, request, pk, image_id):
        product = get_object_or_404(Product.objects.select_for_update(), pk=pk)
        image = get_object_or_404(ProductImage, pk=image_id, product=product)
        was_main = image.is_main
        image.delete()
        if was_main:
            replacement = product.images.order_by("id").first()
            if replacement:
                replacement.is_main = True
                replacement.save(update_fields=["is_main"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackofficeCategoriesAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response(CategorySerializer(Category.objects.order_by("name"), many=True).data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BackofficeStockAPI(APIView):
    permission_classes = [IsAdminRole]
    pagination_class = BackofficePagination

    def get(self, request):
        queryset = ProductVariant.objects.select_related("product").order_by("product__name", "color", "size")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(product__name__icontains=search) | Q(color__icontains=search) | Q(size__icontains=search))
        stock_filter = request.query_params.get("stock")
        if stock_filter == "low":
            queryset = queryset.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)
        elif stock_filter == "out":
            queryset = queryset.filter(stock=0)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(StockVariantSerializer(page, many=True).data)


class BackofficeStockAdjustAPI(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, variant_id):
        variant = get_object_or_404(ProductVariant, pk=variant_id)
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = adjust_stock(variant=variant, performed_by=request.user, **serializer.validated_data)
        return Response(StockMovementSerializer(movement).data)


class BackofficeStockHistoryAPI(APIView):
    permission_classes = [IsAdminRole]
    pagination_class = BackofficePagination

    def get(self, request):
        queryset = StockMovement.objects.select_related("variant__product", "performed_by")
        variant_id = request.query_params.get("variant")
        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(StockMovementSerializer(page, many=True).data)
