from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.utils import optimize_image, unique_slugify
from apps.core.validators import IMAGE_VALIDATORS


class WebsiteSetting(models.Model):
    """Singleton holding site-wide configuration editable from the dashboard."""

    CACHE_KEY = "cozy:website-settings"

    site_name = models.CharField(max_length=80, default="COZY")
    tagline = models.CharField(max_length=160, default="Fashion jewellery for every moment")
    logo = models.ImageField(upload_to="branding/", blank=True, validators=IMAGE_VALIDATORS)
    favicon = models.ImageField(upload_to="branding/", blank=True, validators=IMAGE_VALIDATORS)
    announcement_text = models.CharField(max_length=200, blank=True,
                                         default="Free shipping on orders above ₹999 · Easy 7-day returns")
    announcement_active = models.BooleanField(default=True)
    # Contact
    contact_email = models.EmailField(default="hello@cozy.example")
    contact_phone = models.CharField(max_length=20, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True, help_text="With country code, digits only, e.g. 919876543210")
    address = models.TextField(blank=True)
    business_hours = models.CharField(max_length=120, blank=True, default="Mon–Sat, 10 AM – 7 PM")
    gstin = models.CharField("GSTIN", max_length=20, blank=True)
    # Commerce
    currency_symbol = models.CharField(max_length=5, default="₹")
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("999"))
    tax_percent = models.DecimalField("GST %", max_digits=5, decimal_places=2, default=Decimal("3"))
    prices_include_tax = models.BooleanField(default=True, help_text="Displayed prices already include GST.")
    cod_enabled = models.BooleanField("Cash on Delivery enabled", default=True)
    cod_max_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("10000"))
    cod_extra_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    gift_wrap_enabled = models.BooleanField(default=True)
    gift_wrap_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("49"))
    return_window_days = models.PositiveSmallIntegerField(default=7)
    return_policy_summary = models.CharField(max_length=255, default="Easy 7-day returns on unused items with original packaging.")
    low_stock_threshold = models.PositiveIntegerField(default=5)
    # Brand story (homepage)
    brand_title = models.CharField(max_length=120, default="Crafted to be loved, priced to be worn")
    brand_text = models.TextField(blank=True, default=(
        "COZY brings you on-trend fashion jewellery — Korean minimal, western statement and festive "
        "imitation pieces — designed for everyday sparkle without the precious-metal price tag."
    ))
    brand_image = models.ImageField(upload_to="branding/", blank=True, validators=IMAGE_VALIDATORS)
    newsletter_title = models.CharField(max_length=120, default="Join the COZY circle")
    newsletter_text = models.CharField(max_length=255, default="Be the first to know about new drops and members-only offers.")
    # Footer & social
    footer_about = models.TextField(blank=True, default="Affordable, trend-led fashion jewellery and accessories, delivered across India.")
    copyright_text = models.CharField(max_length=160, blank=True, default="COZY Fashion Jewellery. All rights reserved.")
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    pinterest_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_handle = models.CharField(max_length=60, blank=True, default="@cozy.jewellery")
    # SEO & marketing integrations (IDs only — no secrets)
    meta_title = models.CharField(max_length=160, default="COZY — Fashion Jewellery Online")
    meta_description = models.CharField(max_length=300, default=(
        "Shop trendy fashion, Korean, western and imitation jewellery online at COZY. Earrings, necklaces, "
        "bracelets, rings and gift sets at affordable prices."
    ))
    og_image = models.ImageField(upload_to="branding/", blank=True, validators=IMAGE_VALIDATORS)
    google_analytics_id = models.CharField(max_length=40, blank=True, help_text="e.g. G-XXXXXXX")
    facebook_pixel_id = models.CharField(max_length=40, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "website settings"
        verbose_name_plural = "website settings"

    def __str__(self):
        return "Website settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        optimize_image(self.logo, max_size=600)
        optimize_image(self.brand_image, max_size=1400)
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass  # singleton cannot be deleted

    @classmethod
    def load(cls):
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, obj, 300)
        return obj

    @property
    def whatsapp_link(self):
        return f"https://wa.me/{self.whatsapp_number}" if self.whatsapp_number else ""


class ScheduledQuerySet(models.QuerySet):
    def live(self):
        now = timezone.now()
        return self.filter(is_active=True).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gte=now)
        )


