import io
import logging
import secrets
import string
from decimal import ROUND_HALF_UP, Decimal

from django.core.files.base import ContentFile
from django.utils.text import slugify

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def money(value):
    """Round a value to two decimal places using commercial rounding."""
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def unique_slugify(instance, value, slug_field="slug", max_length=200):
    base = slugify(value)[: max_length - 8] or "item"
    slug = base
    model = instance.__class__
    counter = 2
    while model._default_manager.filter(**{slug_field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def random_code(length=6, alphabet=string.ascii_uppercase + string.digits):
    return "".join(secrets.choice(alphabet) for _ in range(length))


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get(
        "accept", ""
    )


def optimize_image(field_file, max_size=1600, quality=85):
    """Resize and recompress an uploaded image in-place (keeps aspect ratio).

    Called from model.save() for newly uploaded images only.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        return
    if not field_file or getattr(field_file, "_committed", True):
        return
    try:
        field_file.seek(0)
        img = Image.open(field_file)
        img = ImageOps.exif_transpose(img)
        fmt = (img.format or "JPEG").upper()
        if fmt not in ("JPEG", "PNG", "WEBP"):
            fmt = "JPEG"
        if fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_size, max_size))
        buffer = io.BytesIO()
        save_kwargs = {"optimize": True}
        if fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = quality
        img.save(buffer, format=fmt, **save_kwargs)
        name = field_file.name.rsplit("/", 1)[-1]
        field_file.save(name, ContentFile(buffer.getvalue()), save=False)
    except Exception:  # never block a save because of optimisation
        logger.exception("Image optimisation failed for %s", getattr(field_file, "name", "?"))


def safe_next_url(request, default="/"):
    """Return ?next= / POST next only if it points to this site (prevents open redirects)."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default
