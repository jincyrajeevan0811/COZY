"""CRUD module declarations for the COZY dashboard."""
from django.db.models import Count

from apps.categories.models import Category, SubCategory
from apps.coupons.models import Coupon
from apps.products.models import ProductAttribute
from apps.shipping.models import ServiceablePincode, ShippingMethod, ShippingProvider
from apps.website_settings.context_processors import clear_site_caches
from apps.website_settings.models import (
    FAQ, Banner, BlogPost, HomeSection, InstagramPost, NewsletterSubscriber, StaticPage, Testimonial,
)

from . import forms
from .crud import CrudConfig

ACTIVE_FILTER = [("true", "Active"), ("false", "Inactive")]


def _clear(request, obj):
    clear_site_caches()


def _blog_author(request, obj):
    if obj is not None and obj.author_id is None:
        obj.author = request.user
        obj.save(update_fields=["author"])


CRUD_MODULES = [
    CrudConfig(
        name="category", model=Category, form_class=forms.CategoryForm, permission="categories.manage",
        title="Categories", icon="bi-grid-3x3-gap",
        queryset=lambda: Category.objects.annotate(n_products=Count("products")),
        columns=[("", "image", "image"), ("Name", "name", "strong"), ("Products", "n_products"),
                 ("Order", "display_order"), ("Homepage", "show_on_homepage"), ("Active", "is_active")],
        search_fields=["name"], filters=[("is_active", "Status", ACTIVE_FILTER)], after_save=_clear,
        description="Organise the catalogue. Display order controls menus and the homepage.",
    ),
    CrudConfig(
        name="subcategory", model=SubCategory, form_class=forms.SubCategoryForm, permission="categories.manage",
        title="Sub categories", singular="Sub category", icon="bi-diagram-3",
        queryset=lambda: SubCategory.objects.select_related("category"),
        columns=[("Name", "name", "strong"), ("Category", "category__name"), ("Order", "display_order"),
                 ("Active", "is_active")],
        search_fields=["name", "category__name"],
        filters=[("category_id", "Category", lambda: [(c.pk, c.name) for c in Category.objects.all()]),
                 ("is_active", "Status", ACTIVE_FILTER)],
        after_save=_clear,
    ),
    CrudConfig(
        name="attribute", model=ProductAttribute, form_class=forms.AttributeForm, permission="categories.manage",
        title="Attributes", singular="Attribute", icon="bi-palette",
        columns=[("Type", "get_attr_type_display"), ("Value", "value", "strong"), ("Swatch", "color_code", "color"),
                 ("Order", "display_order")],
        search_fields=["value"], filters=[("attr_type", "Type", ProductAttribute.TYPE_CHOICES)],
        description="Colours, materials, styles and sizes used for filters and variants.",
    ),
    CrudConfig(
        name="coupon", model=Coupon, form_class=forms.CouponForm, permission="coupons.manage", title="Coupons",
        icon="bi-ticket-perforated",
        columns=[("Code", "code", "strong"), ("Offer", "label"), ("Min order", "min_order_value", "money"),
                 ("Used", "used_count"), ("Limit", "usage_limit"), ("Expires", "valid_to"), ("Campaign", "campaign"),
                 ("Active", "is_active")],
        search_fields=["code", "campaign", "description"],
        filters=[("is_active", "Status", ACTIVE_FILTER), ("discount_type", "Type", Coupon.TYPE_CHOICES)],
    ),
    CrudConfig(
        name="banner", model=Banner, form_class=forms.BannerForm, permission="content.manage", title="Banners",
        icon="bi-images",
        columns=[("", "image", "image"), ("Title", "title", "strong"), ("Position", "get_position_display"),
                 ("Order", "display_order"), ("Starts", "starts_at"), ("Ends", "ends_at"), ("Active", "is_active")],
        search_fields=["title"], filters=[("position", "Position", Banner.POSITION_CHOICES),
                                          ("is_active", "Status", ACTIVE_FILTER)],
        description="Hero slides, promotional tiles and offer strips. Schedule with start/end dates.",
    ),
    CrudConfig(
        name="homesection", model=HomeSection, form_class=forms.HomeSectionForm, permission="content.manage",
        title="Homepage sections", singular="Homepage section", icon="bi-layout-text-window",
        columns=[("Section", "get_key_display", "strong"), ("Heading", "title"), ("Order", "display_order"),
                 ("Items", "item_limit"), ("Visible", "is_visible")],
        description="Show, hide and reorder homepage sections without touching code.",
    ),
    CrudConfig(
        name="page", model=StaticPage, form_class=forms.StaticPageForm, permission="content.manage",
        title="Website pages", singular="Page", icon="bi-file-earmark-text",
        columns=[("Title", "title", "strong"), ("URL slug", "slug"), ("Footer", "get_footer_column_display"),
                 ("Active", "is_active"), ("Updated", "updated_at")],
        search_fields=["title", "slug"], after_save=_clear,
        description="About Us, policies, shipping & returns and other CMS pages.",
    ),
    CrudConfig(
        name="blog", model=BlogPost, form_class=forms.BlogPostForm, permission="content.manage", title="Blog",
        singular="Blog post", icon="bi-journal-richtext",
        columns=[("", "cover_image", "image"), ("Title", "title", "strong"), ("Published", "is_published"),
                 ("Date", "published_at")],
        search_fields=["title", "tags"], filters=[("is_published", "Status", [("true", "Published"), ("false", "Draft")])],
        after_save=_blog_author,
    ),
    CrudConfig(
        name="testimonial", model=Testimonial, form_class=forms.TestimonialForm, permission="content.manage",
        title="Testimonials", icon="bi-chat-quote",
        columns=[("Name", "name", "strong"), ("Location", "location"), ("Rating", "rating"), ("Active", "is_active")],
        search_fields=["name", "text"],
    ),
    CrudConfig(
        name="faq", model=FAQ, form_class=forms.FAQForm, permission="content.manage", title="FAQs", singular="FAQ",
        icon="bi-question-circle",
        columns=[("Question", "question", "strong"), ("Category", "category"), ("Order", "display_order"),
                 ("Active", "is_active")],
        search_fields=["question", "answer"],
    ),
    CrudConfig(
        name="instagram", model=InstagramPost, form_class=forms.InstagramPostForm, permission="content.manage",
        title="Social gallery", singular="Social post", icon="bi-instagram",
        columns=[("", "image", "image"), ("Caption", "caption"), ("Order", "display_order"), ("Active", "is_active")],
    ),
    CrudConfig(
        name="newsletter", model=NewsletterSubscriber, form_class=forms.NewsletterSubscriberForm,
        permission="newsletter.manage", title="Newsletter subscribers", singular="Subscriber", icon="bi-envelope-heart",
        columns=[("Email", "email", "strong"), ("Source", "source"), ("Subscribed", "subscribed_at"), ("Active", "is_active")],
        search_fields=["email"], filters=[("is_active", "Status", ACTIVE_FILTER)], per_page=50,
    ),
    CrudConfig(
        name="shippingmethod", model=ShippingMethod, form_class=forms.ShippingMethodForm,
        permission="shipping.manage", title="Shipping methods", singular="Shipping method", icon="bi-truck",
        columns=[("Name", "name", "strong"), ("Charge", "charge", "money"), ("Free above", "free_above", "money"),
                 ("Days", lambda o: f"{o.min_days}–{o.max_days}"), ("COD", "cod_allowed"), ("Active", "is_active")],
    ),
    CrudConfig(
        name="pincode", model=ServiceablePincode, form_class=forms.PincodeForm, permission="shipping.manage",
        title="Serviceable PIN codes", singular="PIN code rule", icon="bi-geo-alt",
        columns=[("PIN / prefix", "pincode_prefix", "strong"), ("City", "city"), ("State", "state"),
                 ("Serviceable", "is_serviceable"), ("COD", "cod_available"), ("Extra days", "extra_days")],
        search_fields=["pincode_prefix", "city", "state"], per_page=50,
        description="Leave empty to deliver everywhere. Add a prefix (e.g. 560) to cover a whole region.",
    ),
    CrudConfig(
        name="provider", model=ShippingProvider, form_class=forms.ShippingProviderForm, permission="shipping.manage",
        title="Courier partners", singular="Courier partner", icon="bi-box2-heart",
        columns=[("Name", "name", "strong"), ("Code", "code"), ("Tracking URL", "tracking_url_template"),
                 ("Active", "is_active")],
    ),
]
