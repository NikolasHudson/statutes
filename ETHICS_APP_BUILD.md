# Ethics & Procedure App — Build Log & Plan

**Status:** Backend foundation + security boundary **done & verified on dev** (2026-06-30,
uncommitted, on `main`). Frontend not started.
**Working name:** "ethics app" (real product name TBD).
**Companion docs:** `MULTI_TENANT_PRODUCTS_PLAN.md` (original strategy — note its
subdomain-per-tenant design is **superseded** by the access model in §2 below).

---

## 1. What this is

A standalone, **scope-locked** Ethics & Procedure research app sold to the **Iowa State
Bar Association (ISBA)** as a member benefit. Lawyers ask procedure/ethics questions and
get the exact rule + official comment, with every citation verified. The narrow corpus is
the moat: it's where the existing verification gate shines.

The corpus stays **one shared, read-only public asset**. This work is a *packaging* layer
(who's the org, what product, who's entitled, what brand) — **not** data isolation.

### Decided parameters

| Decision | Choice | Why |
|---|---|---|
| Geographic scope | **Iowa first**, architected so a 2nd state is *data, not code* | Corpus already models jurisdiction (§3) |
| Buyer | **ISBA / bar association** (member benefit), not the regulator (OPR) | Proven distribution motion (how Fastcase scaled); lower liability |
| Corpus depth (v1) | **Rules + official comments only** | Already ingested/embedded (~1,205 rules); lowest liability |
| Positioning | "Find the rule," verified citations — **not** ethics *advice* | Bars are risk-averse; the verification gate *is* the product |
| Pre-login branding | The **app's own brand** (not per-bar) | Lets us drop per-tenant subdomains (§2) |

---

## 2. Access model (the key architectural decision)

**The domain identifies the PRODUCT; access is decided by ENTITLEMENT** — not by the URL.
This replaces the subdomain-per-tenant / wildcard-DNS design in the original plan doc.

```
        clerk.<domain>                          app.<domain>  (+ apex)
        LOCKED front door                       UNLOCKED app
        host pins ONE product (ethics)          host pins nothing
        scope fixed to that product             user sees everything they're entitled to
                    │                                   │
                    └─────────────┬─────────────────────┘
                          same app, same login, same backend
                                  │
                            log in → entitlement gate
                                  │
        ENTITLED if ANY of (union):
          1. individual subscription to the product
          2. member of an org (bar/firm) with an active subscription
          3. holds the full corpus (paid tier ⇒ all scoped apps; superset)
```

- **No per-bar subdomains, no wildcard DNS.** Adding the ethics app later = one DNS record
  + one `Product.hostname` value.
- **Locked vs unlocked are the same app**; the only difference is whether the host pins a
  product. A full-corpus subscriber on `clerk.*` is let in (superset); an ethics-only bar
  member who lands on `app.*` simply sees only the ethics scope. Degrades gracefully because
  access is entitlement, not URL.
- **Multi-org membership is a non-issue** — entitlement is a union, so there's nothing to
  "pick" for access. (The only place "which org" matters is the future co-brand ribbon.)
- **Branding:** pre-login shows the *product's* own brand. A bar's logo becomes an optional
  post-login "Provided by &lt;bar&gt;" ribbon (deferred).

---

## 3. What's built (backend) — done & verified 2026-06-30

### New app: `backend/apps/tenancy/`

| Model | Role / key fields |
|---|---|
| `Product` | the scoped app def + its own brand. `slug`, `hostname` (locked front door), `allowed_source_slugs` (the scope lock; empty = full corpus), `system_prompt_key`, `jurisdiction` FK, brand fields |
| `Organization` | distribution/billing vehicle (bar/firm). `slug`, `name`, `status`, minimal co-brand. **Not in the URL.** |
| `Subscription` | active license, held by **org XOR user** (DB check constraint). `status` only — **no seats/billing yet** |
| `OrgMembership` | who's in the org + role. Many-to-many (multi-bar OK) |

- `entitlement.is_entitled(user, product)` — the union of the 3 grants above. Full-corpus
  tiers (SOLO/FIRM/CUSTOM) short-circuit to entitled; FREE needs a direct/org subscription.
- Migration `0001_initial` applied.

### Wiring

- **`core.middleware.ProductResolutionMiddleware`** — resolves Host → `request.product`
  (a `Product` or `None`). Registered after `AuthenticationMiddleware`. In `DEBUG`, an
  `X-Product-Slug` header (or `?product=`) overrides host resolution for no-DNS testing.
- **`GET /api/branding`** (`apps/api/api.py`, `auth=None`) — public, pre-login brand for the
  host's product. Unrecognized host → `{"product": null}` (frontend falls back to HUDSON).
- **Scope lock + entitlement gate** — `_enforce_product_scope(request, user, payload)` in
  `apps/api/chat.py`, called in **both** `/api/chat` and `/api/chat/stream` right after
  `_require_login`. On a locked product it: 403s a non-entitled user, **clamps**
  `source_slug` to the product's allowed sources, and **drops** an out-of-scope pinned
  `node_id`. The single server-side authority point for scope.
