# Pricing Strategy — Market Analysis & Recommended Price Points

_Created 2026-07-11. Status: recommendation memo for Nick — feeds BILLING_PLAN.md blocking
item #2 ("Decide the actual price points"). Prices live in Stripe; nothing here is hardcoded._

## 1. The market context (what the web says, July 2026)

### National comps — AI legal research

| Product | Price | Notes |
|---|---|---|
| Westlaw Advantage (solo, self-serve) | $257/mo (1 state) – $400/mo (all states + fed) | 3-yr term; AI tier folded in Aug 2025 |
| Westlaw Advantage + CoCounsel Essentials | ~$639/user/mo | the "full stack" solo price |
| CoCounsel standalone | $225–500/user/mo | quote-driven configurator |
| Lexis+ (solo) | $114–300/mo base | AI add-on +$125–275 → $300–675 all-in |
| Paxton AI | $499/user/mo ($2,999/yr) | raised from ~$199–299 in 2025 |
| Alexi | $499–949/mo | usage-metered (memos/arguments) |
| Midpage | $99/mo | the credible low-cost AI research comp |
| Decisis | ~$145/mo ($1,740/yr) | free through many bar associations |
| vLex Fastcase | **free to ISBA members** (bar benefit) | premium upgrade ~$55/mo (NYSBA) / $995/yr value |

### The direct comp — LexIowa

Free / Solo **$49/mo** / Firm **$200/mo incl. 3 seats, +$50/seat**. Founding-beta rates,
publicly posted. This is the anchor an Iowa attorney comparing the two sites will see.

### Structure of the market

- **~7,200 licensed Iowa attorneys**; ISBA ~6,500 members (90% of licensed — highest
  voluntary-bar rate in the country). Every one of them already has *free search* via the
  vLex Fastcase bar benefit. We are not selling search; we are selling the graph,
  verification, currency, and AI layer on top — the same framing both we and LexIowa use.
- Iowa skews solo/small-firm. Solos budget ~1–2% of expenses on software and most don't
  budget for tech at all — the realistic solo price band for a *state-specific supplement
  to a free bar benefit* is **$30–100/mo**. Above $100 we're competing with Midpage
  psychology; above $250 we're competing with Westlaw itself.
- The national tools ($225–650/mo) are our pricing umbrella: we can be dramatically
  cheaper while being *better for Iowa specifically* (IAC, Acts, supersession notes,
  Iowa citation graph — things a 50-state tool does shallowly).

### Pricing principles this implies

1. **Anchor to LexIowa, not to Westlaw.** $49 is now the posted price of "Iowa AI legal
   research." Matching it with a demonstrably deeper product makes us the value leader;
   undercutting it signals we think we're worse.
2. **Trial, not free.** No free accounts and no beta-rate lock-ins (decision: Nick,
   2026-07-11). A card-up-front 7-day trial filters for intent, costs almost nothing in
   tokens, and avoids the two failure modes of freemium in legal AI: a permanent
   non-lawyer support/token drain, and "free" anchoring that cheapens the product
   (consistent with the existing no-free-framing marketing rule).
3. **Per-seat firm pricing, low friction.** Firms are where the money is
   (3–10 seat firms are common in Iowa); make adding a seat cheap enough that firms
   don't share logins.
4. **Margin sanity:** LlmUsage metering shows real cost per user; a heavy researcher on
   OpenAI-class models with RAG costs roughly $5–20/mo in tokens. At $49 that's a
   60–90% gross margin. Keep the existing dollar budget caps as the runaway-stop
   (suggest ~$25/mo cap on Solo, ~$40/seat on Firm, soft-landing message → upsell).

---

## 2. Recommended price points — core product (Hudson)

