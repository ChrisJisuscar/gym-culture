from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Customization, CustomizationAsset


@receiver(post_delete, sender=CustomizationAsset)
def delete_asset_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=Customization)
def delete_preview_files(sender, instance, **kwargs):
    if instance.preview_front:
        instance.preview_front.delete(save=False)
    if instance.preview_back:
        instance.preview_back.delete(save=False)
