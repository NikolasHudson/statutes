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
    # Docling extraction microservice (its own App Platform component). The
    # Verify Document upload path POSTs PDF/DOCX bytes here for text
    # extraction. Empty = no service configured, so PDF/DOCX upload returns a
    # clean "not available" error and paste/.txt still work.
    DOCLING_SERVICE_URL=(str, ""),
    # Docling conversion is CPU-bound and can take tens of seconds on a big
    # brief; give it room before giving up on the upstream call.
    DOCLING_TIMEOUT=(int, 120),
    # Confidentiality: traces hold the user's verbatim question + answer, so
    # they are not kept indefinitely. ``purge_chat_traces`` deletes rows older
    # than this many days (0 disables the purge).
    CHAT_TRACE_RETENTION_DAYS=(int, 7),
)
environ.Env.read_env(BASE_DIR / ".env")

# No default: a missing SECRET_KEY must fail loudly at startup rather than
# silently booting with a weak/blank key. NOTE (finding #38): App Platform
# preserves the existing SECRET value when the spec omits ``value:``; a spec
# re-paste from ``doctl`` (which inlines secrets) can WIPE it, invalidating all
# sessions/CSRF tokens. The deploy-side guard for that lives in the App
# Platform spec (.do/app.yaml — owned by the deploy agent); see the SECRET_KEY
# block there and DEPLOY.md before rotating.
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Server-side OpenAI key for the /api/chat endpoint (no longer BYOK).
OPENAI_API_KEY = env("OPENAI_API_KEY")
CHAT_DAILY_USER_LIMIT = env("CHAT_DAILY_USER_LIMIT")
CHAT_MONTHLY_GLOBAL_LIMIT = env("CHAT_MONTHLY_GLOBAL_LIMIT")
CHAT_TRACE_CAPTURE = env("CHAT_TRACE_CAPTURE")
CHAT_TRACE_RETENTION_DAYS = env("CHAT_TRACE_RETENTION_DAYS")
DOCLING_SERVICE_URL = env("DOCLING_SERVICE_URL")
DOCLING_TIMEOUT = env("DOCLING_TIMEOUT")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    # Brute-force login throttle / lockout (findings #6, #15). Keyed on
    # IP+username, cache-backed, configured in the AXES_* block below.
    "axes",
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
    # AxesMiddleware must come LAST: it wraps the response so a lockout that
    # surfaces as a PermissionDenied during authenticate() is turned into the
    # configured lockout response. It needs request.user, so it sits after
    # AuthenticationMiddleware. (findings #6/#15)
    "axes.middleware.AxesMiddleware",
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

# ---------------------------------------------------------------------------
# Authentication backends + brute-force lockout (django-axes; findings #6/#15)
# ---------------------------------------------------------------------------
# AxesStandaloneBackend must be FIRST: on a locked-out IP+account it raises
# PermissionDenied, which makes django.contrib.auth.authenticate() short-circuit
# and return None (a generic failure) before any password is checked. The
# default ModelBackend follows for the real credential check. "Standalone"
# (vs AxesBackend) means it does NOT itself authenticate — it only gates — so we
# keep ModelBackend explicitly in the chain.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Lockout policy. The login view (apps/api/accounts.py) calls
# authenticate(request, email=..., password=...), so axes reads the attempted
# identifier from the ``email`` credential rather than the default ``username``.
AXES_FAILURE_LIMIT = env("AXES_FAILURE_LIMIT", default=5)
# Lock on the *combination* of IP and username so one attacker IP can't lock a
# victim out account-wide, and a single guessed account can't be hammered from
# one IP. (A distributed attack across many IPs is out of scope for axes; that
# is what the per-account half of the tuple plus monitoring is for.)
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_USERNAME_FORM_FIELD = "email"
# Cool-off after which the lock auto-clears (hours). A successful auth also
# resets the counter for that IP+account (AXES_RESET_ON_SUCCESS).
AXES_COOLOFF_TIME = env("AXES_COOLOFF_TIME_HOURS", default=1)
AXES_RESET_ON_SUCCESS = True
# Behind the DO App Platform proxy the real client IP is in X-Forwarded-For
# (left-most entry). Tell axes to trust exactly that single proxy hop.
AXES_IPWARE_PROXY_COUNT = 1
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]
# Lockout store. In prod we use the shared Redis cache so the count holds across
# the multiple App Platform processes and survives deploys, exactly like the
# chat quota / API rate limiter (AxesCacheHandler reads AXES_CACHE="default").
# In dev/CI there is no Redis — the cache is per-process LocMem, which axes
# (rightly) refuses to use for tracking (check axes.W001), so we fall back to
# the durable database handler there. Either way lockout is enforced; only the
# storage backend differs.
if env("REDIS_URL"):
    AXES_HANDLER = "axes.handlers.cache.AxesCacheHandler"
    AXES_CACHE = "default"
