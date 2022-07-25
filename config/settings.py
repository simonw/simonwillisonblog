import os
import dj_database_url
import urllib.parse


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET") or "dev-secret-s(p7%ue-l6r^&@y63p*ix*1"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(os.environ.get("DJANGO_DEBUG"))
INTERNAL_IPS = ("127.0.0.1",)

STAGING = bool(os.environ.get("STAGING"))

# Django SQL Dashboard
DASHBOARD_ROW_LIMIT = 200

# Cloudflare details
CLOUDFLARE_EMAIL = os.environ.get("CLOUDFLARE_EMAIL", "")
CLOUDFLARE_TOKEN = os.environ.get("CLOUDFLARE_TOKEN", "")
CLOUDFLARE_ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID", "")

# Google Analytics
GOOGLE_ANALYTICS_ID = os.environ.get("GOOGLE_ANALYTICS_ID")

# SESSION_COOKIE_DOMAIN
if os.environ.get("SESSION_COOKIE_DOMAIN"):
    SESSION_COOKIE_DOMAIN = os.environ["SESSION_COOKIE_DOMAIN"]
if os.environ.get("SESSION_COOKIE_SECURE"):
    SESSION_COOKIE_SECURE = True

# Application definition

INSTALLED_APPS = (
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_sql_dashboard",
    "blog",
    "redirects",
    "feedstats",
)

MIDDLEWARE = (
    "redirects.middleware.redirect_middleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
#    "django.middleware.clickjacking.XFrameOptionsMiddleware",
)
if DEBUG:
    MIDDLEWARE = ("debug_toolbar.middleware.DebugToolbarMiddleware",) + MIDDLEWARE
    INSTALLED_APPS += ("debug_toolbar",)
else:
    MIDDLEWARE += ("whitenoise.middleware.WhiteNoiseMiddleware",)


# Sentry
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    INSTALLED_APPS += ("raven.contrib.django.raven_compat",)
    RAVEN_CONFIG = {
        "dsn": SENTRY_DSN,
        "release": os.environ.get("HEROKU_SLUG_COMMIT", ""),
    }


ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "templates/"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "blog.context_processors.all",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "simonwillisonblog",
    },
    "dashboard": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "simonwillisonblog",
        "OPTIONS": {
            "options": "-c default_transaction_read_only=on -c statement_timeout=3000"
        },
    },
}

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DASHBOARD_ENABLE_FULL_EXPORT = True

if "DATABASE_URL" in os.environ:
    # Parse database configuration from $DATABASE_URL
    DATABASES["default"] = dj_database_url.config()
    DATABASES["dashboard"] = dj_database_url.config()
    DATABASES["dashboard"]["OPTIONS"] = {
        "options": "-c default_transaction_read_only=on -c statement_timeout=3000"
    }

if "DISABLE_AUTOCOMMIT" in os.environ:
    DATABASES["default"]["AUTOCOMMIT"] = False

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Allow all host headers
ALLOWED_HOSTS = ["*"]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"

STATICFILES_DIRS = (os.path.join(BASE_DIR, "static/"),)

# Simplified static file serving.
# https://warehouse.python.org/project/whitenoise/
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# urls.W002
# Your URL pattern '^/?archive/(\d{4})/(\d{2})/(\d{2})/$' has a regex beginning
# with a '/'. Remove this slash as it is unnecessary. If this pattern is
# targeted in an include(), ensure the include() pattern has a trailing '/'.
# This is deliberate (we get hits to //archive/ for some reason) so I'm
# silencing the warning:
SILENCED_SYSTEM_CHECKS = ("urls.W002",)


# Caching
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    redis_url = urllib.parse.urlparse(REDIS_URL)
    CACHES["default"] = {
        "BACKEND": "redis_cache.RedisCache",
        "LOCATION": "{0}:{1}".format(redis_url.hostname, redis_url.port),
        "OPTIONS": {
            "PASSWORD": redis_url.password,
            "DB": 0,
        },
        "VERSION": 2,
    }
