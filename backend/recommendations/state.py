"""Persist the Custom Lab v1 schema with recommendation-owned assets."""
import copy
from pathlib import Path

from django.db import transaction
from django.core.files.storage import default_storage
from customizations.validators import validate_uploaded_image
from customizations.print_quality import enrich_print_quality
from .models import DesignRecommendation, RecommendationAsset
from .ordering import lock_cultures


def save_recommendation_state(instance, data, files):
    saved_files = []
    obsolete = []
    configuration = copy.deepcopy(data.pop('customization_state'))
    try:
        with transaction.atomic():
            lock_cultures({*([instance.culture_id] if instance else []), *([data['culture'].id] if data.get('culture') else [])})
            if instance:
                instance = DesignRecommendation.objects.select_for_update().get(pk=instance.pk)
                if 'preview_image' in data and instance.preview_image:
                    obsolete.append(instance.preview_image.name)
                for key, value in data.items():
                    setattr(instance, key, value)
            else:
                instance = DesignRecommendation(**data)
            preview_changed = not instance.preview_image._committed
            instance.save()
            if preview_changed:
                saved_files.append(instance.preview_image.name)
            uploaded = {}
            for key, upload in files.items():
                if not key.startswith('asset_'):
                    continue
                info = validate_uploaded_image(upload, key)
                asset = RecommendationAsset(recommendation=instance, original_name=Path(upload.name).name[:255], mime_type=upload.content_type, width=info['width'], height=info['height'], file_size=upload.size)
                asset.file.save(f"design.{info['extension']}", upload, save=True)
                saved_files.append(asset.file.name)
                uploaded[key.removeprefix('asset_')] = asset
            assets = {str(asset.pk): asset for asset in instance.assets.all()}
            used = set()
            for design in configuration['designs']:
                if design['type'] != 'image':
                    continue
                for key, id_key, url_key in (('assetKey', 'assetId', 'assetUrl'), ('originalAssetKey', 'originalAssetId', 'originalAssetUrl')):
                    upload_key = design.pop(key, None)
                    if upload_key:
                        design[id_key] = str(uploaded[upload_key].id)
                    asset_id = design.get(id_key)
                    if asset_id:
                        design[url_key] = assets[str(asset_id)].file.url
                        used.add(str(asset_id))
                    else:
                        design.pop(url_key, None)
            garment = configuration['garment']
            for design in configuration['designs']:
                if design['type'] == 'image':
                    asset = assets[str(design['assetId'])]
                    original = assets[str(design.get('originalAssetId', design['assetId']))]
                    design.update(imageWidth=asset.width, imageHeight=asset.height, originalWidth=original.width, originalHeight=original.height)
            enrich_print_quality(configuration)
            instance.garment_type = garment['type']
            if garment['color'] in instance.BASE_COLORS:
                instance.base_color = garment['color']
            instance.customization_state = configuration
            instance.save()
            stale = instance.assets.exclude(pk__in=used)
            obsolete.extend(stale.values_list('file', flat=True))
            stale.delete()
            transaction.on_commit(lambda: [default_storage.delete(name) for name in obsolete if name])
            return instance
    except Exception:
        for name in saved_files:
            default_storage.delete(name)
        raise
