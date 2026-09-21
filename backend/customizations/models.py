import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from products.models import Product, ProductVariant
from .storage import customization_storage


def customization_asset_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    prefix = 'private/' if instance.customization.private_assets else ''
    return f"{prefix}customizations/{instance.customization.user_id}/{instance.customization_id}/assets/{instance.id}.{extension}"


def customization_preview_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    prefix = 'private/' if instance.private_assets else ''
    return f"{prefix}customizations/{instance.user_id}/{instance.id}/previews/{uuid.uuid4()}.{extension}"


class Customization(models.Model):
    class State(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        IN_CART = "IN_CART", "En carrito"
        ORDERED = "ORDERED", "Comprada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customizations")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="customizations")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="customizations")
    configuration = models.JSONField(default=dict)
    preview_front = models.ImageField(upload_to=customization_preview_path, storage=customization_storage)
    preview_back = models.ImageField(upload_to=customization_preview_path, storage=customization_storage)
    private_assets = models.BooleanField(default=False)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT, db_index=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product} customization {self.id}"

    @property
    def is_frozen(self):
        return self.state == self.State.ORDERED or self.frozen_at is not None

    def freeze(self):
        self.state = self.State.ORDERED
        self.frozen_at = self.frozen_at or timezone.now()
        self.save(update_fields=["state", "frozen_at", "updated_at"])


class CustomizationAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customization = models.ForeignKey(Customization, on_delete=models.CASCADE, related_name="assets")
    file = models.ImageField(upload_to=customization_asset_path, storage=customization_storage)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=50)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    file_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name


class SavedDesign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_designs')
    customization = models.OneToOneField(Customization, on_delete=models.CASCADE, related_name='saved_design')
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']


def generated_image_path(instance, filename):
    return f'private/generated/{instance.user_id}/{instance.id}.png'


class GeneratedImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='generated_images')
    prompt = models.TextField(max_length=1000)
    provider = models.CharField(max_length=80)
    options = models.JSONField(default=dict)
    file = models.ImageField(upload_to=generated_image_path, storage=customization_storage)
    created_at = models.DateTimeField(auto_now_add=True)
