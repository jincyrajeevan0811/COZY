"""Product management (with images, variants, bulk upload) and inventory management."""
import csv
import io
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, ProtectedError, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.rbac import permission_required
from apps.categories.models import Category, SubCategory
from apps.inventory.models import Inventory, StockHistory
from apps.inventory.services import InsufficientStock, adjust_stock, get_inventory, set_stock
from apps.products.models import Product, ProductAttribute, ProductImage
from apps.website_settings.context_processors import clear_site_caches

from .audit import log_activity
from .forms import BulkProductUploadForm, ProductForm, ProductImageFormSet, ProductVariantFormSet, StockAdjustForm


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
@permission_required("products.manage", "inventory.view")
def product_list(request):
    qs = Product.objects.select_related("category", "subcategory").prefetch_related("images").with_stock()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(tags__icontains=q))
    if request.GET.get("category"):
        qs = qs.filter(category_id=request.GET["category"])
    status = request.GET.get("status")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    flag = request.GET.get("flag")
    if flag in ("is_featured", "is_trending", "is_bestseller", "is_new_arrival"):
        qs = qs.filter(**{flag: True})
    stock = request.GET.get("stock")
    if stock == "out":
        qs = qs.filter(Q(stock_total__lte=0) | Q(stock_total__isnull=True))
    elif stock == "low":
        qs = qs.filter(stock_total__gt=0, stock_total__lte=5)
    sort = request.GET.get("sort", "-created_at")
    if sort.lstrip("-") in ("created_at", "name", "price", "sold_count", "stock_total"):
        qs = qs.order_by(sort)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/products/list.html", {
        "page_obj": page, "q": q, "categories": Category.objects.all(),
    })


def _save_product_children(request, product, image_fs, variant_fs, form):
    image_fs.instance = product
    image_fs.save()
    for upload in form.cleaned_data.get("upload_images") or []:
        ProductImage.objects.create(product=product, image=upload)
    variant_fs.instance = product
    variant_fs.save()
    initial = form.cleaned_data.get("initial_stock")
    if initial and not product.has_variants:
        adjust_stock(get_inventory(product), initial, StockHistory.STOCK_IN, user=request.user, note="Opening stock")


@permission_required("products.manage")
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    image_fs = ProductImageFormSet(request.POST or None, request.FILES or None, instance=product, prefix="images")
    variant_fs = ProductVariantFormSet(request.POST or None, instance=product, prefix="variants")
    if request.method == "POST":
        if form.is_valid() and image_fs.is_valid() and variant_fs.is_valid():
            with transaction.atomic():
                obj = form.save()
                _save_product_children(request, obj, image_fs, variant_fs, form)
            clear_site_caches()
            log_activity(request, "update" if pk else "create", obj)
            messages.success(request, f"Product “{obj.name}” saved.")
            if "save_continue" in request.POST:
                return redirect("dashboard:product_edit", pk=obj.pk)
            return redirect("dashboard:product_list")
        messages.error(request, "Please fix the errors below.")
    inventories = product.inventories.select_related("variant") if product else []
    return render(request, "dashboard/products/form.html", {
        "form": form, "image_fs": image_fs, "variant_fs": variant_fs, "product": product,
        "inventories": inventories,
        "subcategory_map": json.dumps({str(s.pk): s.category_id for s in SubCategory.objects.all()}),
    })


@permission_required("products.manage")
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    log_activity(request, "update", product, f"{'Activated' if product.is_active else 'Deactivated'} product")
    messages.success(request, f"“{product.name}” {'activated' if product.is_active else 'deactivated'}.")
    return redirect(request.META.get("HTTP_REFERER") or "dashboard:product_list")


@permission_required("products.manage")
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = str(product)
    if product.order_items.exists():
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        messages.warning(request, f"“{name}” has orders, so it was deactivated instead of deleted.")
    else:
        try:
            log_activity(request, "delete", product)
            product.delete()
            messages.success(request, f"“{name}” deleted.")
        except ProtectedError:
            messages.error(request, "This product is referenced elsewhere and cannot be deleted.")
    return redirect("dashboard:product_list")


