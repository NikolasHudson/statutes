# Scoped Products & Multi-Tenancy Plan

**Status:** Proposal / discussion notes (2026-06-29)
**Scope:** Packaging the flagship Iowa legal-research product into (a) scoped vertical
products sold to **bar associations / regulators** (white-label, member benefit) and
(b) the full product sold to **law firms per seat**.

The corpus stays **one shared, read-only public asset**. "Multi-tenant" here is **not**
data isolation — it's *organizations of users*, a *server-enforced scope lock*, and
*per-tenant branding/billing*. That single fact makes this a much lighter lift than
classic SaaS multi-tenancy.

---

## Part 1 — The scoped product (Iowa Ethics & Procedure app)

### The idea
A standalone app people sign up for whose chat is **scope-locked to the Iowa Court
Rules** (Rules of Civil/Criminal/Appellate Procedure, Evidence, Professional Conduct,
Admission to the Bar). Lawyers chat ethics + procedural questions and get the exact
rule + official comment, with citations verified live. Sold to bar associations and
offices of professional regulation (OPR), optionally white-labeled.

### Why the instinct is right: narrow corpus is the moat
The #1 failure mode for legal AI is hallucinated / over-broad retrieval. Constraining to
a small, closed, well-bounded corpus (~1,205 rules, already ingested + embedded) is
exactly where the existing **verification gate** shines. "Watch it answer a procedure
question with the exact rule + comment, every citation verified" is a far stronger demo
than anything over the full corpus. The scoped product is the best possible showcase for
work already built.

### Two positioning reframes
1. **Sell "find the rule," not "ethics advice."** An ethics-*advice* bot sits in the most
   liability-sensitive zone in legal, and bar associations are the most risk-averse
   buyers in it. Position as **research/lookup with verified citations** — the
   citation-only guardrails and `should_abstain` logic *are* the product. This is how
   Fastcase/vLex got into every bar association: as *search*, never as counsel.
2. **Lead with procedure, include ethics.** Procedural questions ("deadline to file X,"
   "what does the service rule require") are higher-frequency, lower-liability, and a
   bigger market than ethics. Market ethics (the attention-grabber); monetize procedure
   (the daily-use engine).

### Corpus-depth caveat
Rules-only answers *"what does Rule 1.5 say,"* but practitioners ask *"is this
arrangement OK"* — which lives in **Iowa ethics opinions (ISBA), ABA formal opinions, and
disciplinary case law**, none of which are in the corpus yet. The caselaw infrastructure
already exists, so adding disciplinary cases + ethics opinions is a natural extension and
is what turns a thin lookup tool into something orgs renew.

### Pick the buyer deliberately — two different sales
- **Bar association (member benefit):** license once, distribute to all members,
  recurring revenue, white-label fits naturally. Proven distribution model (how Fastcase
  scaled). **Natural first motion.**
- **Office of Professional Regulation / disciplinary board:** an *internal* tool (intake
  triage, consistency in their own opinions). Different, smaller, bespoke sale. **Second
  motion**, not the wedge.

Don't sell both with one pitch.

### Feasibility read (current codebase)

| Piece | State | Effort |
|---|---|---|
| Scope retrieval to court rules only | Already parametric — `source_slug="iowa-court-rules"` flows through the whole pipeline | ~none |
| Court-rules content | Loaded, embedded, searchable today (~1,205 rules) | none |
| Scoped system prompt + guardrails | Prompt is swappable; verification gate is corpus-generic + reusable | <1 wk |
| Multi-tenant signup / org model | App is strictly single-tenant per user — no org concept | ~1–1.5 wk |
| White-label theming | Branding ("HUDSON", colors, login copy) hardcoded in frontend + system prompt | ~1–1.5 wk |

**The RAG and the accuracy story are done.** The real build is the *packaging layer*
(org model, scope lock, branding) covered in Part 2.

---

## Part 2 — Multi-tenancy architecture

