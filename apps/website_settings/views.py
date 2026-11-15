from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.utils import is_ajax

from .forms import ContactForm, NewsletterForm
from .models import FAQ, Banner, BlogPost, HomeSection, InstagramPost, StaticPage, Testimonial

DEFAULT_SECTIONS = [
    ("hero", "", ""),
    ("usp", "", ""),
    ("categories", "Shop by Category", "Find the perfect piece for every mood"),
    ("new_arrivals", "New Arrivals", "Fresh drops, just landed"),
    ("promo_banners", "", ""),
    ("bestsellers", "Best Sellers", "Loved by the COZY community"),
    ("trending", "Trending Collections", "What everyone is wearing right now"),
    ("offers", "", ""),
    ("featured", "Featured Picks", "Hand-picked by our stylists"),
    ("discount", "Up to 50% Off", "Steals you don't want to miss"),
    ("brand_intro", "", ""),
    ("testimonials", "Words from our Community", ""),
    ("instagram", "#WearCOZY", "Tag us on Instagram to be featured"),
    ("newsletter", "", ""),
]


def ensure_home_sections():
    if not HomeSection.objects.exists():
        HomeSection.objects.bulk_create([
            HomeSection(key=key, title=title, subtitle=subtitle, display_order=i * 10)
            for i, (key, title, subtitle) in enumerate(DEFAULT_SECTIONS)
        ])
    return HomeSection.objects.filter(is_visible=True)


def home(request):
    from apps.categories.models import Category
    from apps.products.models import Product

    listing = Product.objects.for_listing()
    sections = []
    for section in ensure_home_sections():
        limit = section.item_limit or 8
        data = None
        if section.key == "hero":
            sections.append({"key": "hero", "section": section,
                             "items": list(Banner.objects.live().filter(position=Banner.HERO))})
            continue
        elif section.key == "categories":
            data = Category.objects.active().filter(show_on_homepage=True)[:limit]
        elif section.key == "new_arrivals":
            data = listing.filter(is_new_arrival=True).order_by("-created_at")[:limit]
        elif section.key == "bestsellers":
            data = listing.filter(is_bestseller=True).order_by("-sold_count")[:limit]
        elif section.key == "trending":
            data = listing.filter(is_trending=True).order_by("-view_count")[:limit]
        elif section.key == "featured":
            data = listing.filter(is_featured=True)[:limit]
        elif section.key == "discount":
            data = listing.filter(original_price__gt=F("price")).order_by("price")[:limit]
        elif section.key == "promo_banners":
            data = Banner.objects.live().filter(position=Banner.PROMO)[:4]
        elif section.key == "offers":
            data = Banner.objects.live().filter(position=Banner.OFFER)[:1]
        elif section.key == "testimonials":
            data = Testimonial.objects.filter(is_active=True)[:limit]
        elif section.key == "instagram":
            data = InstagramPost.objects.filter(is_active=True)[:limit]
        else:  # usp, brand_intro, newsletter use site settings only
            data = True
        if data is True or (data is not None and len(data) > 0):
            sections.append({"key": section.key, "section": section, "items": data})
    return render(request, "storefront/home.html", {"sections": sections, "newsletter_form": NewsletterForm()})


def page_detail(request, slug):
    page = get_object_or_404(StaticPage, slug=slug, is_active=True)
    return render(request, "storefront/page.html", {"page": page})


def blog_list(request):
    posts = BlogPost.objects.filter(is_published=True)
    tag = request.GET.get("tag")
    if tag:
        posts = posts.filter(tags__icontains=tag)
    page = Paginator(posts, 9).get_page(request.GET.get("page"))
    return render(request, "storefront/blog_list.html", {"page_obj": page, "posts": page.object_list, "tag": tag})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    recent = BlogPost.objects.filter(is_published=True).exclude(pk=post.pk)[:3]
    return render(request, "storefront/blog_detail.html", {"post": post, "recent_posts": recent})


def faq(request):
    faqs = FAQ.objects.filter(is_active=True)
    grouped = {}
    for item in faqs:
        grouped.setdefault(item.category, []).append(item)
    return render(request, "storefront/faq.html", {"faq_groups": grouped})


def contact(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.full_name, "email": request.user.email, "phone": request.user.phone}
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        from apps.support.services import create_ticket

        ticket = create_ticket(
            user=request.user if request.user.is_authenticated else None,
            name=form.cleaned_data["name"],
            email=form.cleaned_data["email"],
            phone=form.cleaned_data.get("phone", ""),
            subject=form.cleaned_data["subject"],
            category=form.cleaned_data["category"],
            message=form.cleaned_data["message"],
        )
        messages.success(request, f"Thank you! Your ticket {ticket.ticket_number} has been created. We'll reply soon.")
        return redirect("site:contact")
    return render(request, "storefront/contact.html", {"form": form})


@require_POST
def newsletter_subscribe(request):
    from .models import NewsletterSubscriber

    form = NewsletterForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"].lower()
        sub, created = NewsletterSubscriber.objects.get_or_create(email=email)
        if not sub.is_active:
            sub.is_active = True
            sub.save(update_fields=["is_active"])
        msg = "You're on the list! Watch your inbox for new drops." if created else "You're already subscribed — thank you!"
        ok = True
    else:
        msg, ok = "Please enter a valid email address.", False
    if is_ajax(request):
        return JsonResponse({"ok": ok, "message": msg}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, msg)
    return redirect(request.META.get("HTTP_REFERER") or reverse("home"))


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /cart/",
        "Disallow: /orders/",
        "Disallow: /accounts/",
        "Disallow: /payments/",
        "Disallow: /notifications/",
        "Disallow: /cozy-admin/",
        f"Sitemap: {request.build_absolute_uri(reverse('django.contrib.sitemaps.views.sitemap'))}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
