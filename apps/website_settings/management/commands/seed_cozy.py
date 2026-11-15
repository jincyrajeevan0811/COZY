"""
Load COZY demo data: categories, attributes, products (with generated images),
banners, CMS pages, FAQs, testimonials, shipping methods and coupons.

    python manage.py seed_cozy            # add demo data (idempotent)
    python manage.py seed_cozy --no-images  # skip image generation

Images are generated with Pillow so the store looks complete without any
third-party photos. Replace them with real product photography from the dashboard.
"""
import io
import math
import random
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.rbac import sync_roles_and_permissions
from apps.categories.models import Category, SubCategory
from apps.coupons.models import Coupon
from apps.inventory.models import StockHistory
from apps.inventory.services import adjust_stock, get_inventory
from apps.products.models import Product, ProductAttribute, ProductImage, ProductVariant
from apps.shipping.models import ShippingMethod, ShippingProvider
from apps.website_settings.models import (
    FAQ, Banner, BlogPost, HomeSection, InstagramPost, StaticPage, Testimonial, WebsiteSetting,
)
from apps.website_settings.views import ensure_home_sections

PALETTES = [
    ((243, 233, 220), (232, 196, 196)),
    ((251, 247, 242), (226, 205, 178)),
    ((244, 225, 227), (201, 166, 107)),
    ((238, 229, 222), (183, 110, 121)),
    ((247, 240, 232), (214, 190, 160)),
]
GOLD = (201, 166, 107)
ROSE = (183, 110, 121)
SILVER = (176, 176, 184)

CATEGORIES = [
    ("Earrings", "Studs, hoops, drops and statement danglers.", ["Studs", "Hoops", "Drop Earrings", "Jhumkas"]),
    ("Necklaces", "Layered chains, chokers and pendant necklaces.", ["Chokers", "Pendant Necklaces", "Layered Chains"]),
    ("Bracelets", "Charm bracelets, cuffs and bangles.", ["Charm Bracelets", "Cuffs", "Bangles"]),
    ("Rings", "Stackable, cocktail and adjustable rings.", ["Stackable Rings", "Cocktail Rings", "Adjustable Rings"]),
    ("Anklets", "Delicate anklets for every day.", []),
    ("Jewellery Sets", "Coordinated sets for parties and festivities.", ["Party Sets", "Festive Sets"]),
    ("Hair Accessories", "Clips, pins and claw clips with sparkle.", ["Hair Clips", "Claw Clips"]),
    ("Fashion Accessories", "Brooches, keychains and bag charms.", []),
    ("Gift Items", "Curated gift boxes ready to surprise.", []),
]

COLORS = [("Gold", "#D4AF37"), ("Rose Gold", "#B76E79"), ("Silver", "#C0C0C8"), ("Pearl White", "#F2EDE4"),
          ("Black", "#2B2B2B"), ("Multicolour", "#C98FA0")]
MATERIALS = ["Brass", "Alloy", "Stainless Steel", "Sterling Silver Plated", "Pearl", "Crystal", "Kundan", "Oxidised Metal"]
STYLES = ["Korean", "Western", "Minimal", "Statement", "Traditional", "Boho", "Party Wear", "Daily Wear"]
SIZES = ["Free Size", "Small", "Medium", "Large", "6", "7", "8"]

ADJECTIVES = ["Luna", "Aurora", "Celeste", "Blossom", "Velvet", "Serene", "Gilded", "Petal", "Starlit", "Ivy", "Opal",
              "Sienna", "Halo", "Dew", "Muse", "Bloom"]
NOUNS = {
    "Earrings": ["Pearl Drop Earrings", "Huggie Hoops", "Crystal Studs", "Jhumka Earrings", "Heart Danglers"],
    "Necklaces": ["Layered Chain", "Pendant Necklace", "Choker", "Pearl Strand", "Initial Necklace"],
    "Bracelets": ["Charm Bracelet", "Cuff Bracelet", "Bangle Set", "Tennis Bracelet"],
    "Rings": ["Stackable Ring", "Cocktail Ring", "Adjustable Ring", "Solitaire Ring"],
    "Anklets": ["Bead Anklet", "Chain Anklet", "Ghungroo Anklet"],
    "Jewellery Sets": ["Party Set", "Kundan Necklace Set", "Pearl Set"],
    "Hair Accessories": ["Pearl Hair Clip", "Claw Clip", "Hair Pin Set"],
    "Fashion Accessories": ["Bag Charm", "Brooch", "Keychain"],
    "Gift Items": ["Gift Box Duo", "Self-love Gift Set", "Bridesmaid Box"],
}


