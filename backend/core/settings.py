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
    # PR4 RAG safety gate. When True, the chat answer gate WITHHOLDS an answer
    # (instead of showing it with an advisory) if the draft relied on Iowa
    # authority that has been invalidated — negatively treated at severity
    # >= RAG_STALE_BLOCK_SEVERITY, without acknowledging that treatment — or if no
    # good-law authority was retrieved at all. Default off: the gate ships dark
    # (advisory-only) and is flipped to enforce per-deploy once trusted. See
    # apps/corpus/services/answer.py (verify_answer / abstain_decision).
    RAG_ABSTAIN_BLOCKING=(bool, False),
    RAG_STALE_BLOCK_SEVERITY=(int, 5),
    # PR5 LLM-assisted layers, each an OpenAI round-trip so each is flag-gated and
    # OFF by default (deterministic v1 paths always run). RAG_CLAIM_NLI: check
    # caselaw holding-claims for misgrounding (apps/corpus/services/answer.py).
    # RAG_QUERY_REWRITE: rewrite the search query before retrieval
    # (apps/corpus/services/query_rewrite.py). Both no-op without an OpenAI key.
    RAG_CLAIM_NLI=(bool, False),
    RAG_QUERY_REWRITE=(bool, False),
    # PR8: domain-applicability check — one LLM call per answer classifying
    # each cited authority as governs/analogy/inapplicable for the fact
    # pattern (catches "real statute, wrong body of law": UCC § 554.2718
    # applied to a residential lease). OFF by default like the other LLM
    # layers; no-op without an OpenAI key. See apps/corpus/services/applicability.py.
    RAG_APPLICABILITY_CHECK=(bool, False),
    # PR9: web currency tripwire. At verification time, cases the answer
    # relies on (and the citator doesn't flag) get one web-search call asking
    # "still good law?"; the verdict persists as a CaseResearchNote on the
    # decision node so future turns read it for free, and adverse findings
    # queue for attorney review (corpus admin). Advisory-only; web content
    # never enters generation. OFF by default like the other LLM layers.
    RAG_WEB_CURRENCY_CHECK=(bool, False),
    # Max NEW web checks per answer (cached notes are free). Bounds worst-case
    # added latency on cache-miss turns to ~budget × timeout.
    # Real web_search calls run 10-30s; the checker uses max_retries=0 so a
    # timeout costs exactly this long, once. Worst case per answer =
    # budget × timeout, and only on cache-miss turns; drop budget to 1 for
    # latency-sensitive deploys.
    RAG_WEB_CURRENCY_BUDGET=(int, 2),
    RAG_WEB_CURRENCY_TIMEOUT=(int, 40),
    # CLEAR notes re-check after this many days; ADVERSE notes persist.
    RAG_WEB_CURRENCY_MAX_AGE_DAYS=(int, 30),
    # PR6: before answering, verify case-holding premises the USER asserts in the
    # question against the retrieved opinion, and inject a pre-answer caution so
    # the model doesn't anchor on a wrong premise. OFF by default; no-op without a
    # key. See apps/corpus/services/premise.py. This is the *fidelity* axis (is the
    # premise a faithful reading of the case?) — an LLM round-trip, hence opt-in.
    RAG_PREMISE_CHECK=(bool, False),
    # Email assistant (apps/mail). POSTMARK_SERVER_TOKEN switches outbound mail
    # from the dev console backend to Postmark via anymail. The webhook token
    # authenticates Postmark's inbound POSTs (?token=... on the webhook URL,
    # compared constant-time) — both unset means the email surface is dark.
    POSTMARK_SERVER_TOKEN=(str, ""),
    EMAIL_INBOUND_WEBHOOK_TOKEN=(str, ""),
    # Require SPF-or-DKIM pass on inbound mail before acting on it. Replying to
    # a spoofed From both leaks answers and creates backscatter, so this stays
    # on everywhere real mail arrives; tests toggle it off explicitly.
    EMAIL_REQUIRE_SENDER_AUTH=(bool, True),
    # Where emailed citation links point for the flagship assistant address
    # (a scoped product's address uses its own Product.hostname instead).
    EMAIL_LINK_BASE_URL=(str, "https://corpus.nick.law"),
    # PR7: the *currency* axis, orthogonal to fidelity — is the case the user's
    # premise rests on still GOOD LAW? Deterministic (reads the PR3 treatment flag
    # already on the retrieved passage; no LLM), so it ships ON by default: a
    # faithful reading of an OVERRULED case (the Madden/Bankers Trust trap) is the
    # failure the fidelity check is structurally blind to. See premise.check_premises.
    # Cost: gated by extract_premises (pure regex) so ordinary questions short-circuit
    # with no retrieval; only a turn whose text ASSERTS a named case's holding pays up
    # to MAX_PREMISES retrieve_context calls pre-draft. Set False to disable.
    RAG_CURRENCY_CHECK=(bool, True),
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
RAG_ABSTAIN_BLOCKING = env("RAG_ABSTAIN_BLOCKING")
RAG_STALE_BLOCK_SEVERITY = env("RAG_STALE_BLOCK_SEVERITY")
RAG_CLAIM_NLI = env("RAG_CLAIM_NLI")
RAG_QUERY_REWRITE = env("RAG_QUERY_REWRITE")
RAG_APPLICABILITY_CHECK = env("RAG_APPLICABILITY_CHECK")
RAG_WEB_CURRENCY_CHECK = env("RAG_WEB_CURRENCY_CHECK")
RAG_WEB_CURRENCY_BUDGET = env("RAG_WEB_CURRENCY_BUDGET")
RAG_WEB_CURRENCY_TIMEOUT = env("RAG_WEB_CURRENCY_TIMEOUT")
RAG_WEB_CURRENCY_MAX_AGE_DAYS = env("RAG_WEB_CURRENCY_MAX_AGE_DAYS")

