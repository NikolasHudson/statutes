# Competitive Plan — Responding to LexIowa

_Created 2026-07-10. Owner: Nick. Status: strategy memo + prioritized backlog._

> **Execution status — updated 2026-07-10 (later the same day).** P0 is DONE: the accuracy
> bundle is committed and shipped to prod main (Phase 3 `d5eb293`, PR9 `4c4adb7`, prompt
> hardening `8e263db`), plus two follow-ons committed since: attorney **construction notes**
> (`02d3dba` — CaseResearchNote kind=construction surfaced inside tool results, migration
> `0021`) and assistant streaming UX fixes (`a3f6229`). The one P0 remnant: **prod DB still
> needs `manage.py migrate corpus 0021`** (creates the CaseResearchNote table; no migrate job
> in the deploy). P1's top item is largely done too: the **Iowa Admin Code ingestion app is
> committed** (`b1cfd7b`) and fully live on dev — 17,690 rules ingested, approved, embedded,
> blending with statutes in retrieval. Remaining for IAC: Phase 2 surface wiring, prod
> migrate `0022` + data transplant. Then P1 continues with Iowa Acts, federal courts,
> constitutions.
>
> **Second update, same day.** IAC **Phase 3 is now done too** (`107cb58`): the citation
> parser reads all IAC forms (em-dash + "441 IAC 65.2"), and the statute↔regulation graph
> exists — 22,508 `reg_enabling` CrossReference edges on dev (96.6% resolved; the 761
> misses are session-law tokens the Acts corpus will absorb). The **prod transplant kit**
> is built and rehearsed green against a prod clone: `/home/dev/iac-prod-dump/load_iac.sh`.
> The **Iowa Acts ingestion plan** is drafted from live-source research
> (`IOWA_ACTS_INGESTION_PLAN.md`, uncommitted pending review): enrolled-bill RTFs are the
> parse target, an official amended-sections table gives 2,871 act→Code edges for 2024
> alone — the supersession feed.
>
> **SHIPPED TO PROD — 2026-07-10 evening.** Nick pushed `107cb58` (deploy ACTIVE), ran the
> prod migrations, and executed the transplant. Verified live on corpus.nick.law: the Iowa
> Administrative Code — 87 agencies, 1,820 chapters, 17,690 rules — with agency browse,
> admin-scoped search, r-sigil citations, and 22,508 statute↔regulation edges. **P1's top
> item (their only visible product lead) is neutralized in one day.** P1 continues: Iowa
> Acts (plan drafted), federal courts, constitutions.

## Why this document exists

On 2026-07-10 we found **LexIowa** (`https://lexiowa.com`), a direct competitor: an
AI research assistant over Iowa law, invite-only beta, for licensed Iowa attorneys.
It is brand new — `noindex`, zero Wayback history, unindexed by search engines, no
Terms/Privacy/About pages yet, domain behind GoDaddy privacy protection. It runs on a
DigitalOcean droplet (Next.js front end, a Python/FastAPI `uvicorn` backend behind
Caddy, Plausible analytics) and its AI layer is Claude via an MCP connector — the same
shape as us.

What makes it worth a formal response is not that it exists, but how precisely its pitch
overlaps ours. Its homepage tracks our own positioning almost line-for-line: the
statute↔case **citation graph**, **treatment signals**, **brief cite-check** as the
Firm-tier feature, the **Claude connector**, "real citations, not the invented ones a
general AI produces," and the explicit **"your ISBA / vLex Fastcase bar benefit gives you
search — we give you the graph"** framing. It even matches our tier names and price point
(Free / Solo **$49** / Firm **$200**, 3 seats +$50). This is either convergence on an
obvious market or someone who studied our work; either way, we can no longer assume we're
the only one telling this story in Iowa.

### Where we actually stand (the honest read)

