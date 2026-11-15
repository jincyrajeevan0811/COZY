# COZY — Fashion Jewellery E-commerce Platform

COZY is a Django e-commerce platform for **fashion, imitation, Korean and western jewellery**
(not gold or precious metals). It has a premium storefront, real online purchasing with
Razorpay and Cash on Delivery, inventory and order management, and a role-based
**Super Admin Dashboard**. Regular content, catalogue and settings changes are made from
the dashboard, without code changes.

---

## Features

**Storefront**
- Announcement bar, sticky header and mega menu. Search has live autocomplete and remembers recent searches.
- Homepage sections are all managed from the dashboard (shown, hidden and reordered there):
  hero slider, service highlights, categories, new arrivals, promo tiles, best sellers,
  trending, offer strip, featured, discount picks, brand story, testimonials, Instagram gallery and newsletter.
- Product listing with filters: category, sub category, price, colour, material, style, discount, collection and stock.
  You can sort 7 ways, and listings are paginated. Product cards show badges, a hover image, quick view, add-to-bag and wishlist.
- Product page has:
  - a gallery with hover zoom
  - variants (size/colour) with their own price and stock
  - a PIN-code delivery check and estimated delivery date
  - reviews with photos and a "verified purchase" badge
  - related and recently viewed products
  - JSON-LD structured data and Open Graph tags
- Bag: works for guests and signed-in customers, and a guest bag is merged into the account at login.
  It also has stock validation, coupons, gift wrap, a free-shipping progress bar, GST and "save for later".
- Checkout on one page in steps: address book, shipping method, coupon, order summary, and payment by Razorpay or COD.
- Customer account: overview, orders, visual tracking timeline, PDF invoices, cancellations, returns,
  wishlist, addresses, offers, payment history, reviews, notifications, support tickets, profile and password.
- Email verification, password reset, login rate limiting, guest order tracking, blog, FAQ, CMS pages,
  contact form, sitemap.xml and robots.txt.

**Super Admin Dashboard** (`/cozy-admin/`, separate from Django admin)
- Overview KPIs, plus Chart.js charts drawn from real orders: daily, weekly, monthly and yearly sales,
  order status split, top categories and best products.
- Products: images (multi-upload, primary image), variants, SEO fields, flags, bulk actions and CSV/Excel bulk upload.
- Categories, sub categories and attributes (colours, materials, styles, sizes).
- Inventory: stock in/out/count adjustments and full movement history, with low-stock and out-of-stock alerts.
  Stock can never go negative.
- Orders:
  - filters and CSV export
  - status workflow with allowed transitions only
  - shipping and tracking (AWB) details
  - internal notes, invoice download and packing slip printing
- Returns (approve, reject, receive), refunds (through the Razorpay API or a manual reference), payments and abandoned carts with reminder emails.
- Customers (profile, orders, lifetime value, activate/deactivate), support tickets with replies and assignment, and review moderation.
- Coupons: percentage or fixed, scoped to products or categories, first order only, minimum value, usage and per-user limits, expiry and campaigns.
- Content: banners (with scheduling), homepage sections, pages, blog, testimonials, FAQs, social gallery, newsletter and website settings.
- Shipping methods, serviceable PIN codes and courier partners (modular courier integration).
- Reports for sales, orders, products, categories, customers, payments, returns, inventory and coupons, with CSV, Excel and PDF export.
- Staff users, **database-driven roles and permissions** and an audit log of every admin action.

**Roles**: Super Admin, Admin, Product Manager, Order Manager, Inventory Manager, Customer Support Staff,
Content Manager and Customer. Every dashboard view checks permissions on the server.
Only a Super Admin can grant Super Admin or edit roles.

---

## Project structure

```
cozy/
├── manage.py
├── config/                 # settings (base/dev/prod), urls, wsgi, asgi
├── apps/
│   ├── core/               # shared utils, validators, template tags, tests
│   ├── accounts/           # custom User, profile, addresses, roles & permissions (RBAC), auth
│   ├── categories/         # Category, SubCategory
│   ├── products/           # Product, images, variants, attributes, listing/search/detail
│   ├── inventory/          # Inventory, StockHistory, stock services
│   ├── cart/               # Cart, CartItem, totals engine
│   ├── wishlist/
│   ├── coupons/            # Coupon, CouponUsage
│   ├── shipping/           # methods, PIN codes, couriers, shipments
│   ├── orders/             # Order, items, status history, returns, checkout, invoices
│   ├── payments/           # Payment, Refund, Razorpay client, webhook
│   ├── reviews/
│   ├── notifications/      # in-app + email (+ optional WhatsApp)
│   ├── support/            # tickets & messages
│   ├── website_settings/   # settings singleton, banners, CMS, blog, FAQ, homepage, seed data
│   ├── dashboard/          # Super Admin dashboard, CRUD engine, audit log
│   └── reports/            # report builders and exporters
├── templates/              # base, storefront, accounts, products, cart, checkout, orders, dashboard, emails
├── static/                 # css/cozy.css, css/dashboard.css, js/cozy.js, js/dashboard.js
├── docker/entrypoint.sh
├── Dockerfile, docker-compose.yml, requirements.txt, .env.example
```