@permission_required("products.manage")
@require_POST
def product_bulk_action(request):
    ids = request.POST.getlist("ids")
    action = request.POST.get("action")
    qs = Product.objects.filter(pk__in=ids)
    if action == "activate":
        n = qs.update(is_active=True)
    elif action == "deactivate":
        n = qs.update(is_active=False)
    elif action in ("feature", "trending", "bestseller"):
        field = {"feature": "is_featured", "trending": "is_trending", "bestseller": "is_bestseller"}[action]
        n = qs.update(**{field: True})
    else:
        messages.error(request, "Choose an action.")
        return redirect("dashboard:product_list")
    log_activity(request, "update", None, f"Bulk {action} on {n} products", object_type="Product")
    messages.success(request, f"{n} product(s) updated.")
    return redirect("dashboard:product_list")


TEMPLATE_COLUMNS = [
    "name", "sku", "category", "subcategory", "price", "original_price", "stock", "color", "material", "style",
    "short_description", "description", "tags", "is_featured", "is_trending", "is_bestseller", "is_new_arrival",
    "is_active",
]


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _read_rows(upload):
    if upload.name.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(upload, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h or "").strip().lower() for h in rows[0]]
        return [dict(zip(headers, [("" if v is None else v) for v in r])) for r in rows[1:] if any(r)]
    text = upload.read().decode("utf-8-sig", errors="ignore")
    return [{(k or "").strip().lower(): v for k, v in row.items()} for row in csv.DictReader(io.StringIO(text))]


def _attr(attr_type, value):
    value = str(value or "").strip()
    if not value:
        return None
    obj, _ = ProductAttribute.objects.get_or_create(attr_type=attr_type, value=value)
    return obj


@permission_required("products.manage")
def product_bulk_upload(request):
    form = BulkProductUploadForm(request.POST or None, request.FILES or None)
    results = None
    if request.method == "POST" and form.is_valid():
        created = updated = skipped = 0
        errors = []
        try:
            rows = _read_rows(form.cleaned_data["file"])
        except Exception as exc:  # malformed workbook / encoding
            rows = []
            errors.append(f"Could not read file: {exc}")
        for line, row in enumerate(rows, start=2):
            try:
                with transaction.atomic():
                    sku = str(row.get("sku", "")).strip().upper()
                    name = str(row.get("name", "")).strip()
                    if not sku or not name:
                        raise ValueError("name and sku are required")
                    cat_name = str(row.get("category", "")).strip()
                    if not cat_name:
                        raise ValueError("category is required")
                    category, _ = Category.objects.get_or_create(name=cat_name)
                    sub = None
                    if str(row.get("subcategory", "")).strip():
                        sub, _ = SubCategory.objects.get_or_create(category=category, name=str(row["subcategory"]).strip())
                    price = Decimal(str(row.get("price", "")).strip())
                    original = str(row.get("original_price", "")).strip()
                    product = Product.objects.filter(sku=sku).first()
                    if product and not form.cleaned_data["update_existing"]:
                        skipped += 1
                        continue
                    is_new = product is None
                    product = product or Product(sku=sku)
                    product.name = name
                    product.category = category
                    product.subcategory = sub
                    product.price = price
                    product.original_price = Decimal(original) if original else None
                    product.color = _attr(ProductAttribute.COLOR, row.get("color"))
                    product.material = _attr(ProductAttribute.MATERIAL, row.get("material"))
                    product.style = _attr(ProductAttribute.STYLE, row.get("style"))
                    for field in ("short_description", "description", "tags"):
                        if row.get(field) not in (None, ""):
                            setattr(product, field, str(row[field]))
                    for flag in ("is_featured", "is_trending", "is_bestseller", "is_new_arrival"):
                        if row.get(flag) not in (None, ""):
                            setattr(product, flag, _truthy(row[flag]))
                    if row.get("is_active") not in (None, ""):
                        product.is_active = _truthy(row["is_active"])
                    product.full_clean(exclude=["slug"])
                    product.save()
                    stock = str(row.get("stock", "")).strip()
                    if stock != "":
                        set_stock(get_inventory(product), int(float(stock)), user=request.user, note="Bulk upload")
                    created += is_new
                    updated += not is_new
            except (ValueError, InvalidOperation, Exception) as exc:  # report and continue with next row
                errors.append(f"Row {line}: {exc}")
        clear_site_caches()
        log_activity(request, "create", None, f"Bulk upload: {created} created, {updated} updated", object_type="Product")
        results = {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:50]}
        if not errors:
            messages.success(request, f"Upload complete: {created} created, {updated} updated.")
    return render(request, "dashboard/products/bulk_upload.html", {"form": form, "results": results,
                                                                   "columns": TEMPLATE_COLUMNS})