### Key architectural fact
The corpus is one shared, read-only public asset, and `source_slug` is currently chosen
by the **client** (`chat-frontend/lib/chat-run.ts:130` sends `scope.sourceSlug`;
`backend/apps/api/chat.py:1435` trusts `payload.source_slug`). Nobody has private corpus
data to wall off. Therefore:

> **One database, one schema, shared corpus. Never db/schema-per-tenant** — that would
> clone identical public law + embeddings for no reason.

Per-tenant data is limited to: org membership, branding, entitlement/billing, and users'
own chat threads (already per-user in `backend/apps/api/models.py`).

### The model layer

Two independent axes — **Tenancy** (who's the org / members) and **Subscription**
(what product + how many seats). Decoupling them lets one org buy multiple products and
lets any product be sold to any org type.

```
Organization ──< Subscription >── Product
                     │
                     ├─ seats: int          ← per-seat lives HERE
                     ├─ billing_ref         ← Stripe subscription id
                     └─ status / period

OrgMembership ──< SeatAssignment >── Subscription   ← which member holds which product seat
```

```python
# accounts/organization.py
class Organization(models.Model):          # the tenant: a bar assoc / OPR / firm
    slug = models.SlugField(unique=True)   # "iowa-bar"
    name = models.CharField(max_length=200)
    custom_domain = models.CharField(max_length=255, blank=True)  # ethics.iowabar.org
    status = models.CharField(...)         # active / trial / suspended
    # branding hangs off here (see Branding section)

class Product(models.Model):               # the "app" definition — CONFIG, not a tenant
    slug = models.SlugField(unique=True)   # "ethics-procedure"
    name = models.CharField(...)           # "Iowa Ethics & Procedure"
    allowed_source_slugs = ArrayField(...) # ["iowa-court-rules"]  ← the scope lock
    system_prompt_key = models.CharField() # which prompt variant to load

class Subscription(models.Model):          # an org's purchase of a product
    org = models.ForeignKey(Organization, ...)
    product = models.ForeignKey(Product, on_delete=PROTECT)
    seats = models.IntegerField(null=True) # null = unlimited / site license
    billing_ref = models.CharField(blank=True)   # Stripe subscription id
    status = models.CharField(...)         # active / past_due / canceled
    tier = models.CharField(...)           # drives quota (see entitlement note)

class OrgMembership(models.Model):
    user = models.ForeignKey(User, ...)
    org  = models.ForeignKey(Organization, ...)
    role = models.CharField(...)           # owner / admin / member
    class Meta: unique_together = ("user", "org")

class SeatAssignment(models.Model):        # which member holds which product's seat
    membership = models.ForeignKey(OrgMembership, ...)
    subscription = models.ForeignKey(Subscription, ...)
    class Meta: unique_together = ("membership", "subscription")
```

`User` / `UserProfile` stay almost as-is. `Product` is separate from `Organization` so
ten bar associations can license the same "ethics-procedure" product with different
branding. **Entitlement check** = *does the user hold a `SeatAssignment` for an active
`Subscription` to this product?* — one query that serves bar-assoc members, per-seat firm
lawyers, and direct B2C users alike.

> v1 simplification: enforce **one active org per user** at the app layer, and let
> org-wide membership implicitly grant all the org's subscriptions (skip `SeatAssignment`
> until per-product seat caps actually matter — i.e. until firms, Part 3). Keep the
> through-models so multi-org / per-product seats are a no-migration change later.

### Tenant resolution — by host, with a public pre-login branding endpoint
The load-bearing white-label constraint: **the login screen must be branded before
anyone authenticates** — so resolve the tenant from the URL, not the logged-in user.

- **MVP:** path prefix — `app.yourdomain.com/o/iowa-bar/...`. No DNS/TLS work.
- **Real white-label:** custom domain / subdomain — `ethics.iowabar.org` (CNAME) or
  `iowa-bar.yourapp.com`. The URL carries the brand.

