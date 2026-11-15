from django import forms
from django.contrib.auth import password_validation
from django.forms import inlineformset_factory

from apps.accounts.models import AccessPermission, Role, User
from apps.categories.models import Category, SubCategory
from apps.core.forms import StyledFormMixin
from apps.coupons.models import Coupon
from apps.inventory.models import StockHistory
from apps.orders.models import Order
from apps.products.models import Product, ProductAttribute, ProductImage, ProductVariant
from apps.reviews.forms import MultipleImageField
from apps.shipping.models import ServiceablePincode, Shipment, ShippingMethod, ShippingProvider
from apps.support.models import SupportTicket
from apps.website_settings.models import (
    FAQ, Banner, BlogPost, HomeSection, InstagramPost, NewsletterSubscriber, StaticPage, Testimonial, WebsiteSetting,
)

DATETIME_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
DATE_WIDGET = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
class ProductForm(StyledFormMixin, forms.ModelForm):
    initial_stock = forms.IntegerField(min_value=0, required=False, initial=0,
                                       help_text="Opening stock for products without variants (new products only).")
    upload_images = MultipleImageField(required=False, label="Upload images (multiple)")

    class Meta:
        model = Product
        fields = [
            "name", "sku", "category", "subcategory", "short_description", "description",
            "price", "original_price", "color", "material", "style", "size_info", "weight_grams", "care_instructions",
            "has_variants", "is_returnable", "return_days",
            "is_active", "is_featured", "is_trending", "is_bestseller", "is_new_arrival", "tags",
            "meta_title", "meta_description", "meta_keywords",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "care_instructions": forms.Textarea(attrs={"rows": 3}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subcategory"].queryset = SubCategory.objects.select_related("category")
        if self.instance.pk:
            self.fields.pop("initial_stock")

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        if Product.objects.filter(sku__iexact=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A product with this SKU already exists.")
        return sku


class ProductImageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary", "display_order"]


class ProductVariantForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["name", "sku", "color", "size", "price", "original_price", "is_active", "display_order"]


ProductImageFormSet = inlineformset_factory(Product, ProductImage, form=ProductImageForm, extra=0, can_delete=True)
ProductVariantFormSet = inlineformset_factory(Product, ProductVariant, form=ProductVariantForm, extra=1, can_delete=True)


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "image", "banner_image", "display_order", "is_active", "show_on_homepage",
                  "show_in_menu", "meta_title", "meta_description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class SubCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = ["category", "name", "description", "image", "display_order", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class AttributeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductAttribute
        fields = ["attr_type", "value", "color_code", "display_order"]
        widgets = {"color_code": forms.TextInput(attrs={"type": "color"})}


class BulkProductUploadForm(StyledFormMixin, forms.Form):
    file = forms.FileField(help_text="CSV or Excel (.xlsx) using the template columns.")
    update_existing = forms.BooleanField(required=False, initial=True, label="Update products whose SKU already exists")

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not (name.endswith(".csv") or name.endswith(".xlsx")):
            raise forms.ValidationError("Upload a .csv or .xlsx file.")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File must be smaller than 5 MB.")
        return f


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
class StockAdjustForm(StyledFormMixin, forms.Form):
    MODE_CHOICES = [
        ("in", "Stock in (add)"),
        ("out", "Stock out (remove)"),
        ("set", "Set exact quantity (stock count)"),
    ]
    mode = forms.ChoiceField(choices=MODE_CHOICES)
    quantity = forms.IntegerField(min_value=0)
    low_stock_threshold = forms.IntegerField(min_value=0, required=False)
    reference = forms.CharField(max_length=100, required=False, help_text="Supplier invoice, PO number…")
    note = forms.CharField(max_length=255, required=False)


class StockHistoryFilterForm(forms.Form):
    movement_type = forms.ChoiceField(choices=[("", "All movements")] + StockHistory.TYPE_CHOICES, required=False)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
class OrderStatusForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(choices=[])
    note = forms.CharField(max_length=255, required=False)
    notify_customer = forms.BooleanField(required=False, initial=True)

    def __init__(self, order, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = dict(Order.STATUS_CHOICES)
        self.fields["status"].choices = [(s, labels[s]) for s in order.allowed_next_statuses]


class ShipmentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Shipment
        fields = ["provider", "tracking_number", "estimated_delivery", "notes"]
        widgets = {"estimated_delivery": DATE_WIDGET, "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"].queryset = ShippingProvider.objects.filter(is_active=True)


class AdminNoteForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = ["admin_note"]
        widgets = {"admin_note": forms.Textarea(attrs={"rows": 3})}


class ReturnActionForm(StyledFormMixin, forms.Form):
    action = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject"), ("receive", "Mark item received")])
    note = forms.CharField(max_length=255, required=False)
    refund_amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)


class RefundProcessForm(StyledFormMixin, forms.Form):
    use_gateway = forms.BooleanField(required=False, initial=True, label="Refund through Razorpay (online payments)")
    reference = forms.CharField(max_length=120, required=False, help_text="UPI / bank reference for manual refunds")


# ---------------------------------------------------------------------------
# Marketing & content
# ---------------------------------------------------------------------------
class CouponForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ["code", "description", "discount_type", "value", "max_discount", "min_order_value", "scope",
                  "categories", "products", "first_order_only", "usage_limit", "per_user_limit", "valid_from",
                  "valid_to", "campaign", "is_public", "is_active"]
        widgets = {"valid_from": DATETIME_WIDGET, "valid_to": DATETIME_WIDGET,
                   "categories": forms.SelectMultiple(attrs={"size": 6}),
                   "products": forms.SelectMultiple(attrs={"size": 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("valid_from", "valid_to"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]


class BannerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Banner
        fields = ["title", "subtitle", "eyebrow", "image", "mobile_image", "button_text", "link", "position",
                  "text_align", "display_order", "is_active", "starts_at", "ends_at"]
        widgets = {"starts_at": DATETIME_WIDGET, "ends_at": DATETIME_WIDGET}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]


class HomeSectionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = HomeSection
        fields = ["key", "title", "subtitle", "is_visible", "display_order", "item_limit"]


class StaticPageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StaticPage
        fields = ["title", "slug", "content", "footer_column", "display_order", "is_active", "meta_title", "meta_description"]
        widgets = {"content": forms.Textarea(attrs={"rows": 14, "class": "code-editor"})}


class BlogPostForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["title", "excerpt", "content", "cover_image", "tags", "is_published", "meta_title", "meta_description"]
        widgets = {"content": forms.Textarea(attrs={"rows": 14})}


class TestimonialForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ["name", "location", "text", "rating", "image", "is_active", "display_order"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}


class FAQForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["category", "question", "answer", "display_order", "is_active"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 4})}


class InstagramPostForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InstagramPost
        fields = ["image", "link", "caption", "display_order", "is_active"]


class NewsletterSubscriberForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email", "is_active"]


class WebsiteSettingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WebsiteSetting
        exclude = ["updated_at"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "brand_text": forms.Textarea(attrs={"rows": 3}),
            "footer_about": forms.Textarea(attrs={"rows": 2}),
        }


# ---------------------------------------------------------------------------
# Shipping
# ---------------------------------------------------------------------------
class ShippingMethodForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ShippingMethod
        fields = ["name", "code", "description", "charge", "free_above", "min_days", "max_days", "cod_allowed",
                  "is_active", "display_order"]


class PincodeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceablePincode
        fields = ["pincode_prefix", "city", "state", "is_serviceable", "cod_available", "extra_days"]


class ShippingProviderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ShippingProvider
        fields = ["name", "code", "tracking_url_template", "integration_class", "is_active"]


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------
class TicketUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["status", "priority", "assigned_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(is_active=True, role__is_staff_role=True)


# ---------------------------------------------------------------------------
# Staff, roles
# ---------------------------------------------------------------------------
class StaffUserForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Required for new staff. Leave blank to keep the current password.")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "role", "is_active"]

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        roles = Role.objects.filter(is_staff_role=True)
        if not (acting_user and acting_user.is_super_admin):
            roles = roles.exclude(slug=Role.SUPER_ADMIN)  # only Super Admin may grant Super Admin
        self.fields["role"].queryset = roles
        self.fields["role"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("password")
        if not self.instance.pk and not pwd:
            self.add_error("password", "Set a password for the new staff member.")
        if pwd:
            try:
                password_validation.validate_password(pwd, self.instance)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        user.email_verified = True
        if commit:
            user.save()
        return user


class RoleForm(StyledFormMixin, forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=AccessPermission.objects.all(), widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = Role
        fields = ["name", "slug", "description", "is_staff_role", "permissions"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=DATE_WIDGET)
    end = forms.DateField(required=False, widget=DATE_WIDGET)