# Tests must NEVER make live LLM/web calls through the flag-gated verification
# layers — the suites inject fake checkers explicitly. Turning a flag on in
# .env (e.g. for the dev UI) must not leak real OpenAI/web traffic into
# `manage.py test`, so the flags are forced off under the test runner.
import sys  # noqa: E402

if "test" in sys.argv:
    RAG_CLAIM_NLI = False
    RAG_PREMISE_CHECK = False
    RAG_APPLICABILITY_CHECK = False
    RAG_WEB_CURRENCY_CHECK = False
RAG_PREMISE_CHECK = env("RAG_PREMISE_CHECK")
RAG_CURRENCY_CHECK = env("RAG_CURRENCY_CHECK")
DOCLING_SERVICE_URL = env("DOCLING_SERVICE_URL")
DOCLING_TIMEOUT = env("DOCLING_TIMEOUT")

# ---------------------------------------------------------------------------
# Email (the apps/mail assistant surface). With a Postmark token, outbound
# goes through anymail's Postmark backend on the transactional stream; without
# one (dev/tests) messages print to the console so the flow stays exercisable.
# ---------------------------------------------------------------------------
POSTMARK_SERVER_TOKEN = env("POSTMARK_SERVER_TOKEN")
EMAIL_INBOUND_WEBHOOK_TOKEN = env("EMAIL_INBOUND_WEBHOOK_TOKEN")
EMAIL_REQUIRE_SENDER_AUTH = env("EMAIL_REQUIRE_SENDER_AUTH")
EMAIL_LINK_BASE_URL = env("EMAIL_LINK_BASE_URL")
if POSTMARK_SERVER_TOKEN:
    EMAIL_BACKEND = "anymail.backends.postmark.EmailBackend"
    ANYMAIL = {"POSTMARK_SERVER_TOKEN": POSTMARK_SERVER_TOKEN}
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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
    "anymail",
    "apps.accounts",
    "apps.corpus",
    "apps.tenancy",
    "apps.api",
    "apps.mail",
    "apps.citations",
    "apps.ingestion_iowa_code",
    "apps.ingestion_iowa_rules",
    "apps.ingestion_iowa_admin_code",
    "apps.ingestion_iowa_acts",
    "apps.ingestion_caselaw",
    "apps.mcp_server",
]

MIDDLEWARE = [
    # FIRST, before host/SSL middleware: answer the App Platform container
    # health probe (pod-IP Host, plain HTTP) so the tightened ALLOWED_HOSTS /
    # SECURE_SSL_REDIRECT don't 400/301 it. See core/middleware.py.
    "core.middleware.HealthCheckMiddleware",
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
    # Resolve the scoped product from the Host (clerk.<domain> -> the Ethics
    # app) and attach request.product. After auth so request.user is available
    # downstream; before the views so /api/branding can read it pre-login.
    "core.middleware.ProductResolutionMiddleware",
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

# Where redirect_to_login() sends an unauthenticated browser. The only Django
# view that uses it today is the MCP OAuth consent page (apps/mcp_server/
# oauth.authorize): the SPA's sign-in gate lives on the root route and gets
# ?next=<full authorize URL> so it can land the user back on the consent page
# after signing in.
LOGIN_URL = "/"

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
