from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    REDIS_URL=(str, ""),
    OPENAI_API_KEY=(str, ""),
    # Per-user daily chat message cap and a global monthly hard ceiling.
    # The endpoint now spends *our* OpenAI key, so these are the only thing
    # between us and an unbounded bill — see apps/api/chat.py.
    CHAT_DAILY_USER_LIMIT=(int, 50),
    CHAT_MONTHLY_GLOBAL_LIMIT=(int, 20_000),
    # Persist each chat's search/grounding trace for offline quality
    # review (apps/api/models.ChatTrace). Off = no rows written.
    CHAT_TRACE_CAPTURE=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Server-side OpenAI key for the /api/chat endpoint (no longer BYOK).
OPENAI_API_KEY = env("OPENAI_API_KEY")
CHAT_DAILY_USER_LIMIT = env("CHAT_DAILY_USER_LIMIT")
CHAT_MONTHLY_GLOBAL_LIMIT = env("CHAT_MONTHLY_GLOBAL_LIMIT")
CHAT_TRACE_CAPTURE = env("CHAT_TRACE_CAPTURE")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "apps.accounts",
    "apps.corpus",
    "apps.api",
    "apps.citations",
    "apps.ingestion_iowa_code",
    "apps.ingestion_iowa_rules",
    "apps.mcp_server",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves collected static (Django admin + the built React
    # app) straight from the web process — App Platform has no shared
    # static volume. Must sit directly after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
# Persistent connections in prod (App Platform → Managed PG). Managed
# Postgres requires TLS; sslmode is also accepted directly in DATABASE_URL.
if not DEBUG:
    DATABASES["default"]["CONN_MAX_AGE"] = 60
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault(
        "sslmode", env("DATABASE_SSLMODE", default="require")
    )

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django admin's own static is hashed/compressed via collectstatic +
# WhiteNoise's manifest storage, served at STATIC_URL (/static/).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
# The frontend used to be a Vite SPA served by WhiteNoise from
# frontend/dist; we've moved to a separate Next.js component (see
# chat-frontend/) routed to "/" by App Platform. Django no longer serves
# any SPA — just /api/* and /admin/*. WhiteNoise continues to serve the
# Django admin's own static (collected to STATIC_ROOT via collectstatic).

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# Cache — Redis in prod (App Platform runs multiple processes and wipes
# LocMem on every deploy; the per-user chat quota and API rate limiter are
# cache-backed, so they MUST share a durable store to actually hold).
# Falls back to LocMem when REDIS_URL is unset (local dev / tests).
# ---------------------------------------------------------------------------
if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ---------------------------------------------------------------------------
# Production security — only enforced when DEBUG is off, so local dev over
# http://localhost is unaffected. App Platform terminates TLS at its edge
# and forwards X-Forwarded-Proto, hence SECURE_PROXY_SSL_HEADER.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# Django's default LOGGING config routes 500-error tracebacks to the
# 'mail_admins' handler, which silently drops them when email isn't
# configured — so production 500s are invisible. Pipe django.request
# straight to stderr/stdout so gunicorn's runtime logs capture the
# traceback and we can debug without flipping DEBUG=True.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
