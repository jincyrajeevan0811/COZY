import json
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import F, Max, Min
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.categories.models import Category

from .filters import COLLECTIONS, SORT_OPTIONS, apply_filters, search_q
from .models import Product, ProductAttribute, RecentlyViewed

PAGE_SIZE = 24


def _listing_context(request, base_qs, title, category=None, collection=None, description=""):
    products, active, sort = apply_filters(base_qs, request.GET)
    paginator = Paginator(products, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    price_range = base_qs.aggregate(lo=Min("price"), hi=Max("price"))
    attributes = ProductAttribute.objects.all()
    return {
        "title": title,
        "description": description,
        "category": category,
        "collection": collection,
        "page_obj": page,
        "products": page.object_list,
        "total": paginator.count,
        "active_filters": active,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "colors": [a for a in attributes if a.attr_type == ProductAttribute.COLOR],
        "materials": [a for a in attributes if a.attr_type == ProductAttribute.MATERIAL],
        "styles": [a for a in attributes if a.attr_type == ProductAttribute.STYLE],
        "price_range": price_range,
        "subcategories": category.subcategories.active() if category else None,
        "all_categories": Category.objects.active(),
        "discount_options": [10, 20, 30, 50],
    }


def product_list(request):
    context = _listing_context(request, Product.objects.for_listing(), "Shop All Jewellery")
    return render(request, "products/list.html", context)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    qs = Product.objects.for_listing().filter(category=category)
    context = _listing_context(request, qs, category.name, category=category, description=category.description)
    return render(request, "products/list.html", context)


def collection(request, slug):
    if slug not in COLLECTIONS:
        raise Http404("Collection not found")
    title, flag, default_sort = COLLECTIONS[slug]
    params = request.GET.copy()
    params.setdefault("flag", flag)
    params.setdefault("sort", default_sort)
    request.GET = params
    context = _listing_context(request, Product.objects.for_listing(), title, collection=slug)
    return render(request, "products/list.html", context)


def search(request):
    query = (request.GET.get("q") or "").strip()[:100]
    if query:
        recent = [s for s in request.session.get("recent_searches", []) if s.lower() != query.lower()]
        request.session["recent_searches"] = ([query] + recent)[:8]
    context = _listing_context(request, Product.objects.for_listing(), f'Results for "{query}"' if query else "Search")
    context["query"] = query
    context["is_search"] = True
    if query and context["total"] == 0:
        context["suggested"] = Product.objects.for_listing().order_by("-sold_count")[:8]
        context["suggested_categories"] = Category.objects.active()[:8]
    return render(request, "products/list.html", context)


@require_GET
def autocomplete(request):
    query = (request.GET.get("q") or "").strip()[:60]
    if len(query) < 2:
        return JsonResponse({"products": [], "categories": [], "recent": request.session.get("recent_searches", [])[:5]})
    products = (
        Product.objects.active().filter(search_q(query)).select_related("category").prefetch_related("images")
        .distinct()[:6]
    )
    categories = Category.objects.active().filter(name__icontains=query)[:4]
    data = {
        "products": [
            {
                "name": p.name,
                "url": p.get_absolute_url(),
                "price": str(p.price),
                "image": p.primary_image.image.url if p.primary_image else "",
                "category": p.category.name,
            }
            for p in products
        ],
        "categories": [{"name": c.name, "url": c.get_absolute_url()} for c in categories],
        "search_url": f"{reverse('products:search')}?{urlencode({'q': query})}",
    }
    return JsonResponse(data)


def _product_payload(product):
    """Variant data for the product page JavaScript (price/stock switching)."""
    variants = []
    for v in product.active_variants():
        variants.append({
            "id": v.id,
            "name": v.name,
            "sku": v.sku,
            "price": str(v.effective_price),
            "original_price": str(v.effective_original_price or ""),
            "stock": v.stock_quantity,
            "color": v.color.value if v.color else "",
            "size": v.size.value if v.size else "",
        })
    return variants


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().select_related("category", "subcategory", "color", "material", "style")
        .prefetch_related("images"),
        slug=slug,
    )
    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
    recently = RecentlyViewed(request)
    recent_ids = recently.ids(exclude=product.id)
    recently.add(product.id)

    recent_products = list(Product.objects.for_listing().filter(id__in=recent_ids[:8]))
    recent_products.sort(key=lambda p: recent_ids.index(p.id))

    related = (
        Product.objects.for_listing().filter(category=product.category).exclude(pk=product.pk)
        .order_by("-is_bestseller", "-sold_count")[:8]
    )
    reviews = product.reviews.filter(status="approved").select_related("user").prefetch_related("images")[:20]
    variants = _product_payload(product) if product.has_variants else []

    in_wishlist = False
    can_review = False
    has_reviewed = False
    if request.user.is_authenticated:
        from apps.reviews.models import ProductReview
        from apps.wishlist.models import WishlistItem

        in_wishlist = WishlistItem.objects.filter(wishlist__user=request.user, product=product).exists()
        has_reviewed = ProductReview.objects.filter(user=request.user, product=product).exists()
        can_review = not has_reviewed

    rating_breakdown = {i: 0 for i in range(5, 0, -1)}
    for r in product.reviews.filter(status="approved").values_list("rating", flat=True):
        rating_breakdown[r] = rating_breakdown.get(r, 0) + 1

    from apps.shipping.services import default_delivery_estimate
    from apps.website_settings.models import WebsiteSetting

    context = {
        "product": product,
        "images": product.images.all(),
        "variants": variants,
        "variants_json": json.dumps(variants),
        "related_products": related,
        "recent_products": recent_products,
        "reviews": reviews,
        "rating_breakdown": rating_breakdown,
        "in_wishlist": in_wishlist,
        "can_review": can_review,
        "has_reviewed": has_reviewed,
        "delivery_estimate": default_delivery_estimate(),
        "site_settings": WebsiteSetting.load(),
    }
    return render(request, "products/detail.html", context)


def quick_view(request, slug):
    product = get_object_or_404(Product.objects.active().prefetch_related("images"), slug=slug)
    variants = _product_payload(product) if product.has_variants else []
    return render(request, "products/_quick_view.html", {
        "product": product, "variants": variants, "variants_json": json.dumps(variants)
    })
