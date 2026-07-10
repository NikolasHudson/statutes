# Accuracy Program: Search, Citator & Verification

**Status: ACTIVE PLAN** (expanded 2026-07-09 from the citator-supersession proposal).
Competition is arriving in Iowa-adjacent space; accuracy IS the product. This doc
consolidates the retrieval roadmap (RETRIEVAL_MEMO + Phase 3 findings), the citator
supersession design, and the web-search strategy into one prioritized program.

## 0. Competitive & research context (2026-07, web-verified)

- **Even the best legal AI hallucinates 15–25%** (Stanford JELS "Hallucination-Free?"
  2025: Lexis+ AI 17%, Westlaw AIAR 33%; Vals AI Oct 2025: legal tools 78–81%
  accuracy). Nobody in the market ships *deterministic* citation/quote verification
  — our gate is a real differentiator IF we surface it in the UX.
- **Cheap/free competitors have AI citators**: Midpage (free, negative/caution/
  neutral treatment, ~99% state appellate coverage), Paxton ($499/mo, "AI Citator"
  + confidence indicator). Table stakes are rising; a *reviewed* Iowa citator with
  statutory-supersession coverage beats an LLM-guessed one on trust.
- **ChatGPT + web search matched dedicated legal tools** (Vals) — recency is why.
  A corpus-first product must close the recency gap or generic chatbots undercut
  it. Thomson's CoCounsel Deep Research and LEGALFLY's "Legal Radar" both sell
  current-awareness as a first-class feature.
- Research-backed builder guidance: design for abstention, guard against
  sycophancy (correct wrong premises — our PR6/PR7 already do), transparency about
  sources/confidence, and state-law depth (frontier training data is federal-heavy
  — an Iowa-deep corpus is a moat, not a niche).

**Positioning: "Verified or flagged, never confident-and-wrong, and Iowa-deeper
than anyone."** Every item below serves that sentence.

## 1. Retrieval & ranking roadmap (get the right documents)

Status key: ✅ shipped · 🟡 built-on-dev-uncommitted · ⬜ not started

- 🟡 **Commit & ship Phase 3 items 1+3** — authority blend (w=0.25 absolute-norm
  cited_by boost; authority-set MRR 0.324→0.525 with other sets held) + latency
  fixes (version-branch skip, trigram-off: warm p50 2.2s→0.8s). Built and gated
  2026-07-09, sitting uncommitted with benchmarks. **Highest ratio item in the
  whole program: it's done — ship it.**