We benchmarked their marketing claims against what our repo actually ships. The result is
reassuring: **on every headline feature LexIowa advertises, we have a shipped equivalent,
and in several cases a deeper one.** Their leads are narrow and specific.

> **Status verification — 2026-07-10.** Re-checked the actual code before executing this
> plan. The assistant tech has moved a lot since the first draft, and it makes our position
> *stronger*, not weaker. The working tree already contains, built but uncommitted: the
> Phase 3 authority-weighted retrieval work; a hardened assistant prompt (voice/register
> control, cross-reference following, a claim-splitting / res-judicata guard on volunteered
> strategy, an authority hierarchy, a currency re-check on user-cited authority, ethics-
> timeline logic); and **PR9 — a web-currency supersession tripwire** (`web_currency.py`,
> a new `CaseResearchNote` model + migration `0020`, an attorney-review queue, wired into
> the verification gate) that a standalone benchmark scored at 4/4 precision with 3 novel
> catches and 0 false positives. Net effect on this plan: the strategic analysis and the
> priority order are unchanged, but several items I had filed under "planned" in P2 are in
> fact **built and waiting to ship** — which makes P0 (ship the uncommitted work) even more
> clearly the single highest-leverage move, and shrinks P2 to "ship it, turn it on, and
> prove it."

**LexIowa's only real advantages:**
1. **Broader claimed corpus.** They advertise Iowa Administrative Code, Iowa Acts (2026),
   and federal courts that govern Iowa (8th Circuit + N.D./S.D. Iowa), plus constitutions
   "going in now." We ingest Iowa Code + Iowa Court Rules + full Iowa appellate caselaw
   only. This is the one substantive product gap a prospect comparing the two sites would
   see immediately. (Caveat: these are unverified beta claims and easy to overstate.)
2. **MCP OAuth.** Their Claude connector uses a full, spec-complete OAuth 2.0 server
   (dynamic client registration, PKCE, refresh, revocation). Ours is `X-API-Key`. Theirs
   is the more polished "point-and-click connector."
3. **A public, self-serve pricing page** with locked founding-beta rates. Ours is
   "talk to us."

**Our advantages to defend and market (they have no equivalent):**
- **Email assistant** — attorneys email in, verified answers come back. Nothing like it
  in their pitch.
- **A full research web app** — browse UI for statutes/cases (plus year-over-year edition
  diff), and a real search UI with intent routing, vector + rerank, facets, date
  histogram, and cited-by. Their product is framed as connector-only ("no app to install").
- **Deeper verification** — a deterministic citation/quote verification gate wired into
  the answer loop, a default-on currency/stale-use gate, and brief cite-check that accepts
  **PDF/DOCX uploads** (via docling), not just pasted text.
- **Accounts maturity** — shipped Terms of Service, onboarding, and versioned ToS
  acceptance. LexIowa has no legal pages at all yet.

**Shared gaps (neither of us has solved these — so they are not competitive
disadvantages *today*, but table stakes for any real launch):** no Stripe / self-serve
checkout, and no real attorney-license verification (both of us gate by disclaimer only).

### The strategy behind the priority order

Because their leads are narrow, "being competitive" is less about catching up and more
about three moves, in this order of leverage:

1. **Bank the work we've already done but haven't shipped.** The tree is dirty with
   Phase 3 retrieval + accuracy work. Shipping beats building; it's the cheapest lift and
   it compounds under everything else.
2. **Neutralize their one visible product lead** (corpus breadth) and **protect the
   battlefield the whole category is fought on** (citation accuracy). In legal AI,
   "verified citations" is the entire value proposition — a public accuracy miss is fatal,
   and our treatment v1 still has a ~1/3 false-positive rate that a competitor could
   exploit.
3. **Become able to win customers, then go get discovered.** We can't lose a market we
   can't transact in or that can't find us. But since LexIowa also can't transact yet
   (invite-only, no checkout), this is important-not-urgent relative to product/accuracy.

