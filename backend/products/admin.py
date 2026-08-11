from django.contrib import admin
from .models import Category, Product, ProductVariant, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'active')
    list_filter = ('active',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'active', 'created_at')
    list_filter = ('category', 'active')
    search_fields = ('name', 'description')

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'size', 'color', 'stock')
    list_filter = ('size', 'color')
    search_fields = ('product__name', 'color')

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_main', 'created_at')
    list_filter = ('is_main',)