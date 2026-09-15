from users.backoffice import BackofficeAPIView
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from products.models import Product

from .models import Culture, DesignRecommendation
from .ordering import lock_cultures, write_positions
from .serializers import (
    CultureSerializer,
    CultureWriteSerializer,
    DesignRecommendationSerializer,
    DesignRecommendationWriteSerializer,
)


def active_cultures():
    return Culture.objects.filter(active=True)


class CultureListAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = CultureSerializer(active_cultures(), many=True)
        return Response(serializer.data)


class CultureDetailAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        culture = get_object_or_404(Culture, slug=slug, active=True)
        return Response(CultureSerializer(culture).data)


class DesignRecommendationListAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = DesignRecommendation.objects.filter(active=True, culture__active=True)
        culture = request.query_params.get("culture", "").strip()
        if culture:
            queryset = queryset.filter(culture__slug=culture)
        garment_type = request.query_params.get("garment_type", request.query_params.get("garment", "")).strip()
        if garment_type:
            if garment_type not in Product.GarmentType.values:
                raise serializers.ValidationError({"garment_type": "Prenda inválida."})
            queryset = queryset.filter(garment_type=garment_type)
        queryset = queryset.select_related("culture")
        serializer = DesignRecommendationSerializer(queryset, many=True, context={"request": request})
        return Response({"count": queryset.count(), "results": serializer.data})


class BackofficeCultureCollectionAPI(BackofficeAPIView):

    def get(self, request):
        serializer = CultureSerializer(Culture.objects.all(), many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        serializer = CultureWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BackofficeCultureDetailAPI(BackofficeAPIView):

    def get_object(self, pk):
        return get_object_or_404(Culture, pk=pk)

    def get(self, request, pk):
        return Response(CultureSerializer(self.get_object(pk)).data)

    @transaction.atomic
    def patch(self, request, pk):
        culture = self.get_object(pk)
        serializer = CultureWriteSerializer(culture, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        culture = serializer.save()
        return Response(CultureSerializer(culture).data)

    def delete(self, request, pk):
        culture = self.get_object(pk)
        culture.active = False
        culture.save(update_fields=["active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackofficeRecommendationCollectionAPI(BackofficeAPIView):

    def get(self, request):
        queryset = DesignRecommendation.objects.select_related("culture")
        culture = request.query_params.get("culture", "").strip()
        if culture:
            if not culture.isdecimal():
                raise serializers.ValidationError({"culture": "Cultura inválida."})
            queryset = queryset.filter(culture_id=culture)
        garment_type = request.query_params.get("garment_type", "").strip()
        if garment_type:
            if garment_type not in Product.GarmentType.values:
                raise serializers.ValidationError({"garment_type": "Prenda inválida."})
            queryset = queryset.filter(garment_type=garment_type)
        active = request.query_params.get("active", "")
        if active:
            if active not in {"true", "false"}:
                raise serializers.ValidationError({"active": "Estado inválido."})
            queryset = queryset.filter(active=active == "true")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        serializer = DesignRecommendationSerializer(queryset, many=True, context={"request": request})
        return Response({"count": queryset.count(), "results": serializer.data})

    @transaction.atomic
    def post(self, request):
        serializer = DesignRecommendationWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        recommendation = serializer.save()
        data = DesignRecommendationSerializer(DesignRecommendation.objects.select_related("culture").get(pk=recommendation.pk), context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)


class BackofficeRecommendationDetailAPI(BackofficeAPIView):

    def get_object(self, pk):
        return get_object_or_404(DesignRecommendation.objects.select_related("culture"), pk=pk)

    def get(self, request, pk):
        return Response(DesignRecommendationSerializer(self.get_object(pk), context={"request": request}).data)

    @transaction.atomic
    def patch(self, request, pk):
        recommendation = self.get_object(pk)
        serializer = DesignRecommendationWriteSerializer(recommendation, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        recommendation = serializer.save()
        return Response(DesignRecommendationSerializer(DesignRecommendation.objects.select_related("culture").get(pk=recommendation.pk), context={"request": request}).data)

    def delete(self, request, pk):
        recommendation = self.get_object(pk)
        recommendation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackofficeRecommendationReorderAPI(BackofficeAPIView):

    @transaction.atomic
    def post(self, request):
        ordered_ids = request.data.get("ordered_ids")
        expected = request.data.get('expected_order')
        culture_id = request.data.get('culture')
        if not isinstance(ordered_ids, list) or not ordered_ids or not isinstance(expected, list):
            raise serializers.ValidationError({"ordered_ids": "Enviá la lista de recomendaciones ordenadas."})
        if any(type(value) is not int or value < 1 for value in [culture_id, *ordered_ids, *expected]):
            raise serializers.ValidationError({'ordered_ids': 'Los IDs deben ser enteros positivos.'})
        if len(set(ordered_ids)) != len(ordered_ids) or len(set(expected)) != len(expected):
            raise serializers.ValidationError({'ordered_ids': 'No se permiten IDs repetidos.'})
        if not lock_cultures([culture_id]):
            raise serializers.ValidationError({'culture': 'La cultura no existe.'})
        items = list(DesignRecommendation.objects.select_for_update().filter(culture_id=culture_id).order_by('sort_order', 'pk'))
        current = [item.pk for item in items]
        if expected != current:
            return Response({'detail': 'La colección cambió en otra sesión. Recargamos el orden para que puedas volver a moverla.', 'code': 'order_conflict'}, status=409)
        if set(ordered_ids) != set(current):
            raise serializers.ValidationError({'ordered_ids': 'Enviá todas las recomendaciones de esta cultura, sin incluir otras culturas.'})
        by_id = {item.pk: item for item in items}
        write_positions(DesignRecommendation, [by_id[pk] for pk in ordered_ids])
        return Response({'culture': culture_id, 'ordered_ids': ordered_ids, 'positions': [{'id': pk, 'sort_order': index} for index, pk in enumerate(ordered_ids, 1)]})