else:
    AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
# Generic lockout response — never reveal whether the account exists or how many
# attempts remain (account-enumeration hardening, finding #15). Ninja turns this
# into the response; we keep the 403 status and a generic body.
AXES_LOCKOUT_TEMPLATE = None
AXES_VERBOSE = False
# Tests exercise the lockout path explicitly; nothing else relies on axes being
# disabled, so it stays on in tests (toggled per-test via override_settings).
AXES_ENABLED = env("AXES_ENABLED", default=True)

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
# The session routes are CSRF-protected (apps/api/session_auth.py). For an
# HTTPS request with an Origin header, Django verifies that origin against the
# request host + CSRF_TRUSTED_ORIGINS. In prod the SPA is same-origin
# (corpus.nick.law → set via APP_DOMAIN). In dev the Next server proxies /api
# to Django, so the browser's Origin is the frontend dev origin checked against
# Django's own host — trusting the same origins we already allow to make
# credentialed CORS requests keeps those POSTs from failing the Origin check
# without per-box config. dict.fromkeys dedups while preserving order.
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(env("CSRF_TRUSTED_ORIGINS") + CORS_ALLOWED_ORIGINS)
)

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

# ---------------------------------------------------------------------------
# Logging (findings #26 / #35)
# ---------------------------------------------------------------------------
# Two goals beyond the original "pipe 500s to stdout" fix:
#   1. Structured JSON so the App Platform runtime logs are machine-parseable
#      and ready to forward to a SIEM/log store without reformatting. Plain
#      text stays available in dev via LOG_FORMAT=plain.
#   2. A dedicated ``security`` logger (apps/accounts/audit.py) carrying the
#      auth/security audit events as their own JSON stream, so a failed-login or
#      key-revocation line is queryable even independently of the DB audit
#      table.
#
# Django's default routes 500 tracebacks to 'mail_admins', which silently drops
# them when email isn't configured; we keep django.request on the console so
# gunicorn's runtime logs capture the traceback without flipping DEBUG=True.
#
# PII / log governance (finding #35): the structured records emit only metadata
# (event type, actor email, source IP, outcome) — NOT passwords, session keys,
# raw API keys, or chat/document content. Chat traces are handled separately
# (apps/api/models.ChatTrace) under their own retention. django.request
# tracebacks use a plain StreamHandler, which does not serialise local
# variables, so request bodies are not captured here.
#
# Log retention: App Platform runtime logs are short-lived; the durable record
# of security events is the append-only ``accounts.AuditEvent`` table (no
# automatic purge — see apps/accounts/audit.py). Centralised shipping to a
# retained store (Logtail/Datadog/SIEM) is a DigitalOcean console action, not a
# code change — see requestedInput.
_LOG_FORMAT = env("LOG_FORMAT", default="json")  # "json" | "plain"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            # asctime/levelname/name/message plus any `extra=` fields the call
            # site attaches (event, actor_email, source_ip, outcome, …).
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "rename_fields": {"asctime": "time", "levelname": "level", "name": "logger"},
        },
        "plain": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _LOG_FORMAT,
        },
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
        # Auth / security audit trail. INFO so successful logins are recorded,
        # not just failures.
        "security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # django-axes already logs lockouts; route it through our handler so
        # those lines are JSON too.
        "axes": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
