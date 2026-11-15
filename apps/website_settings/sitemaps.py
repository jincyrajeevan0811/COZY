from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.categories.models import Category
from apps.products.models import Product

from .models import BlogPost, StaticPage


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "daily"

    def items(self):
        return ["home", "products:list", "site:blog_list", "site:faq", "site:contact"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Product.objects.active()

    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Category.objects.active()

    def lastmod(self, obj):
        return obj.updated_at


class PageSitemap(Sitemap):
    priority = 0.4

    def items(self):
        return StaticPage.objects.filter(is_active=True)


class BlogSitemap(Sitemap):
    priority = 0.5

    def items(self):
        return BlogPost.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "static": StaticViewSitemap,
    "products": ProductSitemap,
    "categories": CategorySitemap,
    "pages": PageSitemap,
    "blog": BlogSitemap,
}
