import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    # The app's own public origin: the single front door, and the base of every
    # URL we hand a human. Stripe Checkout/portal return URLs
    # (apps/billing/api._return_base_url) and org invite links
    # (apps/api/orgs._app_base_url) both resolve to exactly this and nothing
    # else — a guessed base URL strands a user who has just paid, or on a page
    # that doesn't exist. The default is today's production origin so no box
    # needs a new .env entry to boot; set it in the App Platform spec when the
    # app changes host.
    APP_URL=(str, "https://app.hudsonlegal.tech"),
    # MCP OAuth 2.0 issuer (apps/mcp_server/{oauth,auth}.py, which read it from
    # os.environ directly — this entry exists so the var is discoverable and
    # settable from .env). Empty means the issuer FLOATS WITH THE REQUEST HOST:
    # tokens minted under one hostname stop validating under another, so on a
    # multi-host deploy prod must pin it to the app origin.
    MCP_OAUTH_ISSUER=(str, ""),
    # The public MCP endpoint, served to the frontend by GET /api/config and
    # pasted by the user into claude_desktop_config.json. Empty = derive it from
    # APP_URL, which is what every real deploy wants (the MCP door is a path on
    # the app host, routed there by App Platform ingress); the override exists for
    # a tunnel/forwarded-port setup where the two origins genuinely differ.
    # Until now this was read straight from os.environ and was in no spec, so
    # /api/config answered {"mcp_host": null} in production and the account page
    # had no host to put in the snippet.
    MCP_HOST=(str, ""),
    # FALLBACK ONLY — read apps/accounts/audit.client_ip before touching this.
    #
    # How many proxies WE run between the public internet and Django. Each one
    # APPENDS the address it accepted the connection from to X-Forwarded-For, so
    # only the last N entries are ours to trust. An earlier version of this comment
    # asserted "on App Platform that is the single edge hop"; that was never
    # measured and prod contradicts it — app.hudsonlegal.tech is orange-clouded, so a
    # request crosses Cloudflare AND the App Platform edge (verified 2026-07-13:
    # Cloudflare anycast A records + cf-ray + x-do-app-origin on one response).
    #
    # The value is deliberately left at 1 rather than "corrected" to 2, because a
    # second guess is not better than the first: nothing echoes the origin-side
    # header, so the true count is unmeasured. It is safe to leave low — too LOW
    # degrades to a proxy address (one shared bucket), too HIGH reads an entry the
    # client TYPED, and only the latter is a forgery. In production this branch is
    # not reached at all: TRUST_CF_CONNECTING_IP resolves the address first.
    #
    # To measure it for real (needed only if CF trust is ever turned off): the
    # security log now carries xff_len on every auth event — see
    # apps/accounts/audit.proxy_chain_shape. Log in once, read xff_len, and set
    # this to (xff_len - <entries the client sent, i.e. 0 for an honest browser>).
    TRUSTED_PROXY_COUNT=(int, 1),
    # Trust Cloudflare's CF-Connecting-IP as the client address.
    #
    # This is THE client-IP control in production, and it is the one header in the
    # chain a browser cannot lie about THROUGH CLOUDFLARE: Cloudflare OVERWRITES
    # CF-Connecting-IP on ingress, and unlike X-Forwarded-For it does not depend on
    # counting hops. Trusting it is sound ONLY while every request that reaches a
    # path calling client_ip has transited a Cloudflare that overwrote the header.
    #
    # The bypass this must foreclose is NOT the one an earlier version of this
    # comment tested. That test hit the bare *.ondigitalocean.app host with its OWN
    # hostname and got 400 DisallowedHost — but an attacker would not do that; they
    # would send Host: app.hudsonlegal.tech (which IS in ALLOWED_HOSTS) straight to
    # the DO origin, skipping OUR Cloudflare, and forge CF-Connecting-IP. So
    # ALLOWED_HOSTS does NOT foreclose it. What actually does (verified 2026-07-14
    # against prod): a request to statutes-*.ondigitalocean.app bearing
    # Host: app.hudsonlegal.tech is refused 403 at DO's edge — /api/health and
    # /admin/login/ both 403, so the spoofed-host request never reaches Django, and
    # any request that DOES reach it has passed through a Cloudflare (DO's edge is
    # itself CF-fronted) that overwrote CF-Connecting-IP.
    #
    # That safety therefore rests on DO edge behavior we do not control and do not
    # monitor. DEFENSE-IN-DEPTH TO ADD (Cloudflare-side, not code): enable
    # Authenticated Origin Pulls (mTLS) or a CF Transform Rule that injects a secret
    # header the origin verifies, so a direct-to-origin request is rejected
    # regardless of DO's edge. Until then, re-run the 403 probe after any DO/CF
    # topology change.
    #
    # Default OFF, and it MUST stay off anywhere Cloudflare is not genuinely in
    # front — with no CF in the path this header is just another string a client
    # can type. Turned on explicitly in .do/app.yaml, never by default.
    TRUST_CF_CONNECTING_IP=(bool, False),
    # Shared secret proving a request came from the marketing site's own
    # server-side route handlers (marketing-frontend/app/api/{contact,subscribe}).
    # Those relay leads from a container, so the visitor's address is not a
    # property of the connection we see: the handler copies it into X-Real-Client-IP
    # and this token proves the copy is ours. Without it every lead on earth arrives
    # from the marketing container's egress IP and shares one throttle bucket.
    #
    # It authorises asserting a source IP, so audit.client_ip additionally confines
    # it to /api/marketing/* — a leaked token must not become the ability to forge
    # an address into the login lockout or the audit trail.
    #
    # Unset = the header is ignored entirely, so dev and any deploy that forgets it
    # still work; they just fall back to the connecting address. Set the SAME value
    # on BOTH apps. It is a secret, never NEXT_PUBLIC_. Keep it ASCII.
    MARKETING_PROXY_TOKEN=(str, ""),
    # Host → Product resolution (core/middleware.ProductResolutionMiddleware).
    # An unrecognised Host resolves to product=None, and product=None IS the
    # unlocked full-corpus flagship — so a white-label host that reaches DNS and
    # ALLOWED_HOSTS before its Product row exists would serve the whole flagship
    # with the scope lock silently gone. STRICT refuses (404) any Host that is
    # neither a Product.hostname nor an explicit FLAGSHIP_HOSTS entry.
    # Default OFF = today's behaviour exactly. Do NOT turn it on in the same
    # change that first populates FLAGSHIP_HOSTS: an incomplete list locks out
    # the flagship itself. (/api/health is answered by HealthCheckMiddleware
    # ahead of this, so the pod-IP probe is safe either way.)
    PRODUCT_HOST_STRICT=(bool, False),
    FLAGSHIP_HOSTS=(list, []),
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
    # RFC 8601 authserv-id pinning for the SPF/DKIM verdicts on inbound mail.
    # The verdict lives in an Authentication-Results header, and a SENDER can
    # embed a forged "Authentication-Results: …; dkim=pass" in their own message
    # — so a consumer MUST only honor headers stamped by a verifier it trusts,
    # identified by the authserv-id (the token before the first ';'). Set this to
    # the authserv-id(s) our own inbound path stamps (read it off one real
    # message's top Authentication-Results header — the Cloudflare Email Routing
    # / Postmark verifier). When EMPTY (default), pinning is OFF and the legacy
    # first-header substring is used, which is spoofable — so set it in prod.
    EMAIL_TRUSTED_AUTHSERV_IDS=(list, []),
    # Where emailed citation links point for the flagship assistant address
    # (a scoped product's address uses its own Product.hostname instead).
    # LOAD-BEARING DEFAULT: the live App Platform spec does not set this, so
    # prod runs on the value below. Moving the app without also setting this
    # explicitly in the spec silently keeps mailing links to the old host.
    EMAIL_LINK_BASE_URL=(str, "https://app.hudsonlegal.tech"),
    # PR7: the *currency* axis, orthogonal to fidelity — is the case the user's
    # premise rests on still GOOD LAW? Deterministic (reads the PR3 treatment flag
    # already on the retrieved passage; no LLM), so it ships ON by default: a
    # faithful reading of an OVERRULED case (the Madden/Bankers Trust trap) is the
    # failure the fidelity check is structurally blind to. See premise.check_premises.
    # Cost: gated by extract_premises (pure regex) so ordinary questions short-circuit
    # with no retrieval; only a turn whose text ASSERTS a named case's holding pays up
    # to MAX_PREMISES retrieve_context calls pre-draft. Set False to disable.
    RAG_CURRENCY_CHECK=(bool, True),
    # Marketing-site contact form (apps.marketing): where to send the "new
    # submission" heads-up email, and the From it uses.
    #
    # NOTIFY unset = NO EMAIL AT ALL — leads land in the Django admin and nobody
    # is told they exist. That is the state of production today (it is in no
    # spec), so it is not a hypothetical default: set it, or the funnel is a
    # table you have to remember to open. Absent it, a prod boot warns (below)
    # and every stored submission logs a warning.
    #
    # FROM must be a sender Postmark has VERIFIED for the sending domain. It
    # isn't a cosmetic label: Postmark rejects an unverified signature, send_mail
    # raises, apps/marketing/api.py logs it and still answers 200 — the visitor
    # sees a thank-you and we hear nothing. The default below belongs to the old
    # mail domain, so the domain move must set this in the same breath.
    CONTACT_NOTIFY_EMAIL=(str, ""),
    CONTACT_FROM_EMAIL=(str, "assistant@mail.nick.law"),
    # Data-retention window for marketing lead PII (ContactSubmission rows and
    # unsubscribed NewsletterSubscriber rows), enforced by the
    # `purge_marketing_leads` management command. Lead rows hold name/email/IP
    # and had no lifecycle at all — indefinite retention is the SOC 2 gap this
    # closes. 0 = disabled (retain forever): a real value is a policy decision,
    # so the mechanism ships off and Nick sets the number + schedules the command.
    MARKETING_LEAD_RETENTION_DAYS=(int, 0),
    # Whole-platform monthly LLM spend ceiling in USD (apps.api.usage). The
    # dollar sibling of CHAT_MONTHLY_GLOBAL_LIMIT (message count): when
    # month-to-date recorded cost crosses this, chat/verify return 503 for
    # everyone (staff included) until the 1st. 0 disables the ceiling.
    CHAT_GLOBAL_MONTHLY_BUDGET_USD=(float, 500.0),
    # Billing (apps.tenancy.services). How long a ``past_due`` subscription keeps
    # granting its plan after the first failed payment — the dunning grace window.
    # Past it, the org grants ``free`` and every existing tier gate enforces that
    # with no extra code. The STRIPE_* keys live with apps/billing.
    BILLING_PAST_DUE_GRACE_DAYS=(int, 7),
    # The billing launch switch: when True, the interactive surfaces (chat,
    # verify, research search, API keys/MCP, email assistant) require a paid
    # plan — there is no free tier, only the Stripe trial. Default False so
    # beta/dev/CI keep working; flipping it in prod IS the end of open beta,
    # so comp/notify existing users first (apps/tenancy/comping.py).
    BILLING_REQUIRE_PAID=(bool, False),
    # --- Stripe (apps.billing) ---------------------------------------------
    # Every one of these defaults to empty so dev, CI and the test suite boot
    # with no Stripe account at all: apps/billing treats an empty
    # STRIPE_SECRET_KEY as "billing not configured" and the Stripe-calling
    # endpoints answer 503 instead of exploding (GET /api/billing/subscription
    # still serves DB state — a comped subscription has no Stripe object).
    STRIPE_SECRET_KEY=(str, ""),
    STRIPE_PUBLISHABLE_KEY=(str, ""),
    STRIPE_WEBHOOK_SECRET=(str, ""),
    # Price IDs, NOT prices. Dollar amounts live in Stripe and are never
    # hardcoded in Python — these map price_id → plan (apps/billing/plans.py).
    # FIRM_SEAT is the optional per-seat line item that rides alongside the
    # FIRM base price; when it is set, it is the item whose quantity seat sync
    # moves. Leave it empty for a flat per-seat firm price.
    STRIPE_PRICE_SOLO=(str, ""),
    STRIPE_PRICE_FIRM=(str, ""),
    STRIPE_PRICE_FIRM_SEAT=(str, ""),
    # Card-up-front trial length applied at Checkout, first subscription per org
    # only (an org that ever held a Stripe subscription doesn't trial again).
    # 0 disables trials entirely.
    STRIPE_TRIAL_DAYS=(int, 7),
    # Stripe-specific override of APP_URL for Checkout / Billing Portal return
    # URLs. Empty (the normal case) = APP_URL, full stop; there is no guessing
    # tail. The "/account/billing" path is appended.
    STRIPE_RETURN_BASE_URL=(str, ""),
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
CHAT_GLOBAL_MONTHLY_BUDGET_USD = env("CHAT_GLOBAL_MONTHLY_BUDGET_USD")
BILLING_PAST_DUE_GRACE_DAYS = env("BILLING_PAST_DUE_GRACE_DAYS")
BILLING_REQUIRE_PAID = env("BILLING_REQUIRE_PAID")
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
RAG_PREMISE_CHECK = env("RAG_PREMISE_CHECK")
RAG_CURRENCY_CHECK = env("RAG_CURRENCY_CHECK")