A Django/Ninja middleware reads `Host` (or path prefix) → looks up `Organization` →
attaches `request.organization` + `request.product` early. A **public, unauthenticated**
`GET /api/branding?host=…` returns that org's brand config; the frontend fetches it at
boot to theme the login screen.

### The critical change: move scope authority from client → server
Today the client says what to search. For a *sold, scoped* product you cannot trust that
— a user editing a request must not reach corpus they didn't pay for. In the chat
endpoint (`chat.py:1435`):

```python
allowed = request.product.allowed_source_slugs        # e.g. ["iowa-court-rules"]
requested = payload.source_slug
source_slug = requested if requested in allowed else allowed[0]
# or 400 if requested is outside `allowed`
```

For the full B2C / firm product, `allowed` = every source, so existing behavior is
unchanged. Everything downstream already keys off `source_slug`
(`_scope_preamble` chat.py:708, `verify_answer` answer.py:325, the retrievers), so you
change **one authority point** and the entire scoped experience falls out for free. This
is the only real correctness/security change in the whole plan, and it's small.

### Branding / white-label config
Put a `BrandConfig` on the Organization: name, logo URL, primary/accent colors, login
copy, support email, disclaimer text, optional system-prompt override. Served by
`/api/branding`; frontend applies via CSS variables. The hardcoded `"HUDSON"` band
(`chat-frontend/components/app-sidebar-brand.tsx`) and `#1f3a5f` / "Hudson Legal Tech"
login colors (`chat-frontend/components/auth-gate.tsx`) become `var(--brand-*)` with the
flagship values as default fallback. Mechanical refactoring, not architecture.

### Getting members in — a provisioning ladder, not a single choice
Bar-assoc members don't share an email domain, so plan for:
1. **Access code (MVP):** the bar hands members a code → signup with code auto-joins the org.
2. **Roster invite:** org admin uploads a member CSV → invite emails. Most bars *have* the roster.
3. **SSO (enterprise):** SAML/OIDC against the bar's member portal — "paid member ⇒ entitled."
   Gold-standard distribution (how Fastcase scaled through bars); later, per-customer.

### Privacy: org admins must not read member chats
These are lawyers asking *ethics questions about their own conduct*. Tag threads with
`org_id` for **aggregate** seat/usage analytics, but never expose chat content to org
admins. Make it an explicit promise — both an ethics/privilege necessity and a selling
point ("your regulator can't read your queries").

---

## Part 3 — Selling to firms (per-seat)

### Same chassis — that's the point
A firm is just another `Organization`. Everything structural carries over unchanged:
`Organization` + `OrgMembership` + roles, membership-derived entitlement, server-side
scope enforcement, shared corpus / single DB, content-private. **Build the org layer for
bar associations and firms come ~80% for free.** "Per-seat" adds one net-new layer and
flips two config choices.

### What firms flip vs. the bar-assoc app

| | Bar-assoc ethics app | Firm, per-seat |
|---|---|---|
| **Scope** | locked to `iowa-court-rules` | full corpus — lock is "everything" (same mechanism, `allowed_source_slugs` = all) |
| **Branding** | white-label, custom domain | *your* brand, maybe a corner logo — **skip the white-label layer** |
| **Provisioning** | access codes / roster | email-domain allowlist (`@firm.com` auto-joins) + SSO for big firms |
| **Billing** | often flat annual site license | **true per-seat: quantity, proration, true-ups** |

Firms are *simpler* on branding (no white-label) and *harder* on billing. A firm may buy
the **full product per seat** *and* the **ethics add-on** for a subset — which is exactly
why `Subscription` (Part 2) is per `(Organization, Product)` rather than a single FK on
the org.

### The one net-new piece: seats + billing
Confirmed absent from the codebase today (no Stripe/billing/subscription/seat code;
`Tier.FIRM` is just an enum with a 50k/day quota set by hand — `accounts.py:442` notes
tier "is a billing attribute"). New work:
1. **Seat counting & enforcement** — `assigned ≤ seats`; gate on invite/activation;
   provisioned vs. active seats; reclaim on offboard.