The list below is ordered by that logic: ship what's done → close the substantive gap and
harden accuracy → become sellable and discoverable → match polish and press our moat.

---

## The prioritized list

### P0 — Ship the uncommitted retrieval & accuracy work
**Why first:** The working tree already contains a large, built-but-uncommitted accuracy
bundle — the accuracy roadmap marks these 🟡 built-on-dev and calls Phase 3 "the highest
ratio item in the whole program: it's done — ship it." Shipping is the highest-leverage,
lowest-cost move on the board and it de-risks everything downstream. Nothing else should
start before the tree is clean and deployed. The bundle (verified 2026-07-10):
- **Phase 3 authority-weighted retrieval** — `retrieval.py`, `rerank.py`, `search.py`,
  `research.py`, with the benchmark set under `backend/benchmarks/caselaw/`.
- **Assistant-prompt hardening** — `chat.py`: voice/register, cross-reference following,
  the volunteered-strategy grounding guard, authority hierarchy, user-cited-authority
  currency re-check, ethics-timeline duties.
- **PR9 web-currency supersession tripwire** — new `web_currency.py`, `CaseResearchNote`
  model + migration `0020_caseresearchnote.py`, `answer.py` wiring, `admin.py` review
  queue, and the `RAG_WEB_CURRENCY_*` flags (default OFF).
- Execution notes: this is a **mixed** working tree (backend accuracy + a marketing-site
  redesign + the sign-in change + this doc) — commit it in **logical chunks**, not one
  blob. Run the standard gate battery first (`eval_search` + `chat_eval_domain_fit` +
  `chat_eval_adversarial`, Wilson-CI ship bar) and the migration on a clone. Commit locally
  is reversible; **push/deploy is outward-facing — get Nick's go-ahead before that step.**

### P1 — Close the corpus-coverage gap
**Why:** This is the *only* substantive product claim where LexIowa leads, and it's the
one a prospect sees at a glance when comparing feature lists. Each item neutralizes a
specific bullet on their homepage.
- **Iowa Administrative Code** — Iowa-native, fits our `Source → Node → NodeVersion`
  model; reuse existing ingestion patterns. (Highest priority within P1: they claim it, we
  have the machinery.)
- **Iowa Acts / session laws** — also unlocks current-awareness and the supersession
  program (statute-side changes to case currency).
- **Federal: 8th Circuit + N.D./S.D. Iowa** — bigger lift (new CourtListener courts, new
  citation-graph edges across state/federal), but they specifically advertise it.
- **Iowa & US Constitution** — cheap; closes the "going in now" claim outright.

### P2 — Harden the accuracy story
**Why:** "Real, verified citations" is the category's whole battleground and our current
strongest differentiator. **Update (2026-07-10): most of this is already built** — the
supersession/currency signal exists as PR9's web-verified `CaseResearchNote` layer, which
overrides wrong-sided phrase flags at answer time (it caught the Frohwein/Youngblut miss
the deterministic flag got backwards). So this priority collapses from "build" to "ship,
turn on, and prove," and largely rides along with P0.
- **Turn the flags on, shadow → prod**: `RAG_APPLICABILITY_CHECK` (PR8) and
  `RAG_WEB_CURRENCY_CHECK` (PR9) are default-off; enable in shadow, review traces, then on.
- **Stand up the attorney-review loop**: the `CaseResearchNote` review queue (admin) needs
  a human triaging adverse notes — approved notes feed the supersession pipeline, rejected
  ones are suppressed everywhere. This is what makes the signal trustworthy to advertise.
- **Drive down treatment v1 false positives** at the source (the ~1/3 FP phrase-scan): the
  confirm-only / never-drop LLM direction, and fix the `by_citation` attribution bug. PR9
  masks the symptom; this fixes the cause.
- **Publish a number**: precision/recall on treatment + citation verification from the gate
  battery — turn accuracy into a metric we can put on the marketing site, not an adjective.