| Tier | Price | What's in it |
|---|---|---|
| **Trial** | **7 days free, card required** (Stripe `trial_period_days`) | Full Solo access; LlmUsage cap ~$5 for the trial week as abuse control; converts automatically unless canceled — with an email reminder before the charge (honest-framing rule) |
| **Solo** | **$49/mo** or **$490/yr** (2 months free) | Unlimited* research chat w/ verification, full search (vector+rerank, facets), citator + treatment + supersession notes, MCP connector (OAuth), saved research/history, email assistant |
| **Firm** | **$149/mo incl. 3 seats, +$39/seat** ($1,490/yr) | Everything in Solo + brief cite-check w/ PDF/DOCX upload, org console (seats/roles/invites), org usage dashboard, priority support |
| **Enterprise / Custom** | custom, from ~$5k/yr | Bar associations, county attorneys, legal aid, gov, custom corpus, SSO — existing "custom" tier |

\* "Unlimited" = fair use backed by the LlmUsage budget cap.

**No free tier, no founding-rate lock-in** (decision: Nick, 2026-07-11 — deliberately not
copying LexIowa's locked founding rates). Free accounts are replaced by the 7-day trial.
Two consequences to manage:

- **Beta sunset:** when billing goes live, existing beta users get clear notice
  (2–4 weeks) and then must subscribe — no grandfathered rate. This is compatible with
  the pricing page's promise ("pricing announced before launch, never a surprise
  charge"); the promise was notice, not a discount. If a goodwill gesture is wanted, a
  one-time first-year annual coupon is cleaner than a forever-lock and expires on its own.
- **SEO/discovery:** keep read-only corpus pages (statute/case/rule text) publicly
  crawlable *without any account* — that's marketing surface, not a free account, and
  it's the organic-search moat. Everything interactive (chat, search, MCP, email
  assistant) sits behind the trial/paywall.

**Vs. LexIowa, at these prices:**

| | LexIowa | Hudson |
|---|---|---|
| Solo | $49 | $49 — with a full web app, email assistant, cite-check uploads, deeper verification |
| 3-seat firm | $200 | $149 |
| 5-seat firm | $300 | $227 |
| 10-seat firm | $550 | $422 |

We match on solo (where price signals quality) and undercut ~25% on firm (where the
buyer does arithmetic). Against their free tier we counter with the trial + public
read-only corpus pages, not a free account.

**Changes required on the marketing pricing page:** raise Pro from **$29** to **$49**
($29 leaves money on the table and prices us *below* the visibly-thinner competitor),
replace the "Beta access" tier with the 7-day-trial framing, and update the FAQ answers
that currently promise ongoing beta access.

### What stays out of the tier table (deliberately)

- **Email assistant** — include in Solo+ rather than selling as an add-on. It's the moat
  feature nobody else has; use it to justify $49, don't nickel-and-dime it.
- **MCP connector** — paid tiers only (already the gating model). It's a reason to pay,
  not a separate SKU.
- **API for legal-tech vendors** — future SKU, usage-priced; don't build now.

---

## 3. Product line — pricing the rest of the portfolio

### 3a. ISBA Ethics app (scoped tenancy product — built)

Two ways to sell it; pursue in this order:

1. **Bar-partnership license (preferred):** flat annual license to ISBA to offer it as a
   member benefit — the exact model vLex/Decisis use in reverse. Price as a
   per-member-per-year number that's trivial next to dues: **$8–12/member/yr → a
   $50–80k/yr contract** at ~6,500 members. One sales motion, instant distribution,
   and it makes ISBA a partner instead of a channel conflict.
2. **Standalone fallback:** **$19/mo or $190/yr** individual, or **included in Hudson
   Solo/Firm** as a bundle sweetener. Ethics questions are episodic — low price,
   high perceived insurance value.

### 3b. Muni code product ("Codeworks" — mockup stage)

Comps: Municode self-publishing averages **<$2,800/yr**; traditional recodification
projects run **~$9,500** base; League-of-Minnesota-style "basic code" for tiny towns is
**$880**. Iowa has **943 incorporated cities**, the large majority under 1,000 population
— an underserved long tail that finds Municode expensive and slow.