2. **Billing integration** — Stripe with `quantity = seat count`, proration on mid-cycle
   changes, webhooks → `Subscription.status`.
3. **Move the billing entity from `User` → `Subscription`** — today `user.tier` drives
   `TIER_DAILY_QUOTA` / `FEATURES_BY_TIER` (`backend/apps/api/auth.py`) and
   `_enforce_chat_quota` (`chat.py:839`). For per-seat, the **org's subscription** carries
   the tier/quota and a seat assignment grants the member that entitlement. The existing
   quota machinery stays — you just change *what it reads off of* (member → seat →
   subscription → effective tier, instead of the lone `user.tier`).

---

## Part 4 — Phasing / roadmap

- **Phase 0 — Prove the product (days).** Server-side scope lock + a `Product` config in
  code, **no org model yet**. Ship the scoped ethics/procedure app on a path prefix;
  provision users by hand in Django admin. De-risks the whole idea with almost no new
  infra — demoable to a friendly ISBA contact next week.
- **Phase 1 — Org layer (~1–1.5 wk).** `Organization` + `OrgMembership` + entitlement
  check + host-based resolution + `/api/branding` + frontend theming.
- **Phase 2 — Self-serve + billing.** `Subscription` + seats + Stripe; org-admin
  dashboard (seats, invites, usage); roster invites. *Per-seat firms need this; bar-assoc
  deals can be hand-invoiced annually at first.*
- **Phase 3 — Enterprise.** SSO (SAML/OIDC) for big bars and firms.
- **Parallel track — corpus depth.** Source Iowa ethics opinions + disciplinary cases so
  the scoped app answers "is this OK," not just "what does the rule say."

**Sequencing note:** if per-seat firm sales are the bigger revenue target, the
`Subscription`/Stripe layer (Phase 2) may be worth doing *before* white-label (part of
Phase 1) — firms expect self-serve seat management, while bar-assoc contracts can be
invoiced manually at first.

---

## Appendix — codebase anchors

| Concern | Location |
|---|---|
| Client picks scope today | `chat-frontend/lib/chat-run.ts:130` (`source_slug: scope.sourceSlug`) |
| Server trusts client scope | `backend/apps/api/chat.py:1435` (`payload.source_slug`) |
| Scope → system prompt | `_scope_preamble(source_slug)` — `backend/apps/api/chat.py:708` |
| Citation/quote verification | `verify_answer(content, source_slug, context)` — `backend/apps/api/answer.py:325` |
| Abstain when no good-law authority | `should_abstain(...)` — `backend/apps/api/answer.py` |
| Retrieval entry (source-filterable) | `retrieve_context(... source_slug=None)` — `retrieval.py:319`; `hybrid_search(... source_slug=None)` — `search.py:723` |
| Court-rules source | slug `iowa-court-rules`, seeded `corpus/migrations/0007_seed_iowa_court_rules.py` |
| User / tier model | `backend/apps/accounts/models.py` (`User.tier`, `Tier` = FREE/SOLO/FIRM/CUSTOM) |
| Per-user profile | `backend/apps/accounts/profile.py` (`UserProfile`, free-text `organization`, `default_search_scope`) |
| Auth endpoints | `backend/apps/api/accounts.py` (`/api/auth/register|login|me|logout|csrf`) |
| Session-cookie + CSRF | `chat-frontend/lib/csrf.ts` |
| Quota / feature gating | `TIER_DAILY_QUOTA`, `FEATURES_BY_TIER` — `backend/apps/api/auth.py`; `_enforce_chat_quota` — `chat.py:839` |
| Hardcoded branding | `chat-frontend/components/app-sidebar-brand.tsx` ("HUDSON"); `chat-frontend/components/auth-gate.tsx` (`#1f3a5f`, "Hudson Legal Tech") |
| Per-user chat threads | `backend/apps/api/models.py` |
| Billing / seats | **none exist yet** (net-new for Phase 2) |
</content>
</invoke>