# Tests must NEVER make live LLM/web calls through the flag-gated verification
# layers — the suites inject fake checkers explicitly. Turning a flag on in
# .env (e.g. for the dev UI) must not leak real OpenAI/web traffic into
# `manage.py test`, so the flags are forced off under the test runner. The
# env() reads above must stay above this block or they silently undo it.
import sys  # noqa: E402

# The SUBCOMMAND must be `test` — not merely the word "test" appearing anywhere in
# argv. `"test" in sys.argv` also matches `manage.py changepassword test` (a user
# named "test"), which would hash that user's real password with MD5 below and
# persist it. Prod migrations and management commands here are hand-run against the
# live DB, so that is a reachable way to write a junk hash into production.
IS_TEST_RUN = len(sys.argv) > 1 and sys.argv[1] == "test"

if IS_TEST_RUN:
    RAG_CLAIM_NLI = False
    RAG_PREMISE_CHECK = False
    RAG_APPLICABILITY_CHECK = False
    RAG_WEB_CURRENCY_CHECK = False
    # The dev .env turns billing on to exercise the paywall in the UI, but that
    # leaks into the test runner and 402s every suite written before billing —
    # the sole cause of the ~21 "pre-existing" failures. Tests that WANT the
    # paywall turn it on with override_settings (apps/api/tests/test_paywall.py).
    BILLING_REQUIRE_PAID = False
    # PBKDF2 takes >1s per hash on the dev droplet; with users created in
    # per-test setUp that was ~20 min of suite time. Tests don't care about
    # hash strength.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
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
EMAIL_TRUSTED_AUTHSERV_IDS = env("EMAIL_TRUSTED_AUTHSERV_IDS")
EMAIL_LINK_BASE_URL = env("EMAIL_LINK_BASE_URL")
CONTACT_NOTIFY_EMAIL = env("CONTACT_NOTIFY_EMAIL")
CONTACT_FROM_EMAIL = env("CONTACT_FROM_EMAIL")
MARKETING_LEAD_RETENTION_DAYS = env("MARKETING_LEAD_RETENTION_DAYS")
# Contact notifications OFF is a silent failure mode by construction: the visitor
# still gets a 200 and the row is still written, so nothing anywhere goes red — we
# just never look. Say so at boot, once, where the App Platform runtime log will
# carry it. A warning and not a hard fail: a missing notification address must
# never be the reason the site cannot serve requests, and dev/CI have no mailbox.
if not DEBUG and not IS_TEST_RUN and not CONTACT_NOTIFY_EMAIL:
    import warnings  # noqa: E402

    warnings.warn(
        "CONTACT_NOTIFY_EMAIL is unset: marketing contact submissions will be "
        "stored in the admin and NOBODY will be emailed about them.",
        RuntimeWarning,
        stacklevel=1,
    )
