from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]

image_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def validate_image_file(file):
    """Validate size and real image content for uploads (not only the extension)."""
    max_mb = getattr(settings, "MAX_IMAGE_UPLOAD_MB", 5)
    if file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Image must be smaller than {max_mb} MB.")
    try:
        from PIL import Image

        pos = file.tell() if hasattr(file, "tell") else 0
        img = Image.open(file)
        img.verify()
        if hasattr(file, "seek"):
            file.seek(pos)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Upload a valid image file (JPG, PNG or WEBP).") from exc


IMAGE_VALIDATORS = [image_extension_validator, validate_image_file]
