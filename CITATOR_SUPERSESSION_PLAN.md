# Citator Enrichment: Statutory-Supersession Treatment Edges

**Status: PROPOSED** (2026-07-09) — designed, not scheduled. Nick to decide when/whether to build.

## The gap this closes

The citator's treatment data is built from case-citing-case signals, so it catches
*Godfrey overruled by Burnett* but is structurally blind to a **statute** superseding
a case. Found in the wild 2026-07-09 (adversarial eval, `apps/api/data/chat_eval_adversarial.json`):
the assistant faithfully and accurately explained *Pexa v. Auto Owners Ins. Co.*, 686
N.W.2d 150 (Iowa 2004) — real case, never overruled by any court — without knowing
Iowa Code §§ 622.4 / 668.14A (2020) superseded its medical-expense-evidence rule.
Existence/quote/currency verification all passed, because every layer we have checks
cases against cases.

Decision context: a per-query web-search layer was considered and rejected as the
primary fix (web content must never enter answer generation — it would break the
verified-corpus trust architecture). This offline pipeline is the compounding
alternative; a flag-only per-answer "currency tripwire" web check remains a possible
later complement (PR9-shaped, advisory-only).

## Design (agreed 2026-07-09)

Batch pipeline → evidence-backed candidates → attorney review → same treatment store
the product already reads. Zero query-time cost; every approval permanently upgrades
the citator. Also the treatise-thesis workflow in miniature (agent-drafted,
attorney-reviewed), and a sellable artifact: a reviewed statutory-supersession
citator for Iowa.

### Stage 1 — Candidate selection
Rank cases by exposure, not alphabetically: in-degree in the 693K-edge citation
graph, weighted by appearance in our own answers/results (ChatTrace + SearchLog).
Top 500–2,000 cases cover most real-world reliance. Pexa is comfortably in-set.

### Stage 2 — Signal mining (in priority order)
- **2a. Corpus-internal phrase mining (build first):** later Iowa opinions usually
  SAY it — "superseded by statute," "abrogated by the legislature," "in response to
  our holding in X, the General Assembly enacted…". Extend the existing PR3
  phrase-derived treatment classifier's lexicon with statutory-supersession phrases
  and scan the opinions citing each target case. May catch Pexa alone (a post-2020
  opinion applying § 668.14A likely states it).
- **2b. Statute-side heuristic:** sections enacted/amended AFTER the decision date
  whose text is embedding-similar to the case's subject matter — weak signal,
  ranked below phrase evidence; catches supersessions no court has discussed yet.
- **2c. Web mining (recall booster, build last):** 1–2 targeted queries per case
  (`"<case name>" "<cite>" superseded OR abrogated OR "overruled by statute"`),
  domain-whitelisted (legis.iowa.gov, iowacourts.gov, law reviews, bar journals,
  reputable annotators). Extract only sentences mentioning the case + supersession
  language. Web text is evidence FOR THE REVIEWER — never product content, never
  in generation, never cited.

### Stage 3 — LLM synthesis
One structured gpt-5-mini call per case: case + holding excerpt + mined snippets +
candidate statutes → verdict (`superseded` / `qualified` / `not_superseded` /
`unclear`), superseding authority, SCOPE ("as to medical-expense evidence" —
supersessions are often partial), confidence, verbatim evidence quotes. Lands in a
**candidate table, not the live citator**.

### Stage 4 — Attorney review queue
Admin queue: case, proposed edge, quoted evidence with links; approve / reject /
edit scope. Approved candidates become real treatment records. This human gate is
what makes the data defensible ("every treatment edge attorney-reviewed").

### Stage 5 — Serving (free)
Store approved edges as a new treatment type `superseded-by-statute` with
`by_citation` = the Code section, in the same structure the PR3 flags live in.
Downstream picks it up with no new code: search-hit treatment flags, the system
prompt's GOOD LAW rules, verify_answer's stale-use check, chat/email advisories.

### Stage 6 — Ops
Management command batch job (established worker/cron patterns). Incremental after
first pass: re-check a case when a new citing opinion arrives (daily CourtListener
update) or a statute in its subject area changes. First-pass cost, top 1,000 cases:
~1,000 gpt-5-mini calls + a few thousand web queries — single-digit dollars.
The real cost is review time; exposure-ranking keeps the queue short (~50
high-confidence candidates likely cover most risk).

## Acceptance test

Not done until:
1. The pipeline produces `Pexa → superseded by Iowa Code § 668.14A (2020), as to
   medical-expense evidence` with quoted evidence, and
2. Re-running the adversarial eval flips the Pexa question to a pass via the
   treatment flag (silent-reliance advisory or corrected answer).

## Build order & rough effort

1. **Phase 1 (~afternoon):** Stage 2a corpus-internal phrase mining — reuses the
   existing classifier, no new dependencies. Run over top-cited cases; inspect yield.
2. **Phase 2 (~day):** candidate table + LLM synthesis + admin review queue +
   treatment-store write-through.
3. **Phase 3 (after):** web miner (2c) + statute-side heuristic (2b) + incremental
   re-check triggers.