- **Seed:** `python manage.py seed_ethics_procedure_demo [--hostname clerk.nick.law]` —
  idempotent; creates the `iowa-ethics-procedure` product (scope `["iowa-court-rules"]`,
  jurisdiction Iowa, host `clerk.localhost` default), the `iowa-bar` org, and an active
  site-license subscription. Members of `iowa-bar` are then entitled.

### Corpus is already multi-state ready (verified)

`corpus.Jurisdiction` is a first-class model; `Source` FKs to it (unique per
`(jurisdiction, slug)`); three Iowa sources exist (`iowa-code`, `iowa-court-rules`,
`iowa-caselaw`). "Iowa" is hardcoded only in the **prompt/label layer** (`chat.py` system
prompt ~`:442`, `_scope_preamble` ~`:708`, citation formats) and two `== "iowa-caselaw"`
slug checks — not in the data model. A 2nd state = seed a `Jurisdiction` + sources + ingest.

### Verification (all passing)

| Check | Result |
|---|---|
| Host `clerk.localhost` → ethics product brand (public, pre-login) | ✅ 200 + brand |
| Host `app.localhost` → no product (`{"product": null}`) | ✅ |
| Entitlement: bar member / free-no-org / solo-tier / individual-sub | ✅ T / F / T / T |
| `Subscription` org-XOR-user constraint | ✅ enforced at DB |
| Locked app: out-of-scope `source_slug` → clamped to `iowa-court-rules` | ✅ |
| Locked app: out-of-scope `node_id` → dropped | ✅ |
| Locked app: non-entitled user → 403 | ✅ |
| Unlocked flagship: scope honored, no gate | ✅ |

---

## 4. The plan (what's left, in order)

1. **Frontend wiring** *(next — biggest piece; new sub-area)*
   - Fetch `GET /api/branding` at boot → theme via CSS variables (replace hardcoded
     `"HUDSON"` band + `#1f3a5f`/"Hudson Legal Tech" login colors).
   - Brand the login screen (`chat-frontend/components/auth-gate.tsx`) + sidebar.
   - **Hide/lock the scope picker** on a locked app (it's a flat source list today).
   - "No access — ask your bar / request access" screen for the 403 case.
2. **Prompt parameterization** — wire `product.system_prompt_key` + `product.jurisdiction`
   into the system prompt / `_scope_preamble` (multi-state insurance + ethics tone).
3. **Ethics tuning + freshness** — conservative abstention threshold for the scoped product;
   surface "current as of [date]" on every answer (leans on the existing edition-diff work).
4. **Provisioning** — access-code signup so ISBA can hand members in (CSV roster invite next).
5. **Pre-sale hardening** — close the known CSRF gap on cookie endpoints before any bar runs
   a security review (see `SECURITY_AUDIT.md`).

### Deferred (intentionally not built yet)
- Seats / billing / Stripe (Phase 2 — needed for per-seat *firm* sales, not bar deals).
- Per-org post-login co-brand ("Provided by &lt;bar&gt;" ribbon).
- Custom domains (`ethics.iowabar.org` via CNAME) for marquee deals.
- SSO (SAML/OIDC) for large bars/firms.
- Corpus depth: ethics opinions + disciplinary cases (turns "what does the rule say" into
  "is this OK"; the natural renew-driving fast-follow).

### Open questions
- Is ISBA a **mandatory/unified or voluntary** bar? Determines whether "all members" = all
  licensed Iowa attorneys or only dues-payers — drives reach and who signs the check.
- Real product name + brand for the app (currently "Iowa Ethics & Procedure").
- Production host for the locked app (e.g. `clerk.nick.law`) + DNS/cert setup.

---

## Appendix — code anchors

| Concern | Location |
|---|---|
| Tenancy models | `backend/apps/tenancy/models.py` |
| Entitlement union | `backend/apps/tenancy/entitlement.py` (`is_entitled`) |
| Admin (hand-provisioning) | `backend/apps/tenancy/admin.py` |
| Migration | `backend/apps/tenancy/migrations/0001_initial.py` |
| Seed command | `backend/apps/tenancy/management/commands/seed_ethics_procedure_demo.py` |
| Host → product | `backend/core/middleware.py` (`ProductResolutionMiddleware`) |
| App registration + middleware order | `backend/core/settings.py` |
| Public branding endpoint | `backend/apps/api/api.py` (`GET /branding`, `auth=None`) |
| Scope lock + entitlement gate | `backend/apps/api/chat.py` (`_enforce_product_scope`; called in `/chat` + `/chat/stream`) |
| System prompt / scope preamble (to parameterize) | `backend/apps/api/chat.py` (~`:442`, `_scope_preamble` ~`:708`) |
| Jurisdiction / Source (multi-state) | `backend/apps/corpus/models.py` |
| Hardcoded brand (to replace) | `chat-frontend/components/app-sidebar-brand.tsx`, `chat-frontend/components/auth-gate.tsx` |
