from django.contrib import admin

from .models import Product, ProductAttribute, ProductImage, ProductVariant


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "category", "price", "is_active", "is_featured", "sold_count"]
    list_filter = ["is_active", "category", "is_featured", "is_trending", "is_bestseller", "is_new_arrival"]
    search_fields = ["name", "sku", "tags"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariantInline]


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ["attr_type", "value", "color_code", "display_order"]
    list_filter = ["attr_type"]
