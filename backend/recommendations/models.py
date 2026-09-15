from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from uuid import uuid4

from products.models import Product


def recommendation_preview_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"recommendations/{instance.culture.slug}/previews/{uuid4().hex}.{extension}"


def recommendation_asset_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"recommendations/{instance.culture.slug}/assets/{uuid4().hex}.{extension}"


class Culture(models.Model):
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="cultures/", blank=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class DesignRecommendation(models.Model):
    BASE_COLORS = {"Negro": "#111015", "Blanco": "#ebe9e4", "Gris": "#7a7780", "Azul": "#244a8f", "Rojo": "#9f233d", "Verde": "#276749"}
    name = models.CharField(max_length=150)
    seed_key = models.CharField(max_length=80, unique=True, null=True, blank=True, editable=False)
    customization_state = models.JSONField(default=dict, blank=True)
    culture = models.ForeignKey(Culture, on_delete=models.CASCADE, related_name="recommendations")
    garment_type = models.CharField(max_length=16, choices=Product.GarmentType.choices)
    base_color = models.CharField(max_length=16, choices=[(name, name) for name in BASE_COLORS], default="Negro")
    preview_image = models.ImageField(upload_to=recommendation_preview_path)
    design_asset = models.ImageField(upload_to=recommendation_asset_path, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    featured = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveIntegerField(default=0, editable=False)
    default_position = models.JSONField(default=dict, blank=True)
    default_scale = models.FloatField(default=1.0, validators=[MinValueValidator(0.35), MaxValueValidator(2.5)])
    default_rotation = models.FloatField(default=0.0, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-featured", "id"]
        constraints = [models.UniqueConstraint(fields=['culture', 'sort_order'], name='unique_recommendation_position_in_culture')]
        indexes = [
            models.Index(fields=["culture", "garment_type", "active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from .ordering import lock_cultures, next_position, write_positions
        with transaction.atomic():
            previous = None if self._state.adding else type(self).objects.filter(pk=self.pk).values('culture_id', 'sort_order').first()
            lock_cultures({self.culture_id, *([previous['culture_id']] if previous else [])})
            if previous:
                current = type(self).objects.select_for_update().get(pk=self.pk)
                if current.culture_id != previous['culture_id']:
                    raise ValidationError('La cultura cambió en otra sesión. Recargá antes de guardar.')
                self.sort_order = current.sort_order if current.culture_id == self.culture_id else next_position(type(self), self.culture_id)
            else:
                self.sort_order = next_position(type(self), self.culture_id)
            if kwargs.get('update_fields') and previous and previous['culture_id'] != self.culture_id:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'sort_order', 'culture'}
            super().save(*args, **kwargs)
            if previous and previous['culture_id'] != self.culture_id:
                remaining = list(type(self).objects.select_for_update().filter(culture_id=previous['culture_id']).order_by('sort_order', 'pk'))
                write_positions(type(self), remaining)

    def delete(self, *args, **kwargs):
        from .ordering import lock_cultures, write_positions
        with transaction.atomic():
            lock_cultures([self.culture_id])
            result = super().delete(*args, **kwargs)
            write_positions(type(self), list(type(self).objects.select_for_update().filter(culture_id=self.culture_id).order_by('sort_order', 'pk')))
            return result


def recommendation_layer_path(instance, filename):
    extension = filename.rsplit('.', 1)[-1].lower()
    return f"recommendations/{instance.recommendation_id}/layers/{instance.id}.{extension}"


class RecommendationAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    recommendation = models.ForeignKey(DesignRecommendation, on_delete=models.CASCADE, related_name='assets')
    file = models.ImageField(upload_to=recommendation_layer_path)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=50)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    file_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
