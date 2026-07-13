# Brand + Domain Plan

**Status:** proposed, for review
**Date:** 2026-07-13
**Revised:** 2026-07-13 — second-pass audit merged (landmines #9–#17, all verified against code). Three decisions from Nick folded in: **full move, no forwarding** (`corpus.nick.law` is retired, not 301'd); **clerk/white-label deferred** out of this cutover (scope-lock gap noted as its launch gate); **dev must keep working** through every change (see the dev invariants in Part 5).
**Scope:** finalize the brand, move everything to `hudsonlegal.tech`, and deploy the marketing site for the first time.

---

## TL;DR

Three decisions, one deadline.

1. **Brand:** the company stays **Hudson Legal Technologies**. The product is **Hudson Corpus**. No mythological names. MCP and the email assistant are *doors into* Hudson Corpus, not separate brands. *(Mostly implemented already — see Part 1.)*
2. **Domains:** `hudsonlegal.tech` serves marketing from its **own** App Platform app. `app.hudsonlegal.tech` serves **one** application containing every first-party product, gated by entitlement. White-label tenants (ISBA) get their own hostname *(deferred — see landmine #9 and the block at the end of Part 7)*. *(Part 2.)*
3. **Timing:** we have **no real users yet** — 0 registered MCP OAuth clients, 6 assistant emails ever sent, and the ISBA product's hostname is still `clerk.localhost`. Every item that would normally make this migration expensive is **free right now, and never again.** So we do a *clean cutover*, not a careful migration, and we take two other free wins while the window is open. *(Part 3.)*

**The deadline:** all of this must land **before Stripe billing goes live and before the first real customer connects an MCP client.** After that, Stripe product IDs are permanent, MCP URLs live in users' local config files we cannot reach, and every email we've sent contains links we can't fix.

---

# Part 1 — Brand

## The decision

| | |
|---|---|
| **Company** | Hudson Legal Technologies (legal entity) · **Hudson** (wordmark) |
| **Product** | **Hudson Corpus** |
| **Muni codes** (future) | Hudson Codeworks |
| **Casebooks** (future) | Hudson Casebooks |
| **ISBA app** | *Iowa Ethics & Procedure* — carries **ISBA's** brand, not ours |
| **MCP endpoint, email assistant, citator** | **Features. Not named products.** |

### The rule

> **Name what you sell separately. Never name a feature.**
> Every name is a tax on the buyer's memory.

The one exception worth planning for: **the citator.** It is the only thing we are building that can become a *verb* — "Shepardize," "KeyCite it" are two of the most valuable brand assets in the history of legal publishing, and we are attempting the third citator anyone has built for Iowa. If we ever spend a single distinctive coined name, spend it there. Not on the platform, and not on a wrapper.

## Why not Daedalus / Icarus

Two independent reasons, either one disqualifying.

**The name is taken, four times over.** Dedalus Labs (YC-backed, $11M seed, AI agent infrastructure — owns the AI-space SEO), Daedalus (ex-OpenAI technical lead, $21M, AI manufacturing), Dedalus Group (one of the largest healthcare software companies in the world), and — fatally — **Daedalus Technology Group, thirty years in litigation support for technical legal cases.** Plus a live registered DAEDALUS trademark (#6000314, C4 Therapeutics). We would be the fifth Daedalus and the second selling into legal, in a trademark fight we might lose, unable to rank for our own name.

**The myth is wrong for this category.** Icarus is the canonical story of a machine that overreached, ignored its limits, and killed the person relying on it. We sell to a profession that watched a lawyer get sanctioned for filing AI-hallucinated citations. Our entire differentiator — the verification gate, the citator, the supersession tripwire — is *"this one won't fly you into the sun."* Naming a product Icarus hands LexIowa a slogan for free. Daedalus, meanwhile, built the Labyrinth: a structure whose defining property is that you get lost in it. For a legal research tool.

Set trademark aside entirely and the myth still fails on its own terms.

## Why "Hudson Corpus" works

**"Corpus" is a term of art our buyers already own.** *Corpus juris* — the body of the law. Corpus Juris Secundum sits on the shelf in every firm we sell to. It reads as native to lawyers rather than imported from Silicon Valley. It is also *literally true* about our lead over LexIowa: corpus breadth (Code + admin code + session laws + caselaw + court rules, soon municipal codes). "One corpus, three doors" is the argument, and the name does the work.

**"Hudson" is the trust asset.** Legal research is a publisher-led business — attorneys use "Westlaw" but they trust "Thomson Reuters." Law is a credentialed, personal-reputation trade where firms are named after people. An Iowa attorney putting his own name on an Iowa legal AI product is the most defensible thing we have, against LexIowa and against Thomson Reuters. It signals that someone is accountable for the output.

### On the eponymous concern (employees, ownership, and the escape hatch)

The stated worry: *future employees shouldn't feel they're building someone else's name.*

It's a real concern, but misdiagnosed in two ways.

- **"Hudson" doesn't read as a person.** To anyone who hasn't met Nick it's a river, a valley, a bay — and a town in Iowa. It parses as a place-name institution (Lincoln Financial, Jefferson Health), not as "Nick Hudson & Associates." Nobody at John Wiley & Sons feels they work for John Wiley. Surnames stop referring to people the moment the institution outgrows them — and that is the *success* case.
- **The thing actually wanted is solved by equity, not by a wordmark.** If an employee feels they're building someone else's company, the cause is the cap table and who holds decision rights. Give people real ownership and authority and they will not care what is on the door. Withhold those and renaming the company to Daedalus buys nothing.

**The escape hatch, built anyway (free insurance):** every user-visible brand string now reads from one constant per codebase.

- `backend/core/brand.py`
- `chat-frontend/lib/brand.ts`
- brand block in `marketing-frontend/lib/site.ts`

A future rename is an edit to **three files**, not a 90-string sweep.

Deliberately **not** parameterized: the Django app label `apps.corpus` and its tables. "Corpus" there means *the body of law* — a domain term that survives any rebrand. It is the thing that looks scariest in a naive grep and is actually a non-issue.

## What's already done (uncommitted, on `main`)

The audit found **three different names shipping simultaneously**: marketing said "Hudson Corpus," the pricing page said bare "Hudson," and the OAuth consent screen, the MCP server, the assistant page header, the onboarding wizard, the account page, and the Terms of Service all said **"Iowa Legal Corpus."** A user signed up on a page saying one name and landed in a product calling itself another, then accepted a contract naming a third entity.

Converged on **Hudson Corpus** across every live surface, routed through the brand constants. Verified by *rendering* the surfaces, not by grepping:

- OAuth consent screen now reads *"Claude Desktop is requesting access to the **Hudson Corpus** MCP server on your behalf."*
- `/.well-known/oauth-protected-resource` → `resource_name: "Hudson Corpus MCP Server"`
- NinjaAPI title, app chrome, onboarding, account page, Terms — all converged.
- **MCP demoted** from a brand ("Corpus MCP") to a door ("MCP endpoint"), alongside "Email assistant." Route `/products/mcp` unchanged so no links break.

**Terms of Service — flagged for your call.** The ToS named the counterparty as "Hudson Legal Tech" (not the entity's actual name) and the service as "Iowa Legal Corpus." Both corrected. **`TOS_VERSION` was deliberately NOT bumped** from `2026-06-10` — it's the same service under its correct name, and bumping would force every existing user to re-accept over a copy fix. Overrule if you disagree.

**Verification:** Django check clean; both frontends typecheck clean; backend suite shows **21 failures before and after, byte-identical** — all pre-existing billing/tier-gating from `BILLING_REQUIRE_PAID` being on in dev. Zero regressions, confirmed by stashing and re-running rather than by inspection.

---

# Part 2 — Domain architecture

## The target

```
hudsonlegal.tech            →  marketing site        [ITS OWN App Platform app]
www.hudsonlegal.tech        →  301 → apex

app.hudsonlegal.tech        →  THE app  [one login · one session · one bill]
    /corpus                       Hudson Corpus       ┐
    /codeworks                    Hudson Codeworks    ├── entitlement-gated paths
    /casebooks                    Hudson Casebooks    ┘
    /mcp                          MCP endpoint
    /api, /admin                  Django

clerk.hudsonlegal.tech      →  ISBA white-label: scope-locked, own brand, own front door
                               [DEFERRED — not in this cutover; landmine #9 gates it]
                               (longer term: an ISBA-owned domain, CNAME'd to us)

mail.hudsonlegal.tech       →  email assistant (dedicated sending subdomain, never the apex)
```

## Why one app for all first-party products

The dominant modern pattern for selling several products to the *same* buyer is **one marketing apex, one app host, products as paths, entitlements deciding what's unlocked.**

- **Stripe** — `stripe.com` markets; `dashboard.stripe.com` is the single app. Billing, Connect, Radar, Issuing are *tabs*, not hostnames.
- **Atlassian** — `atlassian.com` markets; your org lives at `yoursite.atlassian.net`; Jira and Confluence are paths.
- **Linear, Vercel, Notion, Figma** — same shape.
- Google's `mail.` / `docs.` / `drive.` split is the visible counterexample, but that's 25 years of acquisitions at consumer scale. Nobody starting today builds it, and it costs them enormously in identity plumbing.

**The reason one host wins is session.** Host-per-product forces a choice between separate logins per product (awful) or cross-subdomain cookie sharing (a security hole — see below). One host means one login, one session, one billing surface, one entitlement check. And cross-sell becomes free: a Corpus subscriber *sees* Codeworks in the nav, greyed out with "add to plan." On a separate host they'd never learn it exists.

**Therefore: no `corpus.hudsonlegal.tech`.** Corpus is a first-party product sold to our own buyers. Giving it its own hostname fragments auth and billing to buy nothing.

## Why the white-label tenant *does* get its own host

`tenancy.Product.hostname` already calls itself *"the locked front door,"* and `allowed_source_slugs` scope-locks it. That machinery is correctly *designed* — but the second-pass audit found it is only *enforced in chat* today: search, browse, verify, research, and the MCP server never read `request.product` (landmine #9). An ISBA member must not see Hudson Corpus, must not see our pricing, must not learn the rest of the suite exists — and until #9 is fixed, a clerk-host user could simply open `/browse` and see everything. **Clerk is deferred out of this cutover (Nick, 2026-07-13); fixing #9 is its launch gate.**

### The rule worth writing down

> **A hostname is a *visibility* boundary, not a *product* boundary.**
>
> **One host** when the user *should* see the whole suite — entitlement decides what's unlocked.
> **A separate host** when the user *must not know* the rest exists — white-label, co-brand, different buyer.

## Why marketing must be its own App Platform app

Three reasons. The security one is the strongest, and it isn't the one usually cited.

**1. Trust zones.** Marketing is where third-party JavaScript goes to live: analytics, ad pixels, a HubSpot tag, a chat widget, A/B testing. The app is where session cookies and confidential client matters live. Because cookies are **host-scoped**, a compromised marketing vendor script on `hudsonlegal.tech` **cannot read a session cookie** scoped to `app.hudsonlegal.tech` — the browser will not send it. Put them on one origin and every marketing tag we ever paste runs with full access to our users' authenticated sessions. For a product whose pitch is that lawyers can trust it with privileged material, that is not a nice-to-have.

**2. Blast radius.** A marketing traffic spike (a good article, a Product Hunt day) must not contend with the app serving paying customers, and a copy typo must not require redeploying Django + workers + the SPA.

**3. Cadence.** We will ship marketing changes ten times more often than app changes.

**Honest caveats — "most secure" deserves precision:**

- **Subdomains of one apex are still "same site."** `hudsonlegal.tech` and `app.hudsonlegal.tech` share a registrable domain, so `SameSite=Lax` does **not** treat traffic between them as cross-site. A separate host buys **cookie isolation**, not SameSite protection. The actual CSRF defense is the token (`apps/api/session_auth.py:43,46-59`) — correctly wired today. Maximal isolation would mean a wholly *different registrable domain* for the app, which nobody does because it costs the brand. **Same apex + host-scoped cookies + CSRF tokens is the standard, correct answer.**
- **Cookie tossing.** Any sibling subdomain can set a `Domain=.hudsonlegal.tech` cookie that shadows `csrftoken`. The defense is the **`__Host-` cookie prefix**, which forbids a `Domain` attribute outright. See Part 3.
- **It is more infra.** Two app specs, two builds, and `NEXT_PUBLIC_APP_URL` / `API_ORIGIN` must be kept in sync across them. Real cost, small.

**The DO-specific mechanic:** it isn't a law of nature that marketing needs its own app. It's that `.do/app.yaml` uses **path-based ingress with no host matching** (`/api`, `/mcp`, `/admin` → Django; `/` → chat-frontend). Attaching the apex to that same app would serve **the chat app** at `hudsonlegal.tech/`. A second app is the clean way to get a second origin.

**And a discovery:** `marketing-frontend` has **no Dockerfile and no component in `.do/app.yaml`.** It has never been deployed — it only runs on localhost:3001. Marketing at the apex is a **first deployment**, not a re-point. (The `hudsonlegal.tech` string already in the OG card was aspirational.)

---

# Part 3 — The clean-cutover window

## What the data says

Measured against the dev droplet's clone of prod (**sanity-check against live before acting**):

| | count | consequence |
|---|---|---|
| Registered MCP OAuth clients | **0** | Nobody must re-register or re-authorize. The single most expensive item on the migration list **does not exist.** |
| Live OAuth tokens | **0** | — |
| API keys | 7 | Almost certainly ours + tests. Whoever holds them has `corpus.nick.law/mcp` in a local config — ours to hand-update after the move. |
| Assistant emails ever sent | **6** | Six emails in the world contain `corpus.nick.law` links. They die when the domain is retired — accepted (recipients are allowlisted testers/us). |
| `Product.hostname` (ISBA) | `clerk.localhost` | Confirms the white-label front door **was never live on any real host.** |
| Stripe | not live | Product IDs are still free to change. |

**Conclusion: every item I previously called "permanent" or "expensive" is free right now, and the window closes the moment a real customer signs up.**

## Two decisions I am reversing

Both were made on the premise that real users had configs in the wild and links in their inboxes. **That premise is false.**

**1. Rename the MCP wire ID: `iowa-legal-corpus` → `hudson-corpus`.**
My argument for freezing it was that renaming would orphan connectors already written into users' `claude_desktop_config.json`. With zero OAuth clients, there is nothing to orphan. Freezing it *now* would mean carrying the dead brand in the wire protocol forever, for nobody's benefit. **Rename it now, then freeze it forever.**

**2. Adopt `__Host-` cookie prefixes** (`__Host-sessionid`, `__Host-csrftoken`).
This closes the cookie-tossing hole on the new multi-tenant apex. It normally costs a forced logout of every user — **which costs nothing today and will never be this cheap again.** Prod-only: the rename must live inside the `if not DEBUG:` block, or dev over plain HTTP breaks (landmine #11). `apps/api/session_auth.py:56` reads `settings.SESSION_COOKIE_NAME` and follows automatically; the one code change is `chat-frontend/lib/csrf.ts:16`, whose regex must accept both names.

## What this buys us

We do a **clean cutover**, not a careful migration — and per Nick (2026-07-13), a **full move, no forwarding**:

- `corpus.nick.law` is **retired outright — no 301, no alias kept, no compatibility scaffolding.** (The second-pass audit found the 301 wasn't buildable as originally written anyway: DO ingress redirects are path-matched with no host matching, so an alias domain would have dual-served the whole app — see the note under landmine #6.) The six emailed links die and the seven API-key holders (us) hand-update their configs. The only dual-domain moment is a short overlap during the cutover deploy so the new domain's cert can issue before the old one is dropped — that's downtime insurance, not forwarding.
- `clerk.nick.law` needs **no coordination** — it was never live. (The clerk host is now deferred out of this cutover entirely; see landmine #9 and the deferred block in Part 7.)
- The old sending domain needs only a **short** MX overlap, not an indefinite one.

---

# Part 4 — Landmines (found in audit; each would have caused real damage)

### 🔴 1. Stripe returns and org-invite links would silently point at the marketing site

`backend/apps/billing/api.py:151-167` picks a return-URL base from a fallback chain:

```python
STRIPE_RETURN_BASE_URL  →  settings.APP_URL  →  CORS_ALLOWED_ORIGINS[0]  →  EMAIL_LINK_BASE_URL
```

**`APP_URL` does not exist in `backend/core/settings.py`.** Confirmed by grep. So in production the chain silently lands on **`CORS_ALLOWED_ORIGINS[0]`**.

The trap: the moment someone adds `https://hudsonlegal.tech` to `CORS_ALLOWED_ORIGINS` — a natural-looking "fix" when wiring up the marketing forms — every Stripe Checkout `success_url` / `cancel_url` (`:263-267`), every billing-portal `return_url` (`:306`), and **every org invitation email link** (`apps/api/orgs.py:300-316`, `:327`) starts pointing at a site with no `/account/billing` and no `/invite/<token>` route. **Paying customers stranded mid-checkout.**

**Fix:** define a real `APP_URL` setting and set `STRIPE_RETURN_BASE_URL` explicitly. Never let this resolve by accident.

### 🔴 2. Adding the apex to CORS would make it CSRF-trusted against the app

`settings.py:420-422` feeds `CORS_ALLOWED_ORIGINS` into `CSRF_TRUSTED_ORIGINS`, and `CORS_ALLOW_CREDENTIALS = True` (`:411`). So any origin added to the CORS list becomes a credentialed, CSRF-trusted origin against the app host. An XSS on the marketing site would convert into authenticated read/write on the app.

**The marketing forms do not need a CORS entry at all** — they proxy **server-side** (`marketing-frontend/app/api/contact/route.ts:16`, `.../subscribe/route.ts:14` → `${API_ORIGIN}/api/marketing/*`). The browser never talks to the backend cross-origin.

**Fix:** `CORS_ALLOWED_ORIGINS` stays at exactly **one** entry: `https://app.hudsonlegal.tech`. Add a comment saying why, because this looks like a bug to the next person.

### 🔴 3. An unknown Host fails **open**

`core/middleware.py:41-44,73` — `ProductResolutionMiddleware` maps an unrecognized Host to `product = None`, and `product = None` **is the unlocked, full-corpus flagship.**

So if `clerk.hudsonlegal.tech` goes live in DNS + `ALLOWED_HOSTS` before the `Product.hostname` row is updated, **the ISBA front door serves our entire flagship corpus with the scope-lock silently gone.** Entitlement still gates *access*, but the *scope lock is host-derived.*

**Fixes:** (a) the DB row update must **precede** the DNS cutover — and note prod has **no migrate job in the app spec**, so this is a manual step; (b) consider failing **closed** for hosts matching a known product-subdomain pattern.

### 🟠 4. `Product.hostname` case-sensitivity bug

`core/middleware.py:72` lowercases the *request* host; `tenancy/models.py:118-121` `Product.save()` **never lowercases `hostname`**. A row seeded as `Clerk.HudsonLegal.tech` can never match any request — producing failure mode #3 silently. Fix while touching these rows anyway.

### 🟠 5. `SITE_URL` silently defaults to localhost

`marketing-frontend/lib/site.ts` → `SITE_URL = NEXT_PUBLIC_SITE_URL ?? "http://localhost:3001"`. It's a `NEXT_PUBLIC_*` var, so it's **baked at build time**. If it isn't set on the new marketing app's build, the production **sitemap, robots.txt, and every OG/canonical tag emit `http://localhost:3001` URLs.** Silent, and very bad for SEO on day one.

### 🟠 6. HSTS preload is effectively irreversible

`settings.py:456-458` (plus both `next.config.ts` files) set `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` **and** `PRELOAD = True`. Preloading `hudsonlegal.tech` locks **every future subdomain** — including partner, white-label, and staging hosts that don't exist yet — to HTTPS-only, permanently. This is a deliberate choice, not something to sleepwalk into. (The original plan's corollary — keeping valid TLS on a `corpus.nick.law` redirector indefinitely — is moot now that the domain is retired with no redirect. Note also that no host-based 301 was actually buildable inside the one app: Django has no host-redirect machinery, `next.config.ts` redirects are path-only, and DO ingress redirect rules match paths, not hosts — an alias domain would have served the full app.)

### 🟡 7. Two contradictory comments about `${APP_DOMAIN}`

`.do/app.yaml:87-91` says it's the bare `.ondigitalocean.app` host; `DEPLOY.md:377-379` says it follows the primary custom domain. `CSRF_TRUSTED_ORIGINS` depends on which is true. **Resolve empirically, or just pin the origin literally and stop depending on it.**

### 🟡 8. Deploy-mechanics traps already documented in the spec

- `.do/app.yaml:5-8` — re-applying the spec **wipes panel-attached domains.** This is how `corpus.nick.law` was lost once already. Domains must live in the spec.
- `.do/app.yaml:23-34` — always apply from a live `doctl apps spec get`, **never** straight from the repo file, or `SECRET_KEY` is blanked and every session dies.
- **There is still no migrate job in the live spec.** Prod migrations are manual. Any DB step below is a hand-run command.

## Second-pass audit findings (2026-07-13, all verified against code)

### 🔴 9. The white-label scope-lock is enforced in chat ONLY — *parked, but it gates any white-label launch*

`_enforce_product_scope` runs in exactly two places: the chat endpoints (`apps/api/chat.py:1771`, `:1806`). **Search, browse, verify, research, and the MCP server never read `request.product`** (verified by grep — zero references in `search_common.py`, `browse.py`, `verify.py`, `research.py`, `mcp_server/server.py`). A user on a white-label host can call `/api/search` or open `/browse` with any `source_slug` and read the entire flagship corpus. Entitlement gates *feature access*; nothing outside chat clamps *scope*.

**Per Nick (2026-07-13): not a blocker for this migration — clerk won't go live for a while — but it MUST land before any white-label hostname serves a real user.** Tracked as the ISBA app's launch gate, not a cutover step. (The clean fix is enforcing the clamp once, centrally — e.g. in the source-resolution layer all of those endpoints share — rather than copying the chat check into each endpoint.)

### 🔴 10. MCP OAuth's routes are un-routed — `/.well-known` and `/oauth` fall through to the chat frontend

`/oauth/*` and `/.well-known/oauth-*` are Django views (`apps/mcp_server/urls.py:21-46`, mounted at the root via `core/urls.py`), but the app spec has **no ingress rule for them** — they fall into the `/` catch-all → chat-frontend → 404. The spec's own comment (`.do/app.yaml:137-139`) says to add the rule "when OAuth lands"; OAuth landed (341a13c), the rule was never added. **The original runbook touched domains but never ingress — a fresh MCP connect on the new domain (its own step-10 verification item!) would have failed.** Fixed in the runbook: route `/.well-known` and `/oauth` to the `statutes` component, above the catch-all.

Related: `MCP_OAUTH_ISSUER` is absent from the live spec, so the issuer currently floats with the request Host — and there are **two** independent resolvers (`oauth.py:77-89` and `auth.py:68-86` for the 401 challenge), both reading the same env var. Pinning the env covers both; on a multi-host app an unpinned issuer is unstable.

### 🟠 11. `__Host-` cookie prefixes would break dev

Cookie `Secure` flags are only set when `DEBUG` is off (`settings.py:449-453`), dev runs over plain HTTP, and browsers **silently drop** `__Host-`-prefixed cookies that lack `Secure` — dev login would just stop working. The rename must be DEBUG-conditional, and `chat-frontend/lib/csrf.ts:16` reads the cookie by literal name in a regex, so it must accept **both** names (prod `__Host-csrftoken`, dev `csrftoken`). Good news: `apps/api/session_auth.py:56` already reads `settings.SESSION_COOKIE_NAME` dynamically and follows automatically, and login/logout go through Django's `login()`/`logout()` (no cookie names hardcoded anywhere in the backend) — the only frontend touch is the csrf.ts regex.

### 🟠 12. The wire-ID rename is NOT a constants edit

The user-facing install snippets hardcode `iowa-legal-corpus` instead of importing `MCP_SERVER_ID`: `chat-frontend/app/(app)/account/page.tsx:808`, `chat-frontend/app/classic/account/page.tsx:1158`, `marketing-frontend/app/products/mcp/page.tsx:93,102`, `backend/apps/mcp_server/README.md:101` (plus the carbon mockup). The backend is clean — `server.py:33,77` imports the constant. Fix: wire the snippets to import the constants *while* renaming, so the next rename actually is a constants edit.

### 🟠 13. A Stripe webhook URL change mints a NEW signing secret

The webhook route is `/api/billing/webhook` (`billing/api.py:325`) and signature verification reads `settings.STRIPE_WEBHOOK_SECRET` (`billing/stripe_api.py:60-61`). Registering the new-domain endpoint in the Stripe dashboard issues a **new signing secret**; if the env var isn't rotated in the same step, every webhook 400s and paid subscriptions silently never activate. Added to the runbook.

### 🟠 14. The invite-link chain and the Stripe chain disagree

`apps/api/orgs.py:300-316` `_app_base_url()` skips `STRIPE_RETURN_BASE_URL` and has no last-resort fallback — a misconfigured deploy emails a **relative** `/invite/<token>` link. The billing chain also has a fifth fallback the original audit missed: `request.build_absolute_uri("/")` (`billing/api.py:167`), i.e. whatever host the request arrived on. The fix folds into landmine #1: define `APP_URL` and make **both** chains read it, identically.

### 🟡 15. "Bumping TOS_VERSION forces re-acceptance" is not actually true

Re-acceptance is gated solely on `onboarding_completed` (`chat-frontend/components/auth-gate.tsx:174`, `accounts.py:266`); nothing anywhere compares a user's stored `tos_version` against `CURRENT_TOS_VERSION` (`accounts.py:61`). The don't-bump decision in Part 1 stands — but the comments at `accounts.py:58` and `terms/page.tsx:11` promise an enforcement mechanism that doesn't exist. Latent gap for the first *real* ToS change: build the version-comparison gate then.

### 🟡 16. Strip-list items the original audit missed

- `chat-frontend/components/carbon/sign-in.tsx:67` — literal `corpus.nick.law` rendered on the **sign-in screen**.
- `backend/core/settings.py:91,105` — `EMAIL_LINK_BASE_URL` defaults to `https://corpus.nick.law` and `CONTACT_FROM_EMAIL` to `assistant@mail.nick.law`. Env-overridable, but prod currently **relies on** the `EMAIL_LINK_BASE_URL` default (it's not set in the live spec) — so this default is load-bearing today.
- `backend/apps/tenancy/management/commands/seed_ethics_procedure_demo.py:57` — seeds `support@nick.law`.
- `chat-frontend/app/terms/page.tsx:379` and `app/(app)/account/billing/page.tsx:453` — `mailto:nick@nickhudson.me`, and `CRAWLER_CONTACT` in `brand.py:32` is also `nick@nickhudson.me`: a **third** first-party domain in play. Decide its future deliberately (fine to keep — just make it a decision).
- ~25 test assertions pin `corpus.nick.law` / `mail.nick.law` (`mcp_server/tests/test_oauth.py`, `test_http_app.py`, `mail/tests/test_render.py`, `test_email_assistant.py`, `api/tests/test_paywall.py`). They keep passing while defaults keep today's values (Tranche 1 is safe); budget for updating them whenever the defaults flip.

### 🟡 17. The app host has no robots.txt and no sitemap

The chat app emits neither, and it hosts genuinely public content (`/browse`, case pages, `/terms`). Whether `app.hudsonlegal.tech` is indexable is currently **undecided-by-accident**. Decide deliberately: if marketing at the apex is the SEO surface, ship an explicit robots.txt on the app host — allowing the public browse surfaces or blocking everything, on purpose.

---

# Part 5 — Tranche 1: code prep

**Status: BUILT 2026-07-13.** Uncommitted on `main`. See the "What actually landed" block at the end of this part.

**Goal: make every host and origin config-driven while keeping today's values as defaults.** The cutover then becomes DNS + env + dashboards, with **zero code changes under time pressure.**

> ### ⛔ Correction: this tranche was mis-labelled "safe, no production change"
>
> It isn't, and the reason is `deploy_on_push: true` on **every** component (`.do/app.yaml:183, 215, 231, 269, 304, 322`). **Merging Tranche 1 to `main` auto-deploys it.** There is no staging step and no manual gate. Three of its changes take effect in prod the moment they land, with no env flip:
>
> 1. **The `__Host-` cookie rename force-logs-out every session.** It lives inside `if not DEBUG:`, so it activates on the first prod deploy. Harmless *today* (that is the whole clean-cutover premise) and never this cheap again — but it is a production change, not a no-op.
> 2. **The MCP wire-ID rename breaks every existing connector config** — the 7 API keys, which are ours. Hand-update them.
> 3. **`robots.txt` de-indexes the app host.** `corpus.nick.law` is the only live host today and chat-frontend serves `/`, so `Disallow: /` goes live immediately. Acceptable — that domain is being retired anyway, and marketing (the intended SEO surface) has never been deployed, so there is no ranking to lose. But it is a deliberate consequence, not a side effect to discover later.
>
> **Therefore: do not push Tranche 1 and walk away.** Either push it as the first step of the cutover itself, or accept the three effects above knowingly.

**Backend**
1. **Define a real `APP_URL` setting** in `core/settings.py`, and make **both** base-URL chains — Stripe (`billing/api.py:151-167`) *and* org invites (`orgs.py:300-316`) — read it explicitly and identically (landmine #14). Kill the accidental `CORS_ALLOWED_ORIGINS[0]` fallback — make it an explicit, loud default rather than a silent guess.
2. Route `EMAIL_LINK_BASE_URL`, `CONTACT_FROM_EMAIL`, `MCP_OAUTH_ISSUER`, `MCP_HOST` through env with today's values as defaults. (Note landmine #16: prod currently *relies on* the `EMAIL_LINK_BASE_URL` source default — after cutover it must be set explicitly in the spec.)
3. **Fix the `Product.hostname` lowercase bug** (`tenancy/models.py` `save()`).
4. **Consider failing closed** on unknown hosts matching a product-subdomain pattern (landmine #3).
5. **Regression test: assert `SESSION_COOKIE_DOMAIN is None` and `CSRF_COOKIE_DOMAIN is None`.** This invariant is currently correct *by omission* — nothing documents or protects it, and setting a dot-domain cookie would be a one-line, silent, catastrophic tenant-isolation break.
6. **Rename the MCP wire ID** to `hudson-corpus`, then freeze it permanently. This is NOT just `core/brand.py` (landmine #12): the install snippets hardcode the literal. Rename the constants in `core/brand.py` / `chat-frontend/lib/brand.ts` / `marketing-frontend/lib/site.ts`, **and** wire the snippet sites to import them: `(app)/account/page.tsx:808`, `classic/account/page.tsx:1158`, `marketing-frontend/app/products/mcp/page.tsx:93,102`, `mcp_server/README.md:101`.
7. **Adopt `__Host-` cookie prefixes — prod only** (landmine #11): set `SESSION_COOKIE_NAME`/`CSRF_COOKIE_NAME` inside the existing `if not DEBUG:` block so dev over plain HTTP keeps the unprefixed names (browsers drop `__Host-` cookies without `Secure`). `apps/api/session_auth.py:56` follows automatically; the only code change is `chat-frontend/lib/csrf.ts:16`, whose regex must accept **both** names.

**Frontends**
8. Strip the hardcoded `corpus.nick.law` fallbacks: `chat-frontend/app/(app)/account/page.tsx:805` (MCP snippet), `components/carbon/primitives.tsx:253` (footer), `components/carbon/sign-in.tsx:67` (**sign-in screen** — missed by the first audit), `components/marketing/screenshot.tsx:19`, `marketing-frontend/app/products/email/page.tsx:32` (hardcoded `assistant@mail.nick.law`), `marketing-frontend/app/products/mcp/page.tsx:110`, `marketing-frontend/app/page.tsx:185`, `components/marketing/carbon.tsx:275`.
9. `marketing-frontend/lib/site.ts` — make `SITE_URL` fail **loudly** in a production build if `NEXT_PUBLIC_SITE_URL` is unset, instead of silently emitting localhost URLs (landmine #5). Guard on the production build only — `next dev` / dev builds must keep working with no env set.
10. **Terms of Service** (`chat-frontend/app/terms/page.tsx:115`) names `corpus.nick.law` as the service address. It's a legal document — update deliberately, with the same "don't bump the version for a naming correction" reasoning as Part 1. (And note landmine #15: a version bump wouldn't force re-acceptance anyway — the enforcement mechanism the code comments promise doesn't exist.)
11. **Add an explicit robots.txt** (and optionally a sitemap) to `chat-frontend` — decide the app host's indexability on purpose (landmine #17).

*The chat frontend is otherwise already domain-portable — `lib/iowa-chat.ts:10` uses a relative API base (`DJANGO_BASE = ""`). Nothing to do there.*

## Dev-keeps-working invariants (apply to every item above)

Nick's requirement: none of this may break local dev. Concretely:

- **Every new env var defaults to today's dev-compatible value.** `APP_URL` and friends default to the current behavior; nothing requires a new entry in `backend/.env` to boot.
- **`__Host-` names only when `not DEBUG`** (item 7). Dev cookies stay `sessionid`/`csrftoken` over plain HTTP; `csrf.ts` reads either name so one frontend build serves both worlds.
- **`SITE_URL` loud-fail is scoped to production builds** (item 9). `npm run dev` on :3001 keeps its localhost default.
- **No changes to the dev proxy path**: `chat-frontend/next.config.ts:58-66` rewrites `/api` → `localhost:8000` in dev only; nothing in Tranche 1 touches it.
- **Acceptance check before calling Tranche 1 done:** backend suite shows the same 21 pre-existing failures and no new ones; both frontends typecheck; a dev-droplet login + chat round-trip works over plain HTTP.

## What actually landed (2026-07-13)

All 11 items above are built. Adversarial review (4 lenses, every finding independently refuted-or-confirmed) surfaced **6 real defects — 2 of them introduced by this tranche's own fixes.** All 6 are fixed.

### The two regressions the tranche introduced, and the one it cured

**🔴 `APP_URL`'s prod default silently broke dev.** The fix for landmine #1 gave `APP_URL` a default of `https://corpus.nick.law` and deleted the `CORS_ALLOWED_ORIGINS[0]` fallback — but *that fallback was what made dev work.* Dev's `.env` sets no `APP_URL`, so dev inherited the production origin: a Stripe checkout on the dev droplet would have returned the browser to `corpus.nick.law`, and dev invite emails would have linked there. Killing the accidental fallback was right; it just silently took dev's behaviour with it. **Fixed:** `APP_URL` falls back to `http://localhost:3000` when `DEBUG` and no explicit `APP_URL` is set — checked against `os.environ`, because `env()` cannot tell "unset" from "set to the default."

**🔴 An MD5 password hasher under an over-broad predicate.** A test-speed optimisation added `PASSWORD_HASHERS = [MD5PasswordHasher]` inside the pre-existing `if "test" in sys.argv:` block. That predicate is a *membership test over the whole argv list* — so `manage.py changepassword test` (resetting a user named `test`) matches it, and would hash that user's real password with MD5 and persist it. Prod migrations here are hand-run against the live DB, so this was reachable. **Fixed:** the predicate is now `sys.argv[1] == "test"` — the subcommand, not any argument. Verified both ways: a real test run still gets fast MD5; `changepassword test` gets PBKDF2.

**🟢 Bonus — the "21 pre-existing failures" were one leaked flag.** They were never 21 independent problems. `backend/.env` sets `BILLING_REQUIRE_PAID=True` (to exercise the paywall in the dev UI), and that leaked into `manage.py test`, 402-ing every suite written before billing existed. The test-hermeticity block forced the four RAG flags off but not this one. **Fixed:** `BILLING_REQUIRE_PAID = False` under the test runner (tests that *want* the paywall turn it on with `override_settings`, which is what `test_paywall.py` already does). **The backend suite now runs clean — 224 tests, 0 failures, where the baseline was 21.**

### The other four

- **`PRODUCT_HOST_STRICT` / `FLAGSHIP_HOSTS` were never registered.** The fail-closed switch (landmine #3) was built into the middleware, which read them via `getattr` — but the settings agent never declared them, and **Django settings do not fall through to `os.environ`.** The switch was inert: setting it in the App Platform spec would have done nothing, silently, while appearing to work. Now declared in the env schema, default OFF.
- **`Product.hostname` normalisation only ran in `save()`**, not `clean_fields()`. The admin's `validate_unique()` therefore checked the *raw* value: given an existing `clerk.example.com`, typing `Clerk.Example.com` passed validation, then `save()` lowercased it into a duplicate-key `IntegrityError` — an unhandled 500 instead of a field error. Now normalised before validation.
- **`csrf.ts` needed the both-names regex** (landmine #11) — done, anchored so a cookie merely *ending* in `csrftoken` cannot match, and preferring `__Host-csrftoken` so a stale plain cookie lingering from before the cutover cannot shadow the one the server will actually validate.
- **Two `.rstrip("/")` copies remain** in the billing and orgs base-URL helpers. The chain itself is collapsed to one setting so it can no longer *drift* (landmine #14's real failure mode), but a shared `core` helper is the tidier end-state. Deliberately deferred: neither agent owned a neutral module.

### Verification actually run

`manage.py check` clean · `makemigrations --check` clean (the tenancy migration is committed) · both frontends `tsc --noEmit` clean · settings booted on **both** sides of the `DEBUG` conditional to prove the cookie rename fires in prod and *not* in dev · **`apps.tenancy` + `apps.mcp_server` + `apps.billing` + `apps.accounts`: 224 tests, OK.**

**Not run: the full backend suite.** The six affected apps are green, but nothing outside them has been exercised. Run it once before committing.

---

# Part 6 — Tranche 2: deploy the marketing site

**Status: BUILT 2026-07-13.** Uncommitted on `main`. Everything below the original three-step sketch is the record of what actually landed — the sketch was right in outline and wrong on five specifics that a 6-agent recon + adversarial review caught before any of them shipped. See "What actually landed" at the end of this part.

*Original sketch (kept for reference):*
1. Write `marketing-frontend/Dockerfile` (model it on the existing `chat-frontend/Dockerfile`). Marketing needs **SSR**, not a static site — it has server-side API proxy routes and ISR on `/articles`.
2. Create a **second App Platform app spec** for marketing:
   - domain: `hudsonlegal.tech` (PRIMARY) + `www` → 301
   - **build-time** env: `NEXT_PUBLIC_SITE_URL=https://hudsonlegal.tech`, `NEXT_PUBLIC_APP_URL=https://app.hudsonlegal.tech`
   - **runtime** env: `API_ORIGIN=https://app.hudsonlegal.tech`
   - keep the domain **in the spec**, not panel-attached (landmine #8).
3. Verify the contact/newsletter forms still work end to end through the server-side proxy — **without** adding anything to `CORS_ALLOWED_ORIGINS` (landmine #2).

## Five plan assumptions the recon REFUTED (verified against DO's live API / a real build / real DNS)

1. **"DO ingress is path-only; a host-based `www`→apex 301 isn't buildable."** FALSE. `match.authority.exact` + a `redirect` rule works and validates. The marketing spec uses it. (This also means the Part 7 note that a host 301 "wasn't buildable inside one app" is wrong — it simply wasn't needed there.)
2. **"Copy `chat-frontend/Dockerfile`."** That file declares **zero `ARG`s**, and DO passes `BUILD_TIME` envs to a Dockerfile build as `--build-arg` — which a Dockerfile with no matching `ARG` **silently discards**. A verbatim copy would build green and ship every CTA pointing at `localhost`. The marketing Dockerfile declares an `ARG`/`ENV` per `NEXT_PUBLIC_*` **and** documents the trap so a future copy-back is caught. (`chat-frontend/Dockerfile` had the same latent bug — its own `NEXT_PUBLIC_*` were `""` in every bundle ever shipped; fixed here too.)
3. **`${...}` bindables in a `BUILD_TIME` env** (e.g. `API_ORIGIN=${APP_URL}`) pass `doctl apps spec validate` and arrive **empty** at build — bindables are runtime-only for Dockerfile builds. BUILD_TIME envs use **literals only**.
4. **The Next standalone output does NOT nest** and **marketing has ISR that writes at runtime** — `.next/cache/{fetch-cache,images}` *and* `.next/server/app/*` (ISR rewrites prerendered pages in place). Under `USER node` with a root-owned `.next` all three `EACCES`, Next does not crash, and a newly published article never appears. The Dockerfile chowns the `.next` subtree (only that — least privilege). Proven load-bearing by a negative control.
5. **The pricing page was already correct** (Solo $49 / Firm $149 + $39/seat / no free tier) — the memory note claiming a stale $29+beta tier is closed.

## 🔴 The discovery that revised the migration model: production is behind Cloudflare (orange-cloud)

Both this plan and the first recon assumed DO-managed certs on grey-cloud DNS. **Prod is orange-clouded on Nick's own Cloudflare zone** — `corpus.nick.law` → Cloudflare anycast IPs, `server: cloudflare` + `cf-ray` on every response, with `x-do-app-origin` behind it; the `*.ondigitalocean.app` origin is *itself* Cloudflare-fronted. Consequences folded into the build:

- **Cloudflare guidance in the marketing spec was rewritten** to describe what actually runs (CF terminates TLS; DO is the origin), not a grey-cloud rule prod already violates. Adding the apex to App Platform for a DO-issued cert is now a **decision flagged for Nick**, not an assumed default.
- **`client_ip` was reading a Cloudflare address for every request.** With two appending proxy hops (CF → DO edge), the right-most-XFF read introduced in Tranche 1 returned CF's egress IP — collapsing the django-axes lockout (→ per-username lockout, a DoS primitive), the registration throttle, the marketing throttle, and the audit `source_ip` into one constant. **Fixed** by trusting Cloudflare's unforgeable `CF-Connecting-IP` (behind `TRUST_CF_CONNECTING_IP`, default off, on in the spec) and making the hop count stop being a security control. `record_event` now logs `xff_len`/`cf_ip` so **one real prod login settles the true chain length** instead of a guess. **`TRUSTED_PROXY_COUNT` was deliberately left at 1, not raised to 2** — an unmeasured number is the exact error being fixed; too-low degrades to a proxy address (blunt, safe), too-high reads a client-typed entry (forgeable).
  - Open bet for Nick: our CF zone proxies to a CF-fronted origin (a CF-to-CF O2O hop). CF's documented behaviour preserves the visitor IP in `CF-Connecting-IP`, but it **could not be observed from outside**. If it doesn't survive, `client_ip` degrades to a proxy address — *no worse than today*. The spec carries the one-command check.

## What actually landed (2026-07-13)

Built by three disjoint-file owners, then three independent verifiers (one adversarial); the adversarial pass found **six real defects — three critical — all fixed and re-verified to zero**. Final gates: **backend suite 1,220 tests OK** (was 1,185; +35 new IP/throttle tests), both frontends `tsc` clean, marketing prod build **green against the real article-less prod backend**, both app specs `doctl spec validate` clean, all three build guards fail red, no retired-domain string in the shipped bundle, dev still works over plain HTTP.

**New / changed files**

- `marketing-frontend/Dockerfile` (new) — 3 documented deltas from chat-frontend: the load-bearing `ARG`s, the ISR `chown`, the `public/` copy.
- `marketing-frontend/.dockerignore` + `chat-frontend/.dockerignore` (new) — keep `.env.local` out of a local/CI image (Next loads it ahead of the process env).
- `.do/marketing-app.yaml` (new) — the `hudson-marketing` app: `hudsonlegal.tech` PRIMARY + `www` ALIAS, the authority-exact 301 rule, BUILD_TIME literals, `API_ORIGIN` RUN_AND_BUILD_TIME, `MARKETING_PROXY_TOKEN` secret, honest Cloudflare guidance.
- `.do/app.yaml` — reconciled to the **live** spec (it was stale: missing the `/admin/{usage,users,articles}` rules and the MCP OAuth `/.well-known` + `/oauth` ingress rules), `${APP_DOMAIN}` comment corrected (it's the PRIMARY custom domain, **not** the `.ondigitalocean.app` host — resolves landmine #7), and the new IP-trust + `MARKETING_PROXY_TOKEN` envs added to the `statutes` service.
- `chat-frontend/Dockerfile` — the `ARG`s it never had (its `NEXT_PUBLIC_*` shipped empty).
- `marketing-frontend/lib/{site,api}.ts` — build guards on `NEXT_PUBLIC_APP_URL`/`_ASSISTANT_ADDRESS` (were silently defaulting to the retired domain — 71 clickable CTAs); `??`→`||` for the empty-string env case; **corpus stats + source lists now derived from the live `/api/browse/sources` at build time** so they can never again understate the corpus or advertise the dev-only Acts (prod: 123,424 docs / 4 populated sources); strict-on-**error** (not on-empty) article fetch.
- Marketing content truths: dropped the false "pages stay publicly readable" FAQ, the dead fallback article link (404s on prod), the four invented "coming soon" articles, and the "in pilot with Iowa practitioners" social-proof implication; `/products/mcp` now advertises the shipped OAuth 2.0; `/pricing` + `/products/corpus` no longer omit the Admin Code or over-claim Acts.
- Backend: `client_ip` rewrite + byte-safe token compare (a non-ASCII `X-Marketing-Proxy-Token` was a latent unauthenticated 500 on login once the token was set); throttle **persists the lead then throttles the notification** (was destroying over-limit leads before the row was written); `CONTACT_NOTIFY_EMAIL`/`CONTACT_FROM_EMAIL` failure now logs at ERROR instead of being swallowed; `MCP_HOST` finally routed through the settings schema (Tranche 1 item 2 had missed it).

### Deploy-order gates for Tranche 3 (these BLOCK the marketing deploy; discovered during the build)

1. **Publish ≥1 article on prod first.** `import_articles` was never run on prod (`/api/marketing/articles` → `[]`). The build tolerates empty now, but launching with zero articles ships a bare `/articles`; and the old fallback card pointed at a slug that 404s.
2. **Apply the `.do/app.yaml` OAuth ingress rules to the LIVE app before/with the marketing deploy** — `/products/mcp` now sells OAuth whose discovery endpoints 404 in prod today (they fall through to the SPA). Apply from a live `doctl apps spec get`, never the repo file (SECRET-wipe rule).
3. **Set `MARKETING_PROXY_TOKEN` to the same value on BOTH apps** or the lead funnel silently collapses to one throttle bucket for the whole internet.
4. **The marketing spec currently commits Tranche-3 values** (`app.hudsonlegal.tech`, `mail.hudsonlegal.tech`) that don't resolve yet. For a Tranche-2-only smoke test, point `API_ORIGIN`/`NEXT_PUBLIC_APP_URL` at `corpus.nick.law` (live today), or don't create the app until the app domain is up.
5. **`hudsonlegal.tech` has no A/MX record yet** — stand up DNS + mail before the first social share (the OG card and the `consulting@` mailto both assume it) and before `CONTACT_FROM_EMAIL` can use a Postmark-verified sender.

### Deferred deliberately (not blockers)

- **No `REDIS_URL` in prod** → `CACHES` is LocMem across 3 workers, which also silently no-ops the chat quota and API rate limiter. With per-IP keying now fixed, 3×LocMem is tolerable for marketing; provision Valkey as a separate ticket and add a boot assertion.
- **Node 20 is past EOL** but correct for Next 16 (`>=20.9`). Bump both Dockerfiles to a pinned `node:22-slim` in a separate PR (no Docker on the dev droplet to resolve a digest here).
- **Recapture marketing screenshots** — `assistant.png` still shows the old "Iowa Legal Corpus" brand and a "GPT-5 Mini" model picker baked into the pixels.
- **A real `/privacy` page** — a consent line + link was added under each lead form, but the policy itself is Nick's legal call.

---

# Part 7 — Tranche 3: cutover runbook

**This is a full move — `corpus.nick.law` is retired, not forwarded (Nick, 2026-07-13).** The only dual-domain moment is a short overlap while the new domain's cert issues, so the cutover itself has no downtime. Clerk is **out of scope** for this runbook (deferred block at the end).

0. **Pre-flight** — confirm the clean-cutover counts (0 OAuth clients / 0 tokens / 7 API keys / 6 emails) against **live prod**, not the dev clone. If a real MCP client has registered since the audit, this stops being a free move.
1. **DNS** — add `hudsonlegal.tech`, `www`, `app`, `mail` (no `clerk` yet).
2. **Postmark** — new sending domain `mail.hudsonlegal.tech`: DKIM CNAMEs, return-path/SPF CNAME, DMARC (start at **`p=none`** with `rua=`), MX for inbound. New sender signatures. **Sender reputation starts from zero — warm up before any volume.** While in the dashboard: split the shared dev/prod server token (known open gap from the email-assistant launch).
3. **DB** — create the new `mail.AssistantAddress` row for `assistant@mail.hudsonlegal.tech` (matching is exact-address, no wildcard — use `seed_assistant_address`). *(Manual — no migrate job in the live spec.)*
4. **App spec — domains AND ingress.** `domains:` → add `app.hudsonlegal.tech` as PRIMARY; **keep `corpus.nick.law` temporarily** so the app stays reachable while the new cert issues (removed in step 9 — this is downtime insurance, not forwarding). **Add the missing ingress rules (landmine #10):** `/.well-known` and `/oauth` → `statutes` component with `preserve_path_prefix: true`, above the `/` catch-all — without these, MCP OAuth discovery 404s on any domain. `ALLOWED_HOSTS` must include **every** host served during the overlap (`app.hudsonlegal.tech`, `corpus.nick.law`, `${APP_DOMAIN}`), or it's a 400 `DisallowedHost` on every request — including for the MCP component, which derives its transport-security allowlist from `ALLOWED_HOSTS` (421s otherwise).
5. **Env.** Every one of these is now a real, registered setting (Tranche 1) whose **default is today's value** — so a var you forget to set does not crash, it silently keeps pointing at the retired domain. Set all of them:

    | var | set to | if you forget |
    |---|---|---|
    | `APP_URL` | `https://app.hudsonlegal.tech` | **Every Stripe return URL and every org-invite email link points at the retired domain.** Defaults to `https://corpus.nick.law`. |
    | `CORS_ALLOWED_ORIGINS` | `https://app.hudsonlegal.tech` — **exactly one entry** | Adding the marketing apex makes it a credentialed, **CSRF-trusted** origin against the app (landmine #2). The marketing forms proxy server-side and need no entry. |
    | `CSRF_TRUSTED_ORIGINS` | pinned literally | — |
    | `EMAIL_LINK_BASE_URL` | `https://app.hudsonlegal.tech` | Emailed citation links die. **Prod relies on the code default today** — it is not in the live spec (landmine #16). |
    | `MCP_OAUTH_ISSUER` | `https://app.hudsonlegal.tech` | Absent today, so the issuer **floats with the request Host** — unstable on a multi-host app. Covers *both* independent resolvers (landmine #10). |
    | `STRIPE_RETURN_BASE_URL` | `https://app.hudsonlegal.tech` (or leave empty — it now falls through to `APP_URL`) | — |
    | `CONTACT_FROM_EMAIL` | the new **Postmark-verified** sender | Contact-form notifications bounce. |

    Leave `PRODUCT_HOST_STRICT` **off**. It is the fail-closed switch for unknown hosts (landmine #3) and it belongs to the clerk launch, not this cutover — turning it on with an incomplete `FLAGSHIP_HOSTS` locks out the flagship itself.
6. **Apply the spec from a live `doctl apps spec get`**, never from the repo file (landmine #8).
7. **External dashboards** — Postmark inbound webhook → `https://app.hudsonlegal.tech/api/email/inbound?token=…`. Stripe: register the new webhook endpoint `https://app.hudsonlegal.tech/api/billing/webhook`, **set the NEW signing secret it mints as `STRIPE_WEBHOOK_SECRET`** (landmine #13), then delete the old endpoint. Verify with a test event before trusting it.
8. **Deploy the marketing app** at the apex.
9. **Retire `corpus.nick.law`** — once step 10 verifies clean on the new domain: remove it from `domains:` and `ALLOWED_HOSTS` (spec re-apply, same live-spec rule), then delete the DNS record. No 301, no alias. Hand-update **our** configs that hold the old `/mcp` URL (the 7 API keys are ours); the six sent emails' links are accepted dead.
10. **Verify end to end**, and specifically: sign-in and session (new `__Host-` cookies visible in devtools); OAuth discovery documents fetchable at `https://app.hudsonlegal.tech/.well-known/oauth-authorization-server` and `.../oauth-protected-resource` (proves the new ingress rules, landmine #10); the OAuth consent screen and a fresh MCP connect; Stripe checkout round-trip **including a delivered webhook event**; an org invite email link (absolute URL, new domain); a contact-form submission; an inbound assistant email and its reply with new-domain citation links; marketing `sitemap.xml` / `robots.txt` / OG tags emitting **`hudsonlegal.tech`**, not localhost; the app host serving the robots policy chosen in Tranche 1 item 11; and a **dev-droplet smoke test** (login + chat over plain HTTP) to prove the cutover changed nothing local.

**Deferred: `clerk.hudsonlegal.tech` (white-label).** Not part of this cutover. Before it *ever* goes live: (a) **fix the chat-only scope-lock** — landmine #9 is the launch gate; (b) create/update the `tenancy.Product` row with the **lowercased** hostname *before* DNS resolves (landmines #3 and #4 — unknown hosts fail open to the full corpus); (c) add the host to `ALLOWED_HOSTS` and the spec `domains:`; (d) decide the long-term home (an ISBA-owned domain CNAME'd to us — open decision #3).

---

# Part 8 — What we are deliberately NOT doing

- **Not** giving Hudson Corpus its own hostname. It's a path in the one app.
- **Not** adding the marketing apex to `CORS_ALLOWED_ORIGINS`. The forms proxy server-side.
- **Not** forwarding `corpus.nick.law` at all — **no 301, no alias kept** (decided 2026-07-13). Full move; the old domain is retired outright once the new one verifies. The six emailed links die and our own seven API-key configs get hand-updated. (A host-based 301 wasn't buildable inside the one app anyway — DO ingress redirects are path-matched, not host-matched.)
- **Not** renaming the Django app label `apps.corpus` or its tables. "Corpus" there means the body of law.
- **Not** bumping `TOS_VERSION` for a naming correction (would force needless re-acceptance).
- **Not** renaming Stripe product IDs (`hudson-solo` / `hudson-firm` / `hudson-firm-seat`) — they're already correct under this brand. Just know they become **permanent** in live mode.

---

# Open decisions for you

*(Resolved 2026-07-13: no forwarding — full move, old domain retired. Clerk deferred out of this cutover; landmine #9 is its launch gate.)*

1. ~~**`.tech` vs `.com`.**~~ **RESOLVED 2026-07-13: ship on `hudsonlegal.tech`** (already owned; DNS live on Cloudflare).
   Checked before deciding, and the plan's premise was slightly wrong: **`hudsonlegal.com` is not "taken" — it is *parked on Afternic*, a domain brokerage**, which means it has an asking price rather than an owner using it. `hudson.legal` is **entirely unregistered** (a `.legal` TLD on the surname would read as native to the profession). Nick chose `.tech` for speed.
   **This stays cheap to revisit, on purpose.** Nothing in Tranche 1 hardcodes `.tech` anywhere — every host and origin is now env-driven. Buying the `.com` later and pointing it at the same app is a DNS + env change, not a second migration. What is *not* cheap is doing the cutover twice, so the door is deliberately left open rather than nailed shut.
2. ~~**HSTS preload on the new apex.**~~ **RESOLVED 2026-07-13: keep the HSTS headers, do NOT submit to `hstspreload.org`.** Strong protection for anyone who has visited, while preserving the ability to stand up an HTTP staging or partner subdomain later. Reversible; preload submission is not.
3. ~~**App-host indexability.**~~ **RESOLVED 2026-07-13: block the app host entirely** (`Disallow: /`, shipped as `chat-frontend/app/robots.ts`). The marketing apex is the only SEO surface. *Note the deploy consequence in the correction box at the top of Part 5 — this goes live the moment Tranche 1 is pushed.*
3. **Where does the ISBA app ultimately live?** `clerk.hudsonlegal.tech` works when the time comes, but a white-label product on *our* domain half-undermines the white-label. Longer term it should sit on an ISBA-owned domain, CNAME'd to us. (Deferred with the rest of clerk — see the block at the end of Part 7.)
4. **Still open — the third domain, `nickhudson.me`** (landmine #16): terms-page and billing-page support mailtos plus the crawler contact string point at Nick's personal address. Left untouched in Tranche 1 *on purpose* — it is a decision, not a cleanup. Fine to keep; just decide it rather than inherit it.
5. **Still open — where does the ISBA app ultimately live?** (was #3; deferred with the rest of clerk — see the block at the end of Part 7.)
6. **Timing.** All of this should land **before** Stripe goes live and before the first real customer connects an MCP client. (The live-count pre-flight is now runbook step 0.) **Note the `deploy_on_push` correction at the top of Part 5: pushing Tranche 1 *is* a production deploy.**

---

# Appendix — file reference index

| Concern | Location |
|---|---|
| Brand constants | `backend/core/brand.py` · `chat-frontend/lib/brand.ts` · `marketing-frontend/lib/site.ts` |
| Stripe return-URL chain | `backend/apps/billing/api.py:151-167`, `:263-267`, `:306`, `:51` |
| Org invite links | `backend/apps/api/orgs.py:300-316`, `:327` |
| CORS → CSRF coupling | `backend/core/settings.py:410-422` |
| Cookie settings | `backend/core/settings.py:452-458` |
| Host → Product resolution | `backend/core/middleware.py:37-73` |
| `Product.hostname` (lowercase bug) | `backend/apps/tenancy/models.py:73`, `:118-121` |
| OAuth issuer / audience | `backend/apps/mcp_server/oauth.py:75-113` |
| Emailed-citation link base | `backend/apps/mail/services.py:365-371` |
| Inbound email webhook | `backend/apps/mail/api.py:111-117` |
| Marketing forms proxy | `marketing-frontend/app/api/contact/route.ts:16` · `subscribe/route.ts:14` |
| App spec (domains, ingress, env) | `.do/app.yaml:5-11`, `:23-34`, `:92-104`, `:130-174` |
| Scope-lock enforcement (chat-only, #9) | `backend/apps/api/chat.py:1714-1754`, `:1771`, `:1806` |
| OAuth Django routes needing ingress (#10) | `backend/apps/mcp_server/urls.py:21-46` · missing-rule TODO `.do/app.yaml:137-139` |
| Second OAuth issuer resolver (#10) | `backend/apps/mcp_server/auth.py:68-86` |
| CSRF cookie read by name (#11) | `chat-frontend/lib/csrf.ts:16` |
| Wire-ID hardcoded snippets (#12) | `chat-frontend/app/(app)/account/page.tsx:808` · `classic/account/page.tsx:1158` · `marketing-frontend/app/products/mcp/page.tsx:93,102` · `mcp_server/README.md:101` |
| Stripe webhook + signing secret (#13) | `backend/apps/billing/api.py:325` · `stripe_api.py:60-61` |
| ToS acceptance gate (#15) | `backend/apps/api/accounts.py:61`, `:741-784` · `chat-frontend/components/auth-gate.tsx:174` |
| Host-default settings (#16) | `backend/core/settings.py:91` (`EMAIL_LINK_BASE_URL`), `:105` (`CONTACT_FROM_EMAIL`) |