if POSTMARK_SERVER_TOKEN:
    EMAIL_BACKEND = "anymail.backends.postmark.EmailBackend"
    ANYMAIL = {"POSTMARK_SERVER_TOKEN": POSTMARK_SERVER_TOKEN}
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Stripe (apps.billing). All optional: with STRIPE_SECRET_KEY unset the app
# boots, the suite passes, and /api/billing/{checkout,portal,webhook} return a
# clean 503 "billing not configured". Subscription state is still readable —
# a backfilled/comped Subscription row has no Stripe object behind it at all.
#
# STRIPE_PRICE_* are Stripe price IDs (price_...), never amounts: the price
# points live in the Stripe dashboard, and apps/billing/plans.py maps
# price_id → plan (free/solo/firm/custom) in both directions.
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_SOLO = env("STRIPE_PRICE_SOLO")
STRIPE_PRICE_FIRM = env("STRIPE_PRICE_FIRM")
STRIPE_PRICE_FIRM_SEAT = env("STRIPE_PRICE_FIRM_SEAT")
STRIPE_TRIAL_DAYS = env("STRIPE_TRIAL_DAYS")
STRIPE_RETURN_BASE_URL = env("STRIPE_RETURN_BASE_URL")

# The app's public origin. Every user-facing link we generate server-side hangs
# off this one value — see the schema note above.
APP_URL = env("APP_URL")
# The schema default is the PRODUCTION origin, so a prod box is correct with no
# config. That default is wrong for dev, though: before APP_URL existed, dev
# resolved these links through CORS_ALLOWED_ORIGINS[0] (the local SPA), so
# inheriting the prod default would point a dev Stripe checkout and a dev invite
# email at app.hudsonlegal.tech. Absent an explicit APP_URL, dev keeps its own origin.
# Checked against os.environ, not env(), because env() cannot distinguish "unset"
# from "set to the default"; read_env() has already folded .env into os.environ.
if DEBUG and "APP_URL" not in os.environ:
    APP_URL = "http://localhost:3000"
