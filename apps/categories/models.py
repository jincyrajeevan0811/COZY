from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel
from apps.core.utils import optimize_image, unique_slugify
from apps.core.validators import IMAGE_VALIDATORS


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, validators=IMAGE_VALIDATORS)
    banner_image = models.ImageField(upload_to="categories/banners/", blank=True, validators=IMAGE_VALIDATORS)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    show_on_homepage = models.BooleanField(default=True)
    show_in_menu = models.BooleanField(default=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        optimize_image(self.image, max_size=900)
        optimize_image(self.banner_image, max_size=1920)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:category", args=[self.slug])


class SubCategory(TimeStampedModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/sub/", blank=True, validators=IMAGE_VALIDATORS)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["category__display_order", "display_order", "name"]
        verbose_name_plural = "sub categories"
        constraints = [models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_per_category")]

    def __str__(self):
        return f"{self.category.name} › {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, f"{self.category.name}-{self.name}")
        optimize_image(self.image, max_size=900)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"{self.category.get_absolute_url()}?sub={self.slug}"
