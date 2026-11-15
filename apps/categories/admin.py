from django.contrib import admin

from .models import Category, SubCategory


class SubCategoryInline(admin.TabularInline):
    model = SubCategory
    extra = 0
    fields = ["name", "slug", "display_order", "is_active"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "display_order", "is_active", "show_on_homepage"]
    list_editable = ["display_order", "is_active"]
    search_fields = ["name"]
    inlines = [SubCategoryInline]


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "display_order", "is_active"]
    list_filter = ["category"]
