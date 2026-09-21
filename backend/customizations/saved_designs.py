"""Private library metadata backed by the existing editable Customization."""
import copy

from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .models import Customization, CustomizationAsset, SavedDesign
from .serializers import CustomizationWriteSerializer
from .storage import customization_storage, image_url, private_image_response


class SavedDesignSerializer(serializers.ModelSerializer):
    garment_type = serializers.CharField(source='customization.product.garment_type', read_only=True)
    preview_image = serializers.SerializerMethodField()
    customization_state = serializers.JSONField(source='customization.configuration', read_only=True)

    class Meta:
        model = SavedDesign
        fields = ['id', 'name', 'garment_type', 'preview_image', 'customization_state', 'created_at', 'updated_at']

    def get_preview_image(self, obj):
        return image_url(obj.customization, obj.customization.preview_front, side='front')


def owned_designs(user):
    return SavedDesign.objects.filter(user=user, customization__user=user).select_related('customization__product', 'customization__variant')


def write_saved_design(request, instance=None):
    name = serializers.CharField(max_length=120, allow_blank=False).run_validation(request.data.get('name'))
    writer = CustomizationWriteSerializer(instance.customization if instance else None, data=request.data, context={'request': request, 'saved_design': True})
    writer.is_valid(raise_exception=True)
    customization = writer.save(saved_design_name=name)
    return SavedDesign.objects.select_related('customization__product').get(customization=customization)


def duplicate_saved_design(source, user):
    files = []
    try:
        with transaction.atomic():
            source = owned_designs(user).select_for_update().get(pk=source.pk)
            original = Customization.objects.select_for_update().get(pk=source.customization_id)
            target = Customization(user=user, product=original.product, variant=original.variant, private_assets=True)
            for side in ('front', 'back'):
                with getattr(original, f'preview_{side}').open('rb') as stream:
                    getattr(target, f'preview_{side}').save(f'{side}.webp', ContentFile(stream.read()), save=False)
                files.append(getattr(target, f'preview_{side}').name)
            target.save()
            mapping = {}
            for asset in original.assets.all():
                duplicate = CustomizationAsset(customization=target, original_name=asset.original_name, mime_type=asset.mime_type, width=asset.width, height=asset.height, file_size=asset.file_size)
                with asset.file.open('rb') as stream:
                    duplicate.file.save(f'copy.{asset.file.name.rsplit(".", 1)[-1]}', ContentFile(stream.read()), save=True)
                files.append(duplicate.file.name)
                mapping[str(asset.pk)] = duplicate
            configuration = copy.deepcopy(original.configuration)
            for design in configuration['designs']:
                for id_key, url_key in [('assetId', 'assetUrl'), ('originalAssetId', 'originalAssetUrl')]:
                    if design.get(id_key):
                        asset = mapping[str(design[id_key])]
                        design[id_key] = str(asset.pk)
                        design[url_key] = image_url(target, asset.file, asset_id=asset.pk)
            target.configuration = configuration
            target.save(update_fields=['configuration'])
            return SavedDesign.objects.create(user=user, customization=target, name=f'{source.name[:112]} (copia)')
    except Exception:
        for name in files:
            customization_storage.delete(name)
        raise


class SavedDesignCollectionAPI(APIView):
    def get(self, request):
        class CardSerializer(SavedDesignSerializer):
            class Meta(SavedDesignSerializer.Meta):
                fields = [field for field in SavedDesignSerializer.Meta.fields if field != 'customization_state']
        paginator = PageNumberPagination()
        paginator.page_size = 24
        queryset = owned_designs(request.user).defer('customization__configuration')
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(CardSerializer(page, many=True).data)

    def post(self, request):
        design = write_saved_design(request)
        return Response(SavedDesignSerializer(design).data, status=status.HTTP_201_CREATED)


class SavedDesignDetailAPI(APIView):
    def get(self, request, pk):
        return Response(SavedDesignSerializer(get_object_or_404(owned_designs(request.user), pk=pk)).data)

    def patch(self, request, pk):
        design = get_object_or_404(owned_designs(request.user), pk=pk)
        if 'configuration' not in request.data:
            serializer = SavedDesignSerializer(design, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(SavedDesignSerializer(write_saved_design(request, design)).data)

    def delete(self, request, pk):
        with transaction.atomic():
            design = get_object_or_404(owned_designs(request.user).select_for_update(), pk=pk)
            design.customization.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedDesignDuplicateAPI(APIView):
    def post(self, request, pk):
        design = get_object_or_404(owned_designs(request.user), pk=pk)
        return Response(SavedDesignSerializer(duplicate_saved_design(design, request.user)).data, status=201)


class CustomizationImageAPI(APIView):
    def get(self, request, pk, asset_id=None, side=None):
        customization = get_object_or_404(Customization, pk=pk, user=request.user)
        if asset_id:
            asset = get_object_or_404(customization.assets, pk=asset_id)
            field, mime = asset.file, asset.mime_type
        else:
            if side not in {'front', 'back'}:
                return Response(status=404)
            field, mime = getattr(customization, f'preview_{side}'), 'image/webp'
        return private_image_response(field, mime)
