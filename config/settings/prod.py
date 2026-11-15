from .base import *  # noqa: F401,F403
from .base import STORAGES, env, env_bool

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
if SECRET_KEY.startswith("insecure"):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set a strong DJANGO_SECRET_KEY in production.")

# HTTPS / cookies
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
