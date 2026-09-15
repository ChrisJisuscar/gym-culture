from django.contrib import admin

from .models import Culture, DesignRecommendation

@admin.register(Culture)
class CultureAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tagline", "active", "sort_order")
    list_editable = ("active", "sort_order")
    search_fields = ("name", "slug", "tagline")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(DesignRecommendation)
class DesignRecommendationAdmin(admin.ModelAdmin):
    list_display = ("name", "culture", "garment_type", "featured", "active", "sort_order")
    list_filter = ("culture", "garment_type", "active", "featured")
    list_editable = ("featured", "active")
    readonly_fields = ("sort_order",)
    search_fields = ("name",)
    autocomplete_fields = ("culture",)
    fieldsets = (
        (None, {"fields": ("name", "culture", "garment_type", "base_color", "active", "featured", "sort_order")}),
        ("Archivos", {"fields": ("preview_image", "design_asset")}),
        ("Posicionamiento por defecto", {"fields": ("default_position", "default_scale", "default_rotation"), "classes": ("collapse",)}),
    )