### P3 — Reach commercial readiness
**Why:** Features don't matter for a product you can't sell. This is a shared gap with
LexIowa, so it's important rather than urgent — but whoever becomes self-serve first can
convert the beta waitlist into revenue.
- Self-serve billing (Stripe) wired to the existing free/solo/firm tiers and the
  Org/Subscription/seat models that already exist but are billing-deferred.
- A public pricing page with our own founding-beta rates (match their transparency; we
  already have the tier structure in code).
- Real **attorney-license gating** — today both products gate by disclaimer only. Being
  the one that actually verifies Iowa bar standing is a trust differentiator in this market.

### P4 — Open a public front door & sharpen positioning
**Why:** We are also `noindex` / invite-only. A discoverable site that tells the story is
how we stop ceding the narrative. Lead with what only we have.
- A public marketing site (we have `marketing-frontend`) that is indexable and tells the
  ISBA / vLex Fastcase "search vs. graph" story — the same framing they use, but backed by
  our broader surface area.
- Foreground the surfaces they can't match: the **email assistant**, the **full research
  app** (browse + search), and **upload-a-brief cite-check**.
- Publish Terms/Privacy and the accuracy claim from P2. (We already ship ToS; they don't.)

### P5 — Match connector polish & press the moat
**Why last:** Real but lowest-leverage. `X-API-Key` works today; OAuth is a polish gap in
the "point-and-click connector" story, not a capability gap.
- Add OAuth 2.0 to the MCP connector to equal their setup experience.
- Finish MCP P1 hardening already on the roadmap (durable audit logging, shared-store rate
  limiting across instances).
- Make the email assistant and research UI first-class in sales/marketing collateral —
  these are the things a connector-only competitor structurally cannot copy quickly.

---

## What we are explicitly NOT worried about

To keep focus: we do **not** need to build a citation graph, treatment signals, brief
cite-check, plain-English Q&A, or a Claude connector to "catch up" — we already ship all of
them. The temptation to react to their homepage feature-by-feature would waste our lead.
The gaps are narrow (corpus breadth, connector auth polish, commercial plumbing); the
advantages are real (email assistant, full research app, verification depth, accounts
maturity). This plan closes the former without stopping to rebuild what we already have.

## Appendix — feature comparison snapshot

| | LexIowa (claims) | Us (shipped) |
|---|---|---|
| Iowa Code / Court Rules / appellate caselaw | ✅ | ✅ |
| Iowa Admin Code | ✅ claimed | 🟡 ingested+embedded on dev (17,690 rules, `b1cfd7b`); surfaces + prod rollout pending |
| Iowa Acts / session laws | ✅ claimed | ❌ (planned) |
| 8th Cir + N.D./S.D. Iowa federal | ✅ claimed | ❌ |
| Constitutions | "going in now" | ❌ |
| Citation graph (statute↔case) | ✅ | ✅ |
| Treatment / good-law signals | ✅ | ✅ (v1 running; PR9 web-verified notes correct wrong-sided flags — SHIPPED to prod main; + construction notes `02d3dba`) |
| Deterministic verification gate | — (implied) | ✅ wired into answer loop + supersession/domain-fit layers |
| Brief cite-check | ✅ (Firm tier) | ✅ + PDF/DOCX upload |
| Claude MCP connector | ✅ **OAuth** | ✅ (X-API-Key; OAuth TODO) |
| Email assistant | ❌ | ✅ |
| Browse + search research app | ❌ (connector-only pitch) | ✅ |
| Public self-serve pricing | ✅ | ❌ ("talk to us") |
| Self-serve billing (Stripe) | ❌ | ❌ |
| Attorney-license verification | ❌ (disclaimer) | ❌ (disclaimer) |
| Terms / Privacy / onboarding | ❌ (none yet) | ✅ |
| Pricing | Free / $49 / $200 | Free / Solo / Firm tiers in code |
