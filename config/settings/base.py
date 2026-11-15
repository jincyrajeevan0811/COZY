"""
Base settings for the COZY fashion jewellery platform.

Environment-specific values are read from environment variables (see .env.example).
Never commit real secrets to source control.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional at runtime
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def env(key, default=None, required=False):
    value = os.environ.get(key, default)
    if required and (value is None or value == ""):
        raise ImproperlyConfigured(f"Environment variable {key} is required.")
    return value


def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(key, default=""):
    return [item.strip() for item in os.environ.get(key, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    # COZY apps
    "apps.core",
    "apps.accounts",
    "apps.categories",
    "apps.products",
    "apps.inventory",
    "apps.cart",
    "apps.wishlist",
    "apps.coupons",
    "apps.shipping",
    "apps.orders",
    "apps.payments",
    "apps.reviews",
    "apps.notifications",
    "apps.support",
    "apps.website_settings",
    "apps.dashboard",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

try:  # whitenoise is used in production; skip silently if not installed in dev
    import whitenoise  # noqa: F401
except ImportError:
    MIDDLEWARE.remove("whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.website_settings.context_processors.site_context",
            ],
            "builtins": ["apps.core.templatetags.cozy_tags"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database: MySQL preferred, SQLite for quick local development
# ---------------------------------------------------------------------------
DB_ENGINE = env("DB_ENGINE", "sqlite").lower()
if DB_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME", "cozy"),
            "USER": env("DB_USER", "cozy"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "home"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_RATE_LIMIT_ATTEMPTS = int(env("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW = int(env("LOGIN_RATE_LIMIT_WINDOW", "900"))  # seconds

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS reads the token for AJAX requests

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-in"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_IMAGE_UPLOAD_MB = int(env("MAX_IMAGE_UPLOAD_MB", "5"))

# ---------------------------------------------------------------------------
# Cache (Redis if configured, otherwise local memory)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "cozy"}}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "COZY <no-reply@cozy.local>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

# ---------------------------------------------------------------------------
# Payments (Razorpay) — start in TEST mode
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
UNPAID_ORDER_TIMEOUT_MINUTES = int(env("UNPAID_ORDER_TIMEOUT_MINUTES", "30"))

# ---------------------------------------------------------------------------
# Optional integrations (left blank unless configured)
# ---------------------------------------------------------------------------
WHATSAPP_API_URL = env("WHATSAPP_API_URL", "")
WHATSAPP_API_TOKEN = env("WHATSAPP_API_TOKEN", "")

DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", "secure-django-admin/")
DASHBOARD_URL = env("DASHBOARD_URL", "cozy-admin/")

MESSAGE_TAGS = {40: "danger"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