@permission_required("products.manage")
def product_upload_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="cozy-product-template.csv"'
    writer = csv.writer(response)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(["Pearl Drop Earrings", "CZ-EAR-001", "Earrings", "Drop Earrings", "499", "899", "25", "Gold",
                     "Alloy", "Korean", "Minimal pearl drops", "Lightweight pearl drop earrings.", "pearl,korean",
                     "yes", "no", "no", "yes", "yes"])
    return response


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
@permission_required("inventory.manage", "inventory.view")
def inventory_list(request):
    qs = Inventory.objects.select_related("product", "variant", "product__category").filter(
        Q(variant__isnull=True, product__has_variants=False) | Q(variant__isnull=False, product__has_variants=True)
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(variant__sku__icontains=q)
                       | Q(variant__name__icontains=q))
    level = request.GET.get("level")
    if level == "out":
        qs = qs.filter(quantity=0)
    elif level == "low":
        qs = qs.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
    elif level == "ok":
        qs = qs.filter(quantity__gt=F("low_stock_threshold"))
    if request.GET.get("category"):
        qs = qs.filter(product__category_id=request.GET["category"])
    totals = qs.aggregate(units=Sum("quantity"))
    page = Paginator(qs.order_by("quantity", "product__name"), 30).get_page(request.GET.get("page"))
    return render(request, "dashboard/inventory/list.html", {
        "page_obj": page, "q": q, "level": level, "totals": totals, "adjust_form": StockAdjustForm(),
        "categories": Category.objects.all(),
    })


@permission_required("inventory.manage")
@require_POST
def inventory_adjust(request, pk):
    inventory = get_object_or_404(Inventory, pk=pk)
    form = StockAdjustForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid stock adjustment.")
        return redirect(request.META.get("HTTP_REFERER") or "dashboard:inventory_list")
    data = form.cleaned_data
    try:
        if data["mode"] == "in":
            adjust_stock(inventory, data["quantity"], StockHistory.STOCK_IN, request.user, data["reference"], data["note"])
        elif data["mode"] == "out":
            adjust_stock(inventory, -data["quantity"], StockHistory.STOCK_OUT, request.user, data["reference"], data["note"])
        else:
            set_stock(inventory, data["quantity"], user=request.user, note=data["note"] or "Stock count")
        if data.get("low_stock_threshold") is not None:
            Inventory.objects.filter(pk=inventory.pk).update(low_stock_threshold=data["low_stock_threshold"])
        log_activity(request, "update", inventory, f"Stock {data['mode']} {data['quantity']}")
        messages.success(request, f"Stock updated for {inventory.label}.")
    except InsufficientStock as exc:
        messages.error(request, str(exc))
    return redirect(request.META.get("HTTP_REFERER") or "dashboard:inventory_list")


@permission_required("inventory.manage", "inventory.view")
def stock_history(request):
    qs = StockHistory.objects.select_related("inventory__product", "inventory__variant", "user")
    if request.GET.get("inventory"):
        qs = qs.filter(inventory_id=request.GET["inventory"])
    if request.GET.get("type"):
        qs = qs.filter(movement_type=request.GET["type"])
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(inventory__product__name__icontains=q) | Q(reference__icontains=q)
                       | Q(inventory__product__sku__icontains=q))
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(request, "dashboard/inventory/history.html", {
        "page_obj": page, "types": StockHistory.TYPE_CHOICES, "q": q,
    })
