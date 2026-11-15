"""
A small, permission-aware CRUD engine for the COZY dashboard.

Each simple module (banners, pages, coupons, shipping methods …) is declared once
with a CrudConfig. The engine generates list / create / edit / delete views that
share consistent premium templates, server-side RBAC checks, search, filters,
pagination and audit logging.
"""
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.db.models.fields.files import FieldFile
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.accounts.rbac import permission_required
from apps.core.templatetags.cozy_tags import inr

from .audit import log_activity


class CrudConfig:
    def __init__(self, *, name, model, form_class, permission, title, columns, singular=None, icon="bi-grid",
                 search_fields=(), filters=(), queryset=None, can_create=True, can_delete=True, per_page=25,
                 description="", after_save=None, form_template="dashboard/crud/form.html"):
        self.name = name
        self.model = model
        self.form_class = form_class
        self.permission = permission
        self.title = title
        self.singular = singular or model._meta.verbose_name.title()
        self.columns = columns  # list of (label, accessor[, kind])
        self.icon = icon
        self.search_fields = search_fields
        self.filters = filters  # list of (lookup, label, [(value, label), ...])
        self.queryset = queryset
        self.can_create = can_create
        self.can_delete = can_delete
        self.per_page = per_page
        self.description = description
        self.after_save = after_save
        self.form_template = form_template

    def get_queryset(self):
        return self.queryset() if callable(self.queryset) else self.model._default_manager.all()

    def url(self, action, pk=None):
        name = f"dashboard:{self.name}_{action}"
        return reverse(name, args=[pk]) if pk is not None else reverse(name)


def _resolve(obj, accessor):
    if callable(accessor):
        return accessor(obj)
    value = obj
    for part in accessor.split("__"):
        if value is None:
            return None
        value = getattr(value, part, None)
        if callable(value) and not hasattr(value, "all"):
            value = value()
    return value


def render_cell(obj, accessor, kind=None):
    value = _resolve(obj, accessor)
    if kind == "money":
        return inr(value)
    if kind == "image" or isinstance(value, FieldFile):
        if value:
            return format_html('<img src="{}" class="table-thumb" alt="" loading="lazy">', value.url)
        return format_html('<span class="table-thumb placeholder-thumb"><i class="bi bi-image"></i></span>')
    if kind == "color" and value:
        return format_html('<span class="swatch" style="background:{}"></span> {}', value, value)
    if isinstance(value, bool):
        if value:
            return format_html('<span class="badge rounded-pill badge-soft-success">Yes</span>')
        return format_html('<span class="badge rounded-pill badge-soft-secondary">No</span>')
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if value is None or value == "":
        return format_html('<span class="text-muted">—</span>')
    if kind == "strong":
        return format_html("<strong>{}</strong>", value)
    return str(value)


def _apply_filters(cfg, request, qs):
    active = {}
    for lookup, _label, _choices in cfg.filters:
        val = request.GET.get(lookup)
        if val in (None, ""):
            continue
        if val in ("true", "false"):
            qs = qs.filter(**{lookup: val == "true"})
        else:
            qs = qs.filter(**{lookup: val})
        active[lookup] = val
    q = (request.GET.get("q") or "").strip()
    if q and cfg.search_fields:
        cond = Q()
        for field in cfg.search_fields:
            cond |= Q(**{f"{field}__icontains": q})
        qs = qs.filter(cond)
    return qs, active, q


def build_crud_views(cfg):
    @permission_required(cfg.permission)
    def list_view(request):
        qs, active, q = _apply_filters(cfg, request, cfg.get_queryset())
        page = Paginator(qs, cfg.per_page).get_page(request.GET.get("page"))
        rows = []
        for obj in page.object_list:
            cells = [render_cell(obj, col[1], col[2] if len(col) > 2 else None) for col in cfg.columns]
            rows.append({"obj": obj, "cells": cells, "edit_url": cfg.url("edit", obj.pk),
                         "delete_url": cfg.url("delete", obj.pk) if cfg.can_delete else ""})
        return render(request, "dashboard/crud/list.html", {
            "cfg": cfg,
            "headers": [c[0] for c in cfg.columns],
            "rows": rows,
            "page_obj": page,
            "q": q,
            "active_filters": active,
            "create_url": cfg.url("create") if cfg.can_create else "",
            "filters": [(lookup, label, [(str(v), l) for v, l in (choices() if callable(choices) else choices)])
                        for lookup, label, choices in cfg.filters],
        })

    @permission_required(cfg.permission)
    def form_view(request, pk=None):
        instance = get_object_or_404(cfg.get_queryset(), pk=pk) if pk else None
        if pk is None and not cfg.can_create:
            return redirect(cfg.url("list"))
        form = cfg.form_class(request.POST or None, request.FILES or None, instance=instance)
        if request.method == "POST" and form.is_valid():
            obj = form.save()
            if cfg.after_save:
                cfg.after_save(request, obj)
            log_activity(request, "update" if pk else "create", obj)
            messages.success(request, f"{cfg.singular} saved successfully.")
            if "save_add" in request.POST and cfg.can_create:
                return redirect(cfg.url("create"))
            return redirect(cfg.url("list"))
        return render(request, cfg.form_template, {
            "cfg": cfg, "form": form, "object": instance, "list_url": cfg.url("list"),
            "delete_url": cfg.url("delete", instance.pk) if (instance and cfg.can_delete) else "",
        })

    @permission_required(cfg.permission)
    @require_POST
    def delete_view(request, pk):
        if not cfg.can_delete:
            return redirect(cfg.url("list"))
        obj = get_object_or_404(cfg.get_queryset(), pk=pk)
        label = str(obj)
        try:
            log_activity(request, "delete", obj)
            obj.delete()
            if cfg.after_save:
                cfg.after_save(request, None)
            messages.success(request, f"{cfg.singular} “{label}” deleted.")
        except ProtectedError:
            messages.error(request, f"“{label}” is in use and cannot be deleted. Deactivate it instead.")
        return redirect(cfg.url("list"))

    return [
        path(f"{cfg.name}/", list_view, name=f"{cfg.name}_list"),
        path(f"{cfg.name}/new/", form_view, name=f"{cfg.name}_create"),
        path(f"{cfg.name}/<int:pk>/edit/", form_view, name=f"{cfg.name}_edit"),
        path(f"{cfg.name}/<int:pk>/delete/", delete_view, name=f"{cfg.name}_delete"),
    ]