- ⬜ **Public/anon search parity**: `/api/browse/search` still runs
  `use_vector=False` (RETRIEVAL_MEMO #1's public half). Anyone evaluating us
  anonymously sees our worst retrieval. Decide: wire vector+rerank with a cheap
  quota, or gate the good search behind free signup (beta-access framing).
- ⬜ **Decision-cluster dedup** (eval finding #3): duplicate clusters waste result
  slots and understate hit@1; users see the same case 2–3×.
- ⬜ **Intent/recency-aware authority weighting** (Phase 3 lesson: flat w can't
  separate authority-seeking from recent-development queries; rel-gap probe showed
  no relevance band separates them). Use SearchLog + intent router signal.
- ⬜ **Eval growth** (memo #8): ~100 stratified graded queries + 20% holdout;
  Wilson-CI ship bar already in eval_caselaw. Add the adversarial + domain-fit
  sets to the standard gate battery.
- ⬜ **Doctrine-from-facts recall** (Heemstra class: facts→merger doctrine; vector
  #22, rerank buries): candidate fixes = flag-gated query rewrite
  (RAG_QUERY_REWRITE exists, off) or holdings-extraction enrichment at index time
  (dual-use with treatise structured extractions).
- ⬜ **Convex-combination fusion** (memo #7, supersedes weighted RRF) — only with
  eval evidence it beats the shipped weighted RRF.
- ⬜ **Latency tail**: residual ~5s spikes = 2GB chunk index vs droplet RAM;
  halfvec quantization is the lever. Also revisit rerank pool only with re-gate
  (authority blend needs deep recoveries).
- Decided/closed: voyage-law-2 stays (owner-tested > MLEB); no apps/search split;
  weighted RRF, ef_search=200, citation + party-name retrievers, chat pool 50 ✅.

## 2. Citator roadmap (know what's good law)

### 2a. Statutory-supersession edges (the Pexa gap) — design as previously agreed

The citator's treatment data is case-citing-case, so *Godfrey overruled by Burnett*
is caught but a **statute** superseding a case (Pexa v. Auto Owners, 686 N.W.2d 150,
superseded by Iowa Code §§ 622.4/668.14A (2020)) is invisible. Found via the
2026-07-09 adversarial eval; verification passed the answer because the case is
real, quoted accurately, and never judicially overruled.

Pipeline (batch → evidence → attorney review → existing treatment store; zero
query-time cost):

1. **Candidates:** rank cases by exposure — citation-graph in-degree (693K edges)
   × appearance in ChatTrace/SearchLog. Top 500–2,000 covers most reliance.
2. **Signal mining, in order:**
   - *2a-i corpus-internal (build first):* extend the PR3 phrase lexicon with
     statutory-supersession phrases ("superseded by statute", "abrogated by the
     legislature", "in response to our holding…") and scan opinions citing each
     target. Likely catches Pexa alone.
   - *2a-ii statute-side heuristic:* sections enacted/amended after the decision
     with embedding-similar text — weak signal, catches uncommented supersessions.
   - *2a-iii web mining (recall booster, last):* 1–2 whitelisted-domain queries
     per case (legis.iowa.gov, iowacourts.gov, law reviews, bar journals);
     extract only case+supersession sentences. **Evidence for the reviewer —
     never product content, never in generation, never cited.**
3. **LLM synthesis** (structured, per case): verdict / superseding authority /
   SCOPE ("as to medical-expense evidence" — supersessions are often partial) /
   confidence / verbatim quotes → candidate table, not live.
4. **Attorney review queue** (admin): approve/reject/edit scope. The human gate
   makes the data defensible and is the treatise workflow in miniature.
5. **Serving is free:** new treatment type `superseded-by-statute`
   (`by_citation` = Code section) in the PR3 store → search flags, GOOD LAW
   prompt rules, stale-use verify check, chat/email advisories all pick it up.
6. **Ops:** management-command batch (established pattern); incremental re-checks
   on new citing opinions (daily CL update) or subject-area statute changes.
   First pass ≈ 1,000 gpt-5-mini calls + web queries — single-digit dollars.

**Acceptance test:** pipeline produces `Pexa → superseded by § 668.14A (2020), as
to medical-expense evidence` with quotes, AND the adversarial eval's Pexa question
flips to pass via the treatment flag.

### 2b. Treatment coverage & trust
- ⬜ LLM treatment-classification pass over the OpinionsCited graph (the known
  "Shepardize gap" — phrase-derived flags cover only 872 cases today). Same
  review-queue pattern as 2a. This is the moat item vs Midpage-style AI citators:
  ours ends attorney-reviewed.
- ⬜ Retrieval-time demotion: negative-treatment cases already get no authority
  boost; consider explicit demotion + always-visible treatment chip in results
  (Phase 2 shipped chips where flags exist).

## 3. Web search: three sanctioned uses (and one ban)

**Ban (unchanged): web content never enters answer generation.** The verified-
corpus trust architecture is the product; web-in-context would make answers
unverifiable. All uses below are pipeline- or advisory-side.

- **3a. Current-awareness ingestion (new, HIGH priority):** recency is the one
  axis where generic chatbots beat corpus tools. We already have daily
  CourtListener caselaw sync. Add: Iowa Legislature monitoring (session laws /
  enrolled bills / Code supplement publication from legis.iowa.gov — scraper infra
  exists), court-order/rule-change monitoring (iowacourts.gov). Web search fills
  gaps between structured feeds (e.g., "did anything happen this week in Iowa
  law" sweep → triage queue). Surfaces as: corpus updates (authoritative) +
  a "recent developments" awareness layer (labeled, non-authoritative).
- **3b. Citator enrichment mining** — §2a-iii above (evidence for review).
- **3c. PR9 currency tripwire (flag-gated, advisory-only):** at verification time,
  for each load-bearing case in an answer, one whitelisted-domain query
  (`"<case>" "<cite>" superseded OR overruled OR abrogated`); credible hits the
  citator doesn't know → advisory line ("secondary sources suggest…—verify") +
  auto-logged citator-gap candidate feeding 2a's queue. Email surface especially
  suited (async = latency-free). Same flag posture as PR5/PR8.

## 4. Verification & UX (make accuracy VISIBLE)

- ⬜ **Turn on PR8** (`RAG_APPLICABILITY_CHECK=True` in prod) after a short
  shadow period reviewing domain_problems in traces.
- ⬜ **Verification badge in the UI/email**: we run existence+quote+currency checks
  on every answer and then show a text advisory only when something FAILS. Show
  the positive case too: "12 citations verified · 3 quotes verified · currency
  checked" chip (Paxton sells a vaguer "confidence indicator"; ours is earned).
  Same badge in email footer (already states it in prose).
- ⬜ **Abstention posture review**: RAG_ABSTAIN_BLOCKING still off; revisit
  per-class blocking (e.g., block silent reliance on negatively-treated authority)
  once supersession edges land — research consensus: declining beats guessing.
- ⬜ **Sycophancy guard is shipped** (PR6/PR7 premise checks + eval'd false-premise
  wins) — keep adversarial premise questions in the standard eval battery.

## 5. Eval program (the referee for everything above)

- Standard gate battery, run before shipping any retrieval/prompt/rank change:
  4 caselaw retrieval sets (holdings, categories, categories2, authority) +
  eval_search + chat_eval_domain_fit + chat_eval_adversarial. Wilson-CI ship bar.
- ⬜ Fold `--judge` (answer-grounded LLM judge) into the cadence — it catches
  QA-wins-rank-misses AND stale-answers-rank-passes (it found the Gacke stale-
  answer and a ground-truth label error).
- ⬜ Keep feeding externally-generated adversarial batches (the prompt from
  2026-07-09 works); corpus-verify keys before inclusion — two external-AI
  miscitations caught so far, both now regression tests.
- ⬜ Track a single headline metric for "are we getting better": answerable-yes %
  on the judge over the combined battery, plus hallucination-style incident count
  from ChatTrace review.

## 6. Priority order (impact ÷ effort, 2026-07-09 view)

1. **Ship Phase 3 retrieval work** (built, gated, uncommitted) — free win.
2. **PR8 shadow→on** in prod (one env var + trace review).
3. **Supersession 2a-i corpus phrase mining** (afternoon) → review queue (day)
   → Pexa acceptance test.
4. **Verification badge UX** (small frontend; big positioning value).
5. **Current-awareness ingestion 3a** (legis.iowa.gov monitor first).
6. **Treatment-classification pass 2b** (the Shepardize moat).
7. **Public-search parity decision** (product call as much as engineering).
8. **PR9 tripwire**, eval growth, dedup, doctrine-from-facts recall — as capacity
   allows, always through the eval gate.

## Sources (2026-07 research)

- Stanford JELS, "Hallucination-Free? Assessing the Reliability of Leading AI
  Legal Research Tools" (2025) — Lexis+ AI 17% / Westlaw AIAR 33% hallucination.
- Vals AI Legal Research Report (Oct 2025) — legal tools 78–81% accuracy; ChatGPT
  + web search 80% (recency effect).
- AI Law Librarians, "What the Science Says About Hallucinations in Legal
  Research" (Feb 2026) — synthesis + builder recommendations (abstention,
  transparency, state-law depth).
- Market scan: Midpage (free, AI citator, state appellate coverage), Paxton
  ($499/mo, AI Citator + confidence indicator), CoCounsel Deep Research (agentic,
  current awareness), LEGALFLY Legal Radar (legislative monitoring).