Recommended structure (undercut the incumbents ~40–50%, win the tail):

| SKU | Price | Notes |
|---|---|---|
| Code hosting + publishing (static HTML, searchable) | **$950/yr** small (<2k pop), **$1,500/yr** mid (2k–10k), **$2,400/yr** large | vs Municode's ~$2,800 average |
| Initial codification / recodification project | **$3,500–8,000** one-time, population-scaled | vs ~$9,500 incumbent; AI-assisted drafting is our cost advantage |
| Ordinance supplements (attorney-reviewed) | **$45/page** or bundled into hosting at a page allowance | incumbents quote ad-hoc; posted pricing is itself a differentiator |
| Attorney-review workflow seat (for the reviewing law firm) | free | the muni law firm is the *channel*, don't charge the channel |

GTM stays as planned: validate via municipal law firms; the firm brings 10–40 towns.

### 3c. Treatises (long-term) & Open Casebooks

- **Treatises:** when they exist, sell per-title (**$15–25/mo per title**) and bundle
  "all treatises" into Firm. Don't price now; note that Firm at $149 leaves headroom
  for a future $199 "Firm + Treatises" tier.
- **Open Casebooks:** keep free — it's brand/GTM (professor→student→associate pipeline),
  not revenue. Revisit institutional licensing only if a school asks.

### 3d. Consulting

Keep the existing "talk to us" consulting lane at day rates; it's opportunistic revenue
and a sales channel for Enterprise, not a product to price-list.

---

## 4. Does the model clear? (back-of-envelope P&L)

Assumptions: infra (droplet + DO App Platform + Spaces + Postmark + Voyage/OpenAI base
load) ≈ **$500–800/mo** today; marginal LLM cost ~$5–20/user/mo on paid tiers.

| Scenario (12–18 mo out) | Mix | MRR | Est. gross margin |
|---|---|---|---|
| Conservative | 60 Solo + 8 firms (avg 4 seats) | ~$4.5k | ~70% |
| Base | 150 Solo + 20 firms (avg 4.5 seats) | ~$11.5k | ~75% |
| + ISBA ethics deal | base + $60k/yr license | ~$16.5k | ~80% |
| + 25 muni towns | + ~$2.5k/mo hosting avg | ~$19k | ~75% |

Penetration check on the base case: 150 solos + ~90 firm seats ≈ **240 paying attorneys
= 3.3% of licensed Iowa attorneys**. That's an ambitious-but-sane share for a
state-specific tool at $49 against a free bar benefit; the conservative case (~1.5%)
is very reachable. Break-even is roughly **25–35 paying solos**. With no free tier,
every active account is revenue-bearing after day 7 — the model clears earlier and the
funnel metric to watch is trial→paid conversion (healthy SaaS benchmark for
card-up-front trials is ~40–60%).

The concentration risk is the flip side of the focus strategy: the ceiling in Iowa alone
is low five-figures MRR. The muni product and the eventual second state are how the
ceiling moves; neither changes the launch pricing above.

## 5. Decisions requested (maps to BILLING_PLAN.md §7.2)

1. Stripe prices: **Solo $49/mo, $490/yr; Firm $149/mo (3 seats incl.), $39/seat** →
   4 Stripe Price objects, each with `trial_period_days=7` (card required at Checkout).
2. Update `marketing-frontend/app/pricing/page.tsx` before `NEXT_PUBLIC_BILLING_LIVE=1`:
   Pro $29 → $49, swap "Beta access" for the 7-day-trial tier, refresh the beta FAQs.
3. Set LlmUsage budget caps: Solo $25/mo, Firm $40/seat/mo, Trial $5/week.
4. Set the beta-sunset notice window (suggest 2–4 weeks) and send it before flipping
   billing on — no grandfathered rates, notice only.
5. Approve the ISBA-partnership motion for the ethics app before building any standalone
   checkout for it.
