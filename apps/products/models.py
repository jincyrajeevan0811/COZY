from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.categories.models import Category, SubCategory
from apps.core.models import TimeStampedModel
from apps.core.utils import optimize_image, unique_slugify
from apps.core.validators import IMAGE_VALIDATORS


class ProductAttribute(models.Model):
    """Filterable product attributes: colours, materials, styles and sizes."""

    COLOR, MATERIAL, STYLE, SIZE = "color", "material", "style", "size"
    TYPE_CHOICES = [(COLOR, "Colour"), (MATERIAL, "Material"), (STYLE, "Style"), (SIZE, "Size")]

    attr_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    value = models.CharField(max_length=60)
    slug = models.SlugField(max_length=80, blank=True)
    color_code = models.CharField(max_length=7, blank=True, help_text="Hex colour for swatches, e.g. #D4AF37")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["attr_type", "display_order", "value"]
        constraints = [models.UniqueConstraint(fields=["attr_type", "value"], name="unique_attribute_value")]

    def __str__(self):
        return f"{self.get_attr_type_display()}: {self.value}"

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.value)
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)

    def with_stock(self):
        return self.annotate(stock_total=Sum("inventories__quantity", filter=self._sellable_inventory_q()))

    @staticmethod
    def _sellable_inventory_q():
        # Variant products count active variants only; simple products count their base row.
        return Q(has_variants=False, inventories__variant__isnull=True) | Q(
            has_variants=True, inventories__variant__is_active=True
        )

    def for_listing(self):
        return (
            self.active()
            .select_related("category", "subcategory", "color")
            .prefetch_related("images")
            .with_stock()
        )


class Product(TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField("SKU", max_length=50, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField("Selling price", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    original_price = models.DecimalField("Original price (MRP)", max_digits=10, decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(Decimal("0.01"))])
    color = models.ForeignKey(ProductAttribute, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                              limit_choices_to={"attr_type": ProductAttribute.COLOR})
    material = models.ForeignKey(ProductAttribute, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                 limit_choices_to={"attr_type": ProductAttribute.MATERIAL})
    style = models.ForeignKey(ProductAttribute, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                              limit_choices_to={"attr_type": ProductAttribute.STYLE})
    size_info = models.CharField("Size / dimensions", max_length=120, blank=True)
    weight_grams = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    care_instructions = models.TextField(blank=True)
    has_variants = models.BooleanField(default=False, help_text="Enable when stock is tracked per variant (colour/size).")
    is_returnable = models.BooleanField(default=True)
    return_days = models.PositiveSmallIntegerField(default=7)
    # Merchandising flags
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_trending = models.BooleanField(default=False, db_index=True)
    is_bestseller = models.BooleanField(default=False, db_index=True)
    is_new_arrival = models.BooleanField(default=True, db_index=True)
    tags = models.CharField(max_length=300, blank=True, help_text="Comma-separated search keywords")
    # SEO
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)
    meta_keywords = models.CharField(max_length=300, blank=True)
    # Denormalised stats (kept up to date by services/signals)
    sold_count = models.PositiveIntegerField(default=0, db_index=True)
    view_count = models.PositiveIntegerField(default=0)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "category"]),
            models.Index(fields=["price"]),
            models.Index(fields=["-sold_count"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.original_price and self.price and self.original_price < self.price:
            raise ValidationError({"original_price": "Original price must be greater than or equal to the selling price."})
        if self.subcategory_id and self.category_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "Sub category does not belong to the selected category."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        self.sku = self.sku.upper().strip()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:detail", args=[self.slug])

    # ---- pricing ------------------------------------------------------
    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            return int(round((self.original_price - self.price) * 100 / self.original_price))
        return 0

    # ---- images -------------------------------------------------------
    @property
    def primary_image(self):
        images = list(self.images.all())  # uses prefetch cache when available
        for img in images:
            if img.is_primary:
                return img
        return images[0] if images else None

    @property
    def secondary_image(self):
        images = list(self.images.all())
        primary = self.primary_image
        for img in images:
            if primary and img.pk != primary.pk:
                return img
        return None

    # ---- stock --------------------------------------------------------
    @property
    def stock_quantity(self):
        if hasattr(self, "stock_total"):
            return self.stock_total or 0
        if self.has_variants:
            qs = self.inventories.filter(variant__isnull=False, variant__is_active=True)
        else:
            qs = self.inventories.filter(variant__isnull=True)
        return qs.aggregate(t=Sum("quantity"))["t"] or 0

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def is_new(self):
        return self.is_new_arrival or (timezone.now() - self.created_at).days <= 30

    def active_variants(self):
        return self.variants.filter(is_active=True).select_related("color", "size", "inventory")


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", validators=IMAGE_VALIDATORS)
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-is_primary", "display_order", "id"]

    def __str__(self):
        return f"Image for {self.product}"

    def save(self, *args, **kwargs):
        optimize_image(self.image, max_size=1600)
        if not self.alt_text:
            self.alt_text = self.product.name
        super().save(*args, **kwargs)
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        elif not ProductImage.objects.filter(product=self.product, is_primary=True).exists():
            ProductImage.objects.filter(pk=self.pk).update(is_primary=True)
            self.is_primary = True


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=120, help_text="e.g. Rose Gold / Medium")
    sku = models.CharField("SKU", max_length=60, unique=True)
    color = models.ForeignKey(ProductAttribute, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                              limit_choices_to={"attr_type": ProductAttribute.COLOR})
    size = models.ForeignKey(ProductAttribute, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                             limit_choices_to={"attr_type": ProductAttribute.SIZE})
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                help_text="Leave blank to use the product price.")
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.product.name} — {self.name}"

    def save(self, *args, **kwargs):
        self.sku = self.sku.upper().strip()
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def effective_original_price(self):
        return self.original_price if self.original_price is not None else self.product.original_price

    @property
    def stock_quantity(self):
        inv = getattr(self, "inventory", None)
        return inv.quantity if inv else 0


class RecentlyViewed:
    """Session-backed list of recently viewed product ids (no DB table needed)."""

    SESSION_KEY = "recently_viewed"
    LIMIT = 12

    def __init__(self, request):
        self.session = request.session

    def add(self, product_id):
        ids = [pid for pid in self.session.get(self.SESSION_KEY, []) if pid != product_id]
        ids.insert(0, product_id)
        self.session[self.SESSION_KEY] = ids[: self.LIMIT]

    def ids(self, exclude=None):
        return [pid for pid in self.session.get(self.SESSION_KEY, []) if pid != exclude]
