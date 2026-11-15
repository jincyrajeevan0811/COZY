from django.contrib import admin

from .models import AccessPermission, Address, Role, User, UserProfile


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Users are created via the storefront, `createsuperuser` or the COZY dashboard."""

    ordering = ["-date_joined"]
    list_display = ["email", "first_name", "last_name", "role", "is_active", "email_verified", "date_joined"]
    list_filter = ["role", "is_active", "email_verified", "is_staff"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email",)}),
        ("Personal", {"fields": ("first_name", "last_name", "phone")}),
        ("Access", {"fields": ("role", "is_active", "is_staff", "is_superuser", "email_verified")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ["last_login", "date_joined"]

    def has_add_permission(self, request):
        return False


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_staff_role", "is_system"]
    filter_horizontal = ["permissions"]
    prepopulated_fields = {"slug": ("name",)}


admin.site.register(AccessPermission)
admin.site.register(UserProfile)
admin.site.register(Address)
