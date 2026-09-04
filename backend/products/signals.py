from django.db.models.signals import post_delete
from django.db import transaction
from django.dispatch import receiver

from .models import ProductImage


@receiver(post_delete, sender=ProductImage)
def delete_product_image_file(sender, instance, **kwargs):
    if instance.image:
        storage = instance.image.storage
        name = instance.image.name
        transaction.on_commit(lambda: storage.delete(name))