def _gradient(size, top, bottom):
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        draw.line((0, y, w, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _sparkles(draw, w, h, rng, n=18):
    for _ in range(n):
        x, y, r = rng.randint(0, w), rng.randint(0, h), rng.randint(2, 6)
        draw.line((x - r * 2, y, x + r * 2, y), fill=(255, 255, 255), width=1)
        draw.line((x, y - r * 2, x, y + r * 2), fill=(255, 255, 255), width=1)


def jewellery_image(kind, seed, size=(800, 1000), label=None):
    """Draw a stylised jewellery illustration (no external assets)."""
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    top, bottom = PALETTES[seed % len(PALETTES)]
    img = _gradient(size, top, bottom)
    w, h = size
    draw = ImageDraw.Draw(img)
    metal = [GOLD, ROSE, SILVER][seed % 3]
    cx, cy = w // 2, int(h * 0.48)

    # soft shadow
    shadow = Image.new("L", size, 0)
    sd = ImageDraw.Draw(shadow)
    sd.ellipse((cx - 220, cy + 260, cx + 220, cy + 300), fill=90)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.paste((150, 120, 110), mask=shadow)
    draw = ImageDraw.Draw(img)

    if kind == "Earrings":
        for dx in (-150, 150):
            draw.ellipse((cx + dx - 18, cy - 200, cx + dx + 18, cy - 164), outline=metal, width=8)
            draw.line((cx + dx, cy - 164, cx + dx, cy - 40), fill=metal, width=6)
            draw.ellipse((cx + dx - 55, cy - 50, cx + dx + 55, cy + 90), fill=(250, 246, 240), outline=metal, width=6)
    elif kind in ("Necklaces", "Jewellery Sets"):
        draw.arc((cx - 280, cy - 380, cx + 280, cy + 120), 20, 160, fill=metal, width=8)
        draw.arc((cx - 230, cy - 330, cx + 230, cy + 60), 25, 155, fill=metal, width=5)
        draw.polygon([(cx, cy + 70), (cx - 50, cy + 150), (cx, cy + 230), (cx + 50, cy + 150)], fill=(250, 246, 240),
                     outline=metal)
        if kind == "Jewellery Sets":
            for dx in (-260, 260):
                draw.ellipse((cx + dx - 35, cy + 200, cx + dx + 35, cy + 280), fill=(250, 246, 240), outline=metal, width=5)
    elif kind == "Rings":
        draw.ellipse((cx - 170, cy - 120, cx + 170, cy + 220), outline=metal, width=30)
        draw.polygon([(cx, cy - 230), (cx - 70, cy - 150), (cx, cy - 90), (cx + 70, cy - 150)], fill=(255, 255, 255),
                     outline=metal)
    elif kind in ("Bracelets", "Anklets"):
        draw.ellipse((cx - 240, cy - 150, cx + 240, cy + 190), outline=metal, width=22)
        for i in range(12):
            a = i / 12 * 2 * math.pi
            x, y = cx + 240 * math.cos(a), cy + 20 + 170 * math.sin(a)
            draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=(250, 246, 240), outline=metal, width=3)
    elif kind == "Hair Accessories":
        draw.rounded_rectangle((cx - 230, cy - 50, cx + 230, cy + 40), radius=40, fill=metal)
        for i in range(-3, 4):
            draw.ellipse((cx + i * 62 - 24, cy - 30, cx + i * 62 + 24, cy + 18), fill=(250, 246, 240))
    else:  # accessories & gifts
        draw.rounded_rectangle((cx - 200, cy - 140, cx + 200, cy + 200), radius=18, fill=(250, 246, 240), outline=metal,
                               width=6)
        draw.rectangle((cx - 18, cy - 140, cx + 18, cy + 200), fill=ROSE)
        draw.rectangle((cx - 200, cy + 12, cx + 200, cy + 48), fill=ROSE)
        draw.ellipse((cx - 70, cy - 200, cx - 5, cy - 140), outline=ROSE, width=12)
        draw.ellipse((cx + 5, cy - 200, cx + 70, cy - 140), outline=ROSE, width=12)
    _sparkles(draw, w, h, rng)
    if label:
        draw.text((40, h - 70), label.upper(), fill=(90, 70, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=86, optimize=True)
    return ContentFile(buf.getvalue())


def banner_image(seed, size=(1920, 820)):
    from PIL import ImageDraw

    rng = random.Random(seed)
    top, bottom = PALETTES[(seed + 1) % len(PALETTES)]
    img = _gradient(size, top, bottom)
    draw = ImageDraw.Draw(img)
    w, h = size
    for i in range(5):
        r = rng.randint(120, 300)
        x, y = rng.randint(int(w * .55), w), rng.randint(0, h)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=[GOLD, ROSE][i % 2], width=rng.randint(6, 16))
    draw.arc((int(w * .55), 80, int(w * .95), h + 300), 190, 350, fill=GOLD, width=10)
    _sparkles(draw, w, h, rng, n=60)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return ContentFile(buf.getvalue())


PAGES = {
    "About Us": ("company", """<p>COZY was born from a simple idea: beautiful jewellery shouldn't be reserved for special occasions or special budgets.</p>
<p>We design and curate trend-led <strong>fashion, imitation, Korean and western jewellery</strong> — earrings, necklaces, rings, bracelets and gift sets — so you can express every mood, every day.</p>
<h2>Our promise</h2><ul><li>Skin-friendly, nickel-safe finishes wherever possible</li><li>Quality checks on every piece before it ships</li><li>Easy returns and friendly support</li></ul>"""),
    "Shipping Policy": ("policies", """<h2>Delivery timelines</h2><p>Orders are dispatched within 1–2 business days. Standard delivery takes 3–7 business days across India; Express delivery takes 1–3 business days in metro cities.</p>
<h2>Shipping charges</h2><p>Shipping is free on orders above the free-shipping threshold shown at checkout. A flat fee applies below it.</p>
<h2>Tracking</h2><p>You'll receive a tracking number by email as soon as your order ships. You can also track it from <em>My orders</em>.</p>"""),
    "Return & Refund Policy": ("policies", """<p>We accept returns within <strong>7 days of delivery</strong> for unused items in their original packaging with tags.</p>
<h2>How to return</h2><ol><li>Go to <em>My orders</em> and open the delivered order.</li><li>Click <em>Return</em> and tell us why.</li><li>Our courier partner will pick up the item once approved.</li></ol>
<h2>Refunds</h2><p>Refunds are issued to the original payment method within 5–7 business days after the item is received and inspected. COD refunds are sent to your bank account or UPI ID.</p>
<p>For hygiene reasons, earrings marked as non-returnable cannot be returned unless damaged.</p>"""),
    "Privacy Policy": ("policies", """<p>We collect only the information needed to process your orders and improve your experience: name, contact details, delivery address and order history.</p>
<p>Payments are processed securely by Razorpay. <strong>We never store card, UPI or bank credentials.</strong></p>
<p>We never sell your data. You can unsubscribe from marketing emails at any time from your profile.</p>"""),
    "Terms & Conditions": ("policies", """<p>By using this website you agree to these terms. Product colours may vary slightly due to photography and screen settings.</p>
<p>Prices are in Indian Rupees and include applicable taxes unless stated otherwise. We reserve the right to cancel orders in case of pricing errors or suspected fraud; any payment received will be refunded in full.</p>"""),
    "Jewellery Care": ("help", """<ul><li>Keep away from water, perfume, lotions and sweat.</li><li>Put jewellery on last and take it off first.</li><li>Store each piece separately in the COZY pouch.</li><li>Wipe gently with a soft dry cloth after wearing.</li></ul>"""),
}

FAQS = [
    ("Orders", "How do I track my order?", "Open My orders in your account, or use the Track order page with your order number and email."),
    ("Orders", "Can I cancel my order?", "Yes — orders can be cancelled from your order page until they are packed."),
    ("Payments", "Which payment methods do you accept?", "UPI, credit and debit cards, net banking and wallets via Razorpay, plus Cash on Delivery on eligible orders."),
    ("Payments", "Is it safe to pay online?", "Absolutely. Payments are handled by Razorpay with bank-grade security; we never see or store your card details."),
    ("Shipping", "How long does delivery take?", "Standard delivery takes 3–7 business days. Express delivery is available at checkout for faster shipping."),
    ("Returns", "What is your return policy?", "Unused items can be returned within 7 days of delivery. Start a return from your order page."),
    ("Product", "Is your jewellery gold or silver?", "COZY specialises in fashion and imitation jewellery made from brass, alloy and stainless steel with plated finishes — not precious metals."),
    ("Product", "Will the jewellery tarnish?", "With proper care our plated pieces keep their shine for a long time. Avoid water and perfume contact."),
]

TESTIMONIALS = [
    ("Ananya", "Bengaluru", "The pearl drops are even prettier in person. Packaging felt so premium — perfect for gifting!"),
    ("Riya", "Mumbai", "I wear the layered chain every day. Super light, doesn't irritate my skin and gets so many compliments."),
    ("Meera", "Kochi", "Ordered a festive set for a wedding — arrived in 3 days and looked stunning. Will order again."),
]


class Command(BaseCommand):
    help = "Load COZY demo catalogue and content (safe to run more than once)."

    def add_arguments(self, parser):
        parser.add_argument("--no-images", action="store_true", help="Do not generate product/banner images")
        parser.add_argument("--products", type=int, default=36, help="Approximate number of demo products")

    @transaction.atomic
    def handle(self, *args, **opts):
        images = not opts["no_images"]
        sync_roles_and_permissions()
        site = WebsiteSetting.load()
        site = WebsiteSetting.objects.get(pk=site.pk)
        site.contact_phone = site.contact_phone or "+91 90000 00000"
        site.address = site.address or "COZY Studio, Kerala, India"
        site.save()

        attrs = {"color": [], "material": [], "style": [], "size": []}
        for i, (name, code) in enumerate(COLORS):
            obj, _ = ProductAttribute.objects.get_or_create(attr_type="color", value=name,
                                                            defaults={"color_code": code, "display_order": i})
            attrs["color"].append(obj)
        for i, name in enumerate(MATERIALS):
            attrs["material"].append(ProductAttribute.objects.get_or_create(attr_type="material", value=name,
                                                                            defaults={"display_order": i})[0])
        for i, name in enumerate(STYLES):
            attrs["style"].append(ProductAttribute.objects.get_or_create(attr_type="style", value=name,
                                                                         defaults={"display_order": i})[0])
        for i, name in enumerate(SIZES):
            attrs["size"].append(ProductAttribute.objects.get_or_create(attr_type="size", value=name,
                                                                        defaults={"display_order": i})[0])

        categories = {}
        for order, (name, desc, subs) in enumerate(CATEGORIES):
            cat, created = Category.objects.get_or_create(name=name, defaults={"description": desc, "display_order": order})
            if images and not cat.image:
                cat.image.save(f"{cat.slug}.jpg", jewellery_image(name, order * 7, size=(700, 700)), save=False)
                cat.banner_image.save(f"{cat.slug}-banner.jpg", banner_image(order + 20), save=False)
                cat.save()
            categories[name] = cat
            for j, sub in enumerate(subs):
                SubCategory.objects.get_or_create(category=cat, name=sub, defaults={"display_order": j})
        self.stdout.write("✓ categories & attributes")

        rng = random.Random(42)
        target = opts["products"]
        created_count = 0
        cat_names = list(NOUNS.keys())
        i = 0
        while created_count < target and i < target * 3:
            cat_name = cat_names[i % len(cat_names)]
            noun = NOUNS[cat_name][(i // len(cat_names)) % len(NOUNS[cat_name])]
            name = f"{ADJECTIVES[i % len(ADJECTIVES)]} {noun}"
            sku = f"CZ-{cat_name[:3].upper()}-{1000 + i}"
            i += 1
            if Product.objects.filter(sku=sku).exists():
                continue
            cat = categories[cat_name]
            subs = list(cat.subcategories.all())
            price = Decimal(rng.choice([299, 349, 399, 449, 499, 599, 699, 799, 899, 999, 1199, 1499]))
            mrp = (price * Decimal(rng.choice(["1.0", "1.3", "1.5", "1.8", "2.0"]))).quantize(Decimal("1"))
            has_variants = cat_name in ("Rings",) and rng.random() < .6
            product = Product.objects.create(
                name=name, sku=sku, category=cat, subcategory=rng.choice(subs) if subs else None,
                short_description=f"{rng.choice(['Lightweight', 'Hand-finished', 'Anti-tarnish', 'Skin-friendly'])} "
                                  f"{noun.lower()} for {rng.choice(['everyday wear', 'parties', 'festive looks', 'gifting'])}.",
                description=(f"Meet the {name} — a COZY favourite designed to elevate any outfit.\n\n"
                             "Crafted from premium-quality base metal with a long-lasting plated finish, it's lightweight "
                             "enough for all-day comfort and pretty enough for every photo.\n\n"
                             "Arrives in a signature COZY pouch — ready to gift."),
                price=price, original_price=mrp if mrp > price else None,
                color=rng.choice(attrs["color"]), material=rng.choice(attrs["material"]), style=rng.choice(attrs["style"]),
                size_info=rng.choice(["Free size", "Length 4.5 cm", "Adjustable", "Chain 16 + 2 in"]),
                weight_grams=Decimal(rng.randint(3, 40)), has_variants=has_variants,
                is_featured=rng.random() < .3, is_trending=rng.random() < .3, is_bestseller=rng.random() < .3,
                is_new_arrival=rng.random() < .5, is_returnable=cat_name != "Earrings" or rng.random() < .5,
                tags=f"{noun.lower()}, {cat_name.lower()}, fashion jewellery, imitation jewellery",
                sold_count=rng.randint(0, 120), view_count=rng.randint(10, 900),
            )
            if images:
                for k in range(2):
                    ProductImage.objects.create(
                        product=product, is_primary=k == 0, display_order=k,
                        image=ContentFile(jewellery_image(cat_name, i * 3 + k).read(), name=f"{product.slug}-{k + 1}.jpg"),
                    )
            if has_variants:
                for j, size in enumerate(["6", "7", "8"]):
                    variant = ProductVariant.objects.create(
                        product=product, name=f"Size {size}", sku=f"{sku}-{size}", display_order=j,
                        size=ProductAttribute.objects.get(attr_type="size", value=size),
                    )
                    adjust_stock(get_inventory(product, variant), rng.randint(0, 15), StockHistory.STOCK_IN,
                                 note="Demo opening stock")
            else:
                qty = rng.choice([0, 3, 8, 15, 25, 40, 60])
                if qty:
                    adjust_stock(get_inventory(product), qty, StockHistory.STOCK_IN, note="Demo opening stock")
            created_count += 1
        self.stdout.write(f"✓ {created_count} products")

        ShippingMethod.objects.get_or_create(code="standard", defaults={
            "name": "Standard delivery", "description": "Tracked delivery across India", "charge": Decimal("59"),
            "min_days": 3, "max_days": 7, "display_order": 0})
        ShippingMethod.objects.get_or_create(code="express", defaults={
            "name": "Express delivery", "description": "Priority dispatch, metro cities", "charge": Decimal("149"),
            "free_above": Decimal("2499"), "min_days": 1, "max_days": 3, "cod_allowed": False, "display_order": 1})
        ShippingProvider.objects.get_or_create(code="manual", defaults={
            "name": "Self-managed courier", "tracking_url_template": ""})
        self.stdout.write("✓ shipping")

        now = timezone.now()
        Coupon.objects.get_or_create(code="WELCOME10", defaults={
            "description": "10% off your first order", "discount_type": "percent", "value": Decimal("10"),
            "max_discount": Decimal("200"), "first_order_only": True, "per_user_limit": 1})
        Coupon.objects.get_or_create(code="FLAT100", defaults={
            "description": "₹100 off on orders above ₹999", "discount_type": "fixed", "value": Decimal("100"),
            "min_order_value": Decimal("999"), "per_user_limit": 3})
        Coupon.objects.get_or_create(code="FESTIVE20", defaults={
            "description": "20% off the festive edit", "discount_type": "percent", "value": Decimal("20"),
            "max_discount": Decimal("500"), "min_order_value": Decimal("1499"), "campaign": "Festive season",
            "valid_to": now + timedelta(days=60), "per_user_limit": 2})
        self.stdout.write("✓ coupons")

        if images:
            hero = [
                ("New Season Edit", "Korean minimal & western statement pieces, freshly landed.", "NEW ARRIVALS",
                 "/shop/collections/new-arrivals/"),
                ("Sparkle for Every Celebration", "Festive jewellery sets crafted to shine.", "FESTIVE EDIT",
                 "/shop/category/jewellery-sets/"),
                ("Everyday Elegance", "Lightweight earrings you'll never want to take off.", "BESTSELLERS",
                 "/shop/collections/best-sellers/"),
            ]
            for idx, (title, sub, eyebrow, link) in enumerate(hero):
                if not Banner.objects.filter(title=title).exists():
                    b = Banner(title=title, subtitle=sub, eyebrow=eyebrow, link=link, position=Banner.HERO, display_order=idx,
                               text_align="left")
                    b.image.save(f"hero-{idx + 1}.jpg", banner_image(idx), save=False)
                    b.save()
            promos = [("The Gift Shop", "Ready-to-gift boxes for every occasion", "/shop/category/gift-items/"),
                      ("Under ₹499", "Everyday favourites at little prices", "/shop/?max_price=499")]
            for idx, (title, sub, link) in enumerate(promos):
                if not Banner.objects.filter(title=title).exists():
                    b = Banner(title=title, subtitle=sub, link=link, position=Banner.PROMO, display_order=idx)
                    b.image.save(f"promo-{idx + 1}.jpg", banner_image(idx + 10, size=(1200, 750)), save=False)
                    b.save()
            if not Banner.objects.filter(position=Banner.OFFER).exists():
                b = Banner(title="Festive Sale — up to 50% off", subtitle="Use code FESTIVE20 for an extra 20% off on orders above ₹1,499.",
                           eyebrow="LIMITED TIME", link="/shop/collections/offers/", button_text="Shop the sale",
                           position=Banner.OFFER)
                b.image.save("offer.jpg", banner_image(30, size=(1600, 600)), save=False)
                b.save()
            for k in range(6):
                if InstagramPost.objects.count() >= 6:
                    break
                post = InstagramPost(caption=f"Styled by our community #{k + 1}", display_order=k)
                post.image.save(f"insta-{k + 1}.jpg", jewellery_image(cat_names[k % len(cat_names)], 100 + k, size=(600, 600)),
                                save=False)
                post.save()
        self.stdout.write("✓ banners & social gallery")

        for order, (title, (column, content)) in enumerate(PAGES.items()):
            StaticPage.objects.get_or_create(title=title, defaults={"content": content, "footer_column": column,
                                                                    "display_order": order})
        for order, (cat, q, a) in enumerate(FAQS):
            FAQ.objects.get_or_create(question=q, defaults={"answer": a, "category": cat, "display_order": order})
        for order, (name, city, text) in enumerate(TESTIMONIALS):
            Testimonial.objects.get_or_create(name=name, defaults={"location": city, "text": text, "display_order": order})
        if not BlogPost.objects.exists():
            post = BlogPost(title="5 Ways to Layer Necklaces Like a Stylist",
                            excerpt="Mix lengths, textures and pendants for an effortless stacked look.",
                            content="<p>Layering is the easiest way to make simple outfits feel styled.</p><h2>1. Start with three lengths</h2><p>Choose a choker, a 16-inch chain and an 18-inch pendant.</p><h2>2. Mix textures</h2><p>Pair a smooth snake chain with pearls or a paperclip chain.</p><h2>3. Keep one hero piece</h2><p>Let one pendant stand out — keep the rest delicate.</p>",
                            tags="styling, necklaces", is_published=True)
            if images:
                post.cover_image.save("blog-layering.jpg", banner_image(40, size=(1400, 875)), save=False)
            post.save()
        ensure_home_sections()
        self.stdout.write(self.style.SUCCESS("COZY demo data loaded. Create an admin with: python manage.py createsuperuser"))