class Banner(TimeStampedModel):
    HERO, PROMO, CATEGORY, OFFER = "hero", "promo", "category", "offer"
    POSITION_CHOICES = [
        (HERO, "Homepage hero slider"),
        (PROMO, "Promotional banner (two-up)"),
        (OFFER, "Special offer strip"),
        (CATEGORY, "Category page banner"),
    ]

    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=255, blank=True)
    eyebrow = models.CharField(max_length=60, blank=True, help_text="Small text above the title, e.g. NEW SEASON")
    image = models.ImageField(upload_to="banners/", validators=IMAGE_VALIDATORS)
    mobile_image = models.ImageField(upload_to="banners/", blank=True, validators=IMAGE_VALIDATORS)
    button_text = models.CharField(max_length=40, blank=True, default="Shop now")
    link = models.CharField(max_length=255, blank=True, help_text="Relative (/shop/) or absolute URL")
    position = models.CharField(max_length=20, choices=POSITION_CHOICES, default=HERO, db_index=True)
    text_align = models.CharField(max_length=10, choices=[("left", "Left"), ("center", "Center"), ("right", "Right")], default="left")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    objects = ScheduledQuerySet.as_manager()

    class Meta:
        ordering = ["position", "display_order", "-created_at"]

    def __str__(self):
        return f"{self.get_position_display()}: {self.title}"

    def save(self, *args, **kwargs):
        optimize_image(self.image, max_size=2000)
        optimize_image(self.mobile_image, max_size=1000)
        super().save(*args, **kwargs)


class HomeSection(models.Model):
    """Controls visibility, order and headings of homepage sections."""

    KEY_CHOICES = [
        ("hero", "Hero banner slider"),
        ("usp", "Service highlights strip"),
        ("categories", "Shop by category"),
        ("new_arrivals", "New arrivals"),
        ("promo_banners", "Promotional banners"),
        ("bestsellers", "Best sellers"),
        ("trending", "Trending collections"),
        ("offers", "Special offers strip"),
        ("featured", "Featured products"),
        ("discount", "Discount collection"),
        ("brand_intro", "Brand introduction"),
        ("testimonials", "Testimonials"),
        ("instagram", "Instagram / social gallery"),
        ("newsletter", "Newsletter signup"),
    ]

    key = models.CharField(max_length=30, choices=KEY_CHOICES, unique=True)
    title = models.CharField(max_length=120, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    is_visible = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    item_limit = models.PositiveSmallIntegerField(default=8)

    class Meta:
        ordering = ["display_order"]

    def __str__(self):
        return self.get_key_display()


class StaticPage(TimeStampedModel):
    FOOTER_COLUMNS = [("", "Not in footer"), ("help", "Help"), ("company", "Company"), ("policies", "Policies")]

    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    content = models.TextField(help_text="HTML allowed. Only trusted content managers can edit pages.")
    footer_column = models.CharField(max_length=20, choices=FOOTER_COLUMNS, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["display_order", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site:page", args=[self.slug])


class BlogPost(TimeStampedModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt = models.CharField(max_length=300, blank=True)
    content = models.TextField(help_text="HTML allowed.")
    cover_image = models.ImageField(upload_to="blog/", blank=True, validators=IMAGE_VALIDATORS)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.CharField(max_length=200, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        optimize_image(self.cover_image, max_size=1600)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("site:blog_detail", args=[self.slug])


class Testimonial(TimeStampedModel):
    name = models.CharField(max_length=80)
    location = models.CharField(max_length=80, blank=True)
    text = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)
    image = models.ImageField(upload_to="testimonials/", blank=True, validators=IMAGE_VALIDATORS)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.name


class FAQ(TimeStampedModel):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.CharField(max_length=60, default="General")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "display_order"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class InstagramPost(TimeStampedModel):
    image = models.ImageField(upload_to="social/", validators=IMAGE_VALIDATORS)
    link = models.URLField(blank=True)
    caption = models.CharField(max_length=150, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.caption or f"Social post {self.pk}"

    def save(self, *args, **kwargs):
        optimize_image(self.image, max_size=800)
        super().save(*args, **kwargs)


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=30, default="website")
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-subscribed_at"]

    def __str__(self):
        return self.email