# Registered, not consumed here: apps/mcp_server reads it from os.environ (which
# read_env() has already populated from .env). Pin it in prod — see the schema.
MCP_OAUTH_ISSUER = env("MCP_OAUTH_ISSUER")
# The MCP door is a path on the app host (App Platform routes /mcp to Django), so
# it follows APP_URL by default and the cutover has one host to set, not two.
MCP_HOST = env("MCP_HOST") or f"{APP_URL.rstrip('/')}/mcp"

# Read by core/middleware.ProductResolutionMiddleware. These must be declared here
# even though the middleware reads them defensively: Django settings do not fall
# through to os.environ, so without these two lines the switch is inert and setting
# it in the App Platform spec would do nothing, silently.
PRODUCT_HOST_STRICT = env("PRODUCT_HOST_STRICT")
FLAGSHIP_HOSTS = env("FLAGSHIP_HOSTS")

# Who the client is — see apps/accounts/audit.client_ip, and the schema notes
# above. Every IP-keyed security control in the app (login lockout, registration
# throttle, marketing lead throttle, audit source_ip) resolves through that one
# helper and these two values; they are the difference between a throttle that
# counts people and one that counts proxies.
TRUSTED_PROXY_COUNT = env("TRUSTED_PROXY_COUNT")
TRUST_CF_CONNECTING_IP = env("TRUST_CF_CONNECTING_IP")
MARKETING_PROXY_TOKEN = env("MARKETING_PROXY_TOKEN")

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
    "apps.billing",
    "apps.mail",
    "apps.marketing",
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
# Source IP. This used to be AXES_IPWARE_PROXY_COUNT=1 — dead configuration:
# django-ipware is not installed (it is nobody's dependency here), so axes fell
# through to its REMOTE_ADDR branch and, behind the App Platform proxy, locked
# out on the *proxy's* address. With AXES_LOCKOUT_PARAMETERS keyed on
# (ip_address, username) and ip_address constant for the whole internet, the
# lockout degenerates to per-username: five wrong guesses from anywhere lock a
# named account, and no attacker address is ever recorded. Point axes at the one
# helper that discounts the hops properly, so axes, the registration throttle,
# the marketing lead throttle and the audit trail all agree on who the client is.
AXES_CLIENT_IP_CALLABLE = "apps.accounts.audit.client_ip"
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