---

## Local setup (development)

Requirements: Python 3.11+, and MySQL 8 (optional, SQLite works out of the box).

```bash
git clone https://github.com/jincyrajeevan0811/COZY.git && cd COZY
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                             # on Windows/macOS without MySQL libs, remove mysqlclient for SQLite-only dev
cp .env.example .env

# First run only: generate migrations for all apps, then commit the generated files
python manage.py makemigrations accounts categories products inventory cart wishlist coupons shipping \
  orders payments reviews notifications support website_settings dashboard
python manage.py migrate            # also creates the default roles & permissions
python manage.py seed_cozy          # demo categories, ~36 products with images, banners, pages, coupons…
python manage.py createsuperuser    # your Super Admin (email + password)
python manage.py runserver
```

- Storefront: http://127.0.0.1:8000/
- COZY dashboard: http://127.0.0.1:8000/cozy-admin/
- Django admin (internal): http://127.0.0.1:8000/secure-django-admin/

During development, emails (verification, order confirmation, password reset) are printed in the terminal.

Run the tests with `python manage.py test`.

> **Migrations**: the repository ships without migration files. Run `makemigrations` once as
> shown above and **commit the generated `apps/*/migrations/0001_initial.py` files** before
> deploying, so every environment shares the same schema history.

### Using MySQL

```sql
CREATE DATABASE cozy CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cozy'@'%' IDENTIFIED BY 'strong-password';
GRANT ALL PRIVILEGES ON cozy.* TO 'cozy'@'%';
```
Set `DB_ENGINE=mysql` and the `DB_*` values in `.env`. The dashboard charts group sales by
day/week/month in the Asia/Kolkata timezone, so load MySQL's timezone tables once:
`mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql`.

---

## Payments (Razorpay)

1. Create a Razorpay account and copy the **test** keys (`rzp_test_…`) into `.env`.
2. Add a webhook at `https://your-domain/payments/webhook/razorpay/` for `payment.captured`
   and `payment.failed`, and put its secret in `RAZORPAY_WEBHOOK_SECRET`.
3. Test thoroughly with Razorpay test cards and UPI before switching to live keys.

How it is secured:
- Card and UPI details never touch the COZY server.
- An order is marked paid only after the HMAC signature has been verified on the server
  (on the checkout callback and on the webhook). Both paths are idempotent.
- Stock is reserved when the order is created. `python manage.py release_unpaid_orders`
  (run every 10–15 minutes by cron, or by the `scheduler` service in docker-compose) cancels
  unpaid online orders and returns their stock.
- If Razorpay keys are missing, online payment is hidden and only COD is offered.

---

## Production deployment

```bash
cp .env.example .env    # set DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS,
                        # SITE_URL, DB_PASSWORD, DB_ROOT_PASSWORD, email SMTP, Razorpay keys
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_cozy     # optional demo content
```

Put a reverse proxy such as Nginx or Caddy in front for HTTPS, and serve `/media/` from the `media`
volume (or move media to S3-compatible storage). Static files are served by WhiteNoise.

Without Docker, run `gunicorn config.wsgi:application` with `DJANGO_SETTINGS_MODULE=config.settings.prod`,
then `python manage.py collectstatic`, and schedule `release_unpaid_orders` with cron.

---

## Security checklist

- [x] Secrets only come from environment variables, and `prod` refuses to start with the default key
- [x] CSRF on every form and AJAX call. Templates auto-escape, and the ORM is used everywhere (no raw SQL)
- [x] RBAC checked on the server for every dashboard view. Customers can only see their own orders and addresses
- [x] Only Super Admin can grant Super Admin or edit roles. All admin actions are written to the audit log
- [x] Login rate limiting, secure password hashing, password validators and email verification
- [x] Uploads are checked for file extension, size (5 MB) and real image content with Pillow, then re-encoded
- [x] Razorpay signatures are verified on the server, with idempotent payment capture. Cards are never stored
- [x] HTTPS redirect, HSTS, secure cookies, X-Frame-Options DENY, nosniff and a strict referrer policy (prod)
- [x] Open-redirect protection on all `next` parameters
- [x] The dashboard and Django admin URLs can be changed in `.env`
- [ ] Before go-live: switch to live Razorpay keys, set up SMTP, back up the database, monitor errors (for example with Sentry)

## Performance notes

- Database indexes on hot lookups. `select_related` and `prefetch_related` in listings, orders and the dashboard.
- Images are resized and compressed on upload, and lazy-loaded in the storefront.
- Site settings, menus and footer pages are cached (Redis when `REDIS_URL` is set).
- Pagination is used everywhere, and static files are served compressed and hashed through WhiteNoise.

## Integrations kept optional and configurable

- **Couriers**: add a class in `apps/shipping/providers.py`, then select it on a courier partner in the dashboard.
- **WhatsApp**: set `WHATSAPP_API_URL` and `WHATSAPP_API_TOKEN` to send order updates through your provider.
- **Analytics**: add the Google Analytics or Facebook Pixel ID in Website settings.