# EXACTLY ONE ENTRY: the app's own origin. This list is not a list of "sites we
# like" — CORS_ALLOW_CREDENTIALS is True and the list is folded into
# CSRF_TRUSTED_ORIGINS below, so every entry is an origin that may send cookies
# to this API *and* is trusted to originate state-changing POSTs against it.
# The marketing site does NOT belong here and does not need to: its forms post
# to their own Next route handlers, which call the API server-side
# (marketing-frontend/app/api/{contact,subscribe}/route.ts → API_ORIGIN), so no
# browser ever makes a cross-origin call to Django. Adding an origin here to
# "fix" a marketing form hands that origin a credentialed, CSRF-trusted channel.
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
# The session routes are CSRF-protected (apps/api/session_auth.py). For an
# HTTPS request with an Origin header, Django verifies that origin against the
# request host + CSRF_TRUSTED_ORIGINS. In prod the SPA is same-origin
# (app.hudsonlegal.tech → set via APP_DOMAIN). In dev the Next server proxies /api
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
    # __Host- prefix: the browser refuses the cookie unless it is Secure,
    # path-scoped to "/", and carries NO Domain attribute. That last clause is
    # the point — on a multi-tenant apex any sibling subdomain can otherwise set
    # a Domain=.<apex> cookie that shadows csrftoken/sessionid in our own
    # requests (cookie tossing), and the prefix makes that impossible rather than
    # merely unlikely. Hence also: SESSION_COOKIE_DOMAIN / CSRF_COOKIE_DOMAIN
    # stay unset, both because __Host- forbids Domain and because a dot-domain
    # cookie is a tenant-isolation break in its own right.
    # DEBUG-gated because the rule is enforced silently: over plain HTTP (dev)
    # the browser drops a __Host- cookie with no error and login just stops
    # working. Renaming the cookies invalidates every live session — a forced
    # logout, which is free only while the user base is us.
    SESSION_COOKIE_NAME = "__Host-sessionid"
    CSRF_COOKIE_NAME = "__Host-csrftoken"
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
