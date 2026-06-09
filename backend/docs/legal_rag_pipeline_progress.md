# Legal-RAG Pipeline — Progress & Resume Log

Living status tracker for the shared legal-RAG answer pipeline. The full
architecture + rationale lives in [`legal_rag_pipeline_design.md`](./legal_rag_pipeline_design.md);
this file is the "where are we / what's next" log so any session can resume.

Branch: `feat/shared-rag-pipeline`

## Goal

Replace the two drift-prone retrieval/answer paths (chat re-implements rerank on
top of an `apps.api → apps.mcp_server` import) with **one shared context service**
that both chat and MCP call down into, and close the legal-grade gaps measured by
the eval/judge: stale/overruled-law surfacing, decision-cluster duplication,
opinion-head excerpts that miss the holding, and no abstain path.

## What we proved before building (session 798ba6b6, 2026-06-07)

- Eval set #3 (`caselaw_eval_queries_categories2.json`, 20 verified cases): vector
  MRR 0.675, hit@5 0.80, recovered 100%. Retrieval is the strong link.
- LLM judge (`retrieval_judge.py` + `--judge`): answerable 70% (85% incl. partial);
  controlling-case present 75%; ground-truth in top-5 80%.
- The dangerous tail is legal-grade, not random: **stale/overruled law surfaced as
  good law** (Godfrey→Burnett, Gacke→Garrison), context-quality misses (opinion-head
  excerpt), seminal-case burial. Judge caught a bad ground-truth label (#20 Gallagher).
- DB facts verified: `caselaw_link` 693,497 edges; `ReporterCitation` 118,783 all
  resolved; `CASELAW_GRAPH` 0 rows / `CrossReference.weight` NULL (treatment graph
  genuinely unbuilt).
- **Green test baseline:** `apps.corpus` + `apps.api` = 328 green; `apps.mcp_server`
  = 32/33 (the 1 red — `lookup_citation_tool("714.99")` fuzzy-suggest — is
  pre-existing uncommitted WIP in `tools.py`, NOT a regression from this work).

## Phased plan & status

- [x] **PR1 — Behavior-preserving extraction (NO quality change).** ✅ DONE (uncommitted)
  - New `apps/corpus/services/retrieval.py` — `retrieve_context()` (shared
    retrieve→rerank→assemble) + `RetrievedContext`/`RetrievedPassage`/`TreatmentFlag`
    dataclasses (forward-compat; PR2–4 populate the empty fields).
  - New `apps/corpus/services/corpus_tools.py` — the direct-lookup/verify/audit tools
    + serializers, corpus-owned (no MCP coupling).
  - `mcp_server/tools.py` → thin MCP adapter (re-exports + repointed
    `search_statutes_tool`); `chat.py._enriched_search` → thin chat adapter.
  - **`apps.api → apps.mcp_server` import deleted.**
  - Resolution of the two rerank divergences: doc-char budget preserved per surface
    (chat none / MCP 8000) via `rerank_doc_chars`; keyed on `node_version_id` for both
    (equivalent — one open version per node, so node_id is unique among hits). One
    **deliberate, documented unification**: the rerank candidate text now uses the raw
    node heading for both surfaces (chat previously reranked caselaw on the annotated
    "Court, Year" display heading). Invisible to tests (NoopReranker ignores candidate
    text) and to `eval_caselaw` (bypasses chat); strictly more correct.
  - Verified: baseline 360 green + 1 known-red → after PR1, identical (361 tests,
    same single pre-existing red `lookup_citation` fuzzy-suggest). **No metric moved.**
  - Adversarial review (3-dimension workflow) cleared it. Two real findings fixed:
    `cluster_id` now source-gated (== node_id for statutes, was wrongly the chapter id;
    latent PR2-dedup trap); chat empty-query `error` key restored. One "regression"
    was a false alarm (reviewer baselined caselaw annotation against HEAD, but it was
    pre-existing uncommitted working-tree code, copied faithfully).
  - NOTE: PR1's edits to `chat.py`/`tools.py` are entangled with the uncommitted
    prior-session foundation (chunking/eval/judge/`search.py`) in the same files, so a
    clean PR1-only commit isn't separable. Commit strategy is the user's call.
- [x] **PR2 — Decision-cluster dedup + MMR + chunk-aware offsets.** ✅ DONE (uncommitted)
  - `search.py`: `SearchHit.chunk_id`; `_vector_search_chunks` returns
    `(vid, score, chunk_id)`; new `_merge_version_chunk_hits`; `vector_search`
    gained a `with_chunks` opt-in that **keeps the default 2-tuple return
    byte-identical** (eval/benchmark/tests unpack 2-tuples); `hybrid_search`
    attaches the dense retriever's winning chunk to each hit.
  - `retrieval.py`: `retrieve_context` rewritten as a pipeline — hybrid
    retrieve (pool **50→100**) → rerank **with exact-citation-lane bypass** →
    **decision-cluster dedup** → MMR select → **chunk-aware assembly** (caselaw
    excerpt/snippet from the matched `NodeChunk` span + neighbor window; statutes
    keep the prefix) → **U-curve order**. Each stage past rerank is individually
    togglable; every stage provably preserves the rank-1 hit at `passages[0]`.
    Excerpt budget is assigned by **relevance rank before** U-order reorders.
    Rerank candidate-text cap **unified to 8000** for both surfaces (so a
    100-opinion caselaw pool stays affordable; only the rerank *input* is capped,
    not what the model reads).
  - Adapters: MCP `search_statutes_tool` + chat `_enriched_search` serialize
    additive `char_start`/`char_end`/`chunk_id`; existing keys unchanged.
  - `eval_caselaw`: new `--use-retrieve-context` **`rc` config** (routes the
    judged top-K through the real pipeline — the only config that exercises PR2),
    `--rc-*` A/B toggles, **distinct-cluster-in-top-k metric**, and a
    chunk-excerpt-aware judge payload.
  - **Tests:** new `apps/corpus/tests/test_retrieval.py` (20 tests: MMR
    position-0 invariant + diversity, U-curve, chunk-excerpt budget/robustness,
    chunk_id threading, dedup collapse, offsets, holding-centered excerpt,
    citation bypass). Full suite **380 / 1-known-red** (was 361/1) — +19/+20
    green, **zero regressions** (the 1 red is the pre-existing `lookup_citation`
    714.99 fuzzy-suggest).
  - **Eval A/B (real corpus, gpt-4o judge, category2 n=20, 2026-06-08):** the new
    PR2 config (dedup+chunk+U-order+cite-bypass, **MMR off**) beats the current
    production path (`hybrid_rr`) on 7/8 metrics — MRR 0.79 vs 0.75, hit@1 0.75
    vs 0.70, hit@10 0.90 vs 0.85, controlling 0.80 vs 0.75, target-shown 0.85 vs
    0.80 (within n=20 Wilson noise, but directionally consistent). Isolations:
    **chunk-excerpt** lifts yes-or-partial answerable 0.90→1.00; **dedup** raises
    distinct-clusters@5 4.65→5.0 with no answer cost; **MMR REGRESSED**
    (hit@10 0.90→0.75, target-shown 0.85→0.75 — diversity demotes the on-point
    case for pinpoint legal queries) → **MMR reverted to default-off**, code +
    `mmr_lambda` param retained for diversity-oriented surfaces. Artifacts:
    `benchmarks/caselaw/pr2/*.json`.
  - **Adversarial review** (4-dimension workflow + per-finding skeptic): no
    confirmed defect touched the critical invariants (byte-identical default
    return, rank-1 position-0, additive serializers all held). Two real fixes
    applied (`_chunk_excerpt` now provably ≤ budget incl. ellipses;
    `vector_search` return annotation); one finding declined with reasoning
    (bare try/except around the chunk fetch would be inconsistent with the
    surrounding un-wrapped essential queries); the rerank-cap change confirmed
    intentional + eval-clean.
  - **Open (carry to PR3+):** U-order ships on but the eval can't measure it
    (set-preserving — same cases shown, only reordered); revisit if a UI surfaces
    passages in list order. Pool-100 + 8000-char-cap rerank latency: p50 rc ~3.8s
    (vs hybrid ~3.1s) — acceptable, watch under load.
  - **Enterprise-readiness (candid): too soon to claim; on current evidence, not
    yet.** Two independent reasons, neither fixable by more tuning of PR2:
    1. *The A/B is underpowered.* n=20, Wilson CIs ≈ ±0.18 on hit@1 — the "7/8
       metrics better than `hybrid_rr`" is every metric moving ~one query, i.e.
       **inside the noise floor**. It's a smoke signal, not a ship gate. A real
       gate needs n in the hundreds across every query shape (citation,
       party-name, procedural, multi-part, adversarial), a held-out set, and
       human-rated relevance wired into CI with regression thresholds — plus
       latency-under-load / multi-tenant / red-team coverage that this eval has
       none of. Scope is also one jurisdiction (Iowa) on a favorable
       landmark-case slice.
    2. *The enterprise-critical safety properties are deliberately deferred.* The
       headline legal risk from the design (overruled law cited as good law) is
       **untouched** by PR2: `stale_warning` is structurally 0 because
       treatment/good-law currency is PR3 and abstention is PR4. Until those land
       the system will still confidently cite a bad case and stretch an adjacent
       rule rather than abstain. Absolute retrieval (hit@1 ~0.75, answerable
       ~0.75) is solid for a **lawyer-in-the-loop research assistant**, below the
       bar for any authoritative/autonomous use.
    What *is* already enterprise-grade is the **discipline**, not the numbers: one
    shared pipeline (no chat/MCP drift to test/monitor twice), green-for-green
    tests, and an eval harness that gated a real decision (MMR reverted on
    evidence). That machinery is the prerequisite for *earning* the claim once
    PR3/PR4 close the safety gaps and the eval set is scaled up.
- [x] **PR2.5 — Ingest the CourtListener citation-map (graph + depth).** ✅ DONE
  (2026-06-08; new — PR3 foundation, split out after researching CL's offerings.)
  - **Ingested:** streamed `citation-map-2026-03-31.csv.bz2` (522 MB, 76,959,991
    national rows) → **475,375 in-corpus Iowa edges** written as
    `CrossReference(source=CASELAW_GRAPH, weight=depth)`. `weight` now 100%
    populated (depth min 1 / max 70 / avg 1.79) — it was 100% NULL before.
    `caselaw_link` (#1) unchanged at 693,497 (source-scoping verified). Skips:
    76.3M citing-not-in-corpus, 205,901 cited-not-in-corpus, 1,836 sibling, 0
    self / 0 bad-depth. ~7 min, streamed (never decompressed to disk).
  - **Semantic spot-check passed:** the most-cited in-corpus cases are the
    expected Iowa landmarks (*In re P.L.* 1,502; *Meier v. Senecaut* 1,234; the
    foundational TPR/juvenile cluster); heaviest edge depth 70 (*State v. Short* →
    *State v. Ochoa*) = the deep-engagement the treatment pass should prioritize.
  - **Command:** `apps/ingestion_caselaw/management/commands/build_caselaw_citation_graph.py`
    (mirrors #1; idempotent delete-all-CASELAW_GRAPH-for-source + rebuild; internal
    edges only; self/sibling skip). 5 golden tests. Adversarially reviewed (one
    real fix: non-positive depth coerced to 1 so a corrupt row can't crash the
    PositiveIntegerField insert).
  - *Why this exists:* PR3's treatment classifier needs the **incoming-citation
    graph with depth** as its substrate (which later opinions cite a target, and
    how heavily — to prioritise the LLM budget and to be sure the negative-
    treatment scan sees every citing case). We have a citation graph today
    (`caselaw_link`, 693K edges) but it was built from inline `<a>` links in
    `html_with_citations`, so it carries **no depth** (`CrossReference.weight` is
    100% NULL) and `CASELAW_GRAPH` is empty. The `Case Law/CASELAW_INGESTION_PLAN.md`
    plan (L110) intended to use CL's `citation-map` for this but the build took
    the inline-link route instead.
  - *Key research finding (changes a design assumption):* CourtListener does **not
    publish citation *treatment*** for state courts — their AI citator (free.law,
    May 2025) is a SCOTUS-only, overruling-only proof-of-concept, not in the API/
    bulk data, no timeline. So "ingest treatment from CL" is **not** an option for
    Iowa; we ingest the **graph + depth** and build the treatment classifier
    ourselves (design §5). CL's citator *does* validate that approach (EyeCite +
    ±6 sentences + LLM; Claude 3.5 Sonnet >90% recall, F1 >80% on overruling) and
    gives a benchmark. Leave a `TreatmentFlag.source="courtlistener"` hook for when
    their citator generalises.
  - *Scope:* download `bulk-data/citation-map-<date>.csv.bz2` (~500 MB compressed,
    `search_opinionscited`: `id, depth, citing_opinion_id, cited_opinion_id`),
    stream-filter via `csv_stream.open_bulk_csv` to in-corpus Iowa edges (join on
    `cl_opinion_id`, which every node carries), and write
    `CrossReference(source=CASELAW_GRAPH, weight=depth)`. New command
    `build_caselaw_citation_graph` mirroring `backfill_caselaw_cross_references`
    (#1); idempotent (delete CASELAW_GRAPH edges, rebuild). Never decompress to
    disk. Resolves §8 Q3.
- [x] **PR3 — Treatment graph + deterministic v1 good-law flag.** ✅ DONE
  (2026-06-08, uncommitted). The headline legal-grade gap from the design — an
  overruled case surfaced as good law — now has a deterministic v1 flag.
  - **`treatment.py`** — phrase-scan classifier. For a target decision, scan the
    citing opinions' sentences (incoming CASELAW_GRAPH edges) for negative stems
    (overruled / abrogated / superseded / repudiated / disapproved /
    no-longer-good-law / declined-to-follow) IN THE SAME SENTENCE as the target's
    reporter cite, within ~70 chars. Calibrated on real Iowa opinions; the
    dominant false positives are all guarded: "overruled **the/our/counsel's
    objection**" (trial ruling), "overruled **by** [target]" (target is the
    *overruler*), "[target] (**overruling** X)" (gerund-after = agent), negation
    ("decline / did not / not at liberty / asked to overrule"), "on (the) other
    grounds" → downgraded to caution, "supersedeas", and distinguish/limit are
    dropped (too noisy). Severity 0–5; status good/caution/negative/unknown.
  - **`annotate_treatment`** — inverted scan: only opinions whose body matches the
    stem prefilter (22,244 of them), classified against the targets they cite,
    aggregated max-severity, written to the cited decision's
    `source_metadata["treatment"]`. Idempotent (clear-then-write); the prefilter is
    a proven superset of the classifier stems so a re-run can't drop a real flag.
    **Run: 470 decisions flagged** — 323 negative (overruled/abrogated/superseded),
    147 caution. Spot-checks correct (Godfrey→Burnett flagged negative; clean cases
    unflagged). ~17 min, streamed.
  - **Wired** into `retrieve_context` (`_treatment_for` reads the cached flag →
    `RetrievedPassage.treatment`), serialized to MCP + chat (`treatment_payload`,
    additive), and a chat system-prompt good-law rule ("never rely on a `negative`
    case; name what treated it; note `caution`").
  - **Tests:** `test_treatment.py` (31 — every guard + the prefilter-superset
    invariant) + treatment-flow tests in `test_retrieval.py`. Adversarially
    reviewed; two real fixes applied (possessive ruling-noun guard; prefilter
    superset to prevent stale-flag loss on re-run).
  - **Known v1 limits (advisory by design):** phrase-only ⇒ moderate recall (misses
    subtle/implicit treatment) and max-aggregation can let one mis-attributed
    sentence flag a good case — mitigated by shipping the verbatim evidence
    sentence with every flag and keeping it advisory (no ranking change yet).
    Enforcement (down-rank/abstain) is PR4; the LLM classifier + a multi-opinion
    support count are PR5. §8 Q4 (cite-sentence sourcing = re-scan body_text) and
    Q5 (cache on `source_metadata`, no table) resolved.
- [x] **PR4 — Verify+abstain extraction and stale-use gate.** ✅ DONE
  (2026-06-09, uncommitted). The treatment flags PR3 produced are now *enforced*
  at answer time, behind a feature flag, with advisory as the default.
  - **New `apps/corpus/services/answer.py`** — the answer gate, moved out of
    `chat.py` so chat + MCP share one checked path. `verify_answer` (the old
    `_verify_answer` body, verbatim) + `render_advisory` (old advisory) + the new
    `should_abstain` / `abstain_decision`. `_verify_answer`/`_verification_advisory`
    deleted from `chat.py`; `verify_document.py` doc-comments repointed.
  - **Stale-use detection** — `verify_answer(content, *, source_slug, context=None)`
    cross-references the cases the *drafted answer* cites against the PR3
    `treatment` flags on the turn's retrieved passages. It distinguishes
    **silent reliance** on a `negative` case (the dangerous "overruled-as-good-law"
    failure) from an **acknowledged** mention ("X was overruled by Y" — which the
    system prompt *tells* the model to write, so it must not be punished): a case
    is "acknowledged" only when a treatment cue or the treating case's name sits in
    the **same sentence** as the mention. `context=None` ⇒ stale check is a no-op
    and the report is byte-identical to the pre-PR4 gate (behavior-preserving).
  - **Abstain** — `should_abstain` fires only when nothing was retrieved or
    **every** passage is `negative`; `unknown` (all statutes + unflagged cases) is
    presumed good, so statutes never spuriously abstain. Surfaced as an additive
    `abstain`/`abstain_reason` on both the chat search tool and the MCP
    `search_statutes_tool`, plus a system-prompt ABSTAIN rule.
  - **Block policy (behind the flag, default OFF)** — `abstain_decision` withholds
    the answer only when `settings.RAG_ABSTAIN_BLOCKING` is True and either the
    answer silently relied on an invalidated case (`severity >=
    RAG_STALE_BLOCK_SEVERITY`, default 5) or no good-law authority was retrieved
    (guarded by a `searched` flag so a lookup-only / pinned-doc answer is never
    blocked for an empty search set). Default ships **advisory-only** — nothing is
    suppressed, the gate just appends a warning. Non-stream path replaces outright;
    the streaming path can't un-send already-streamed text, so it appends a loud
    trailing notice (documented divergence — true stream suppression needs answer
    buffering, deferred). The chat loop now captures each `search_statutes`
    `RetrievedContext` (both sync + stream loops), merges them (dedup by
    `cluster_id`), and threads the result into the finalizers.
  - **Tests:** new `apps/corpus/tests/test_answer.py` (38 — stale-use silent vs
    acknowledged, anchor extraction, abstain, block policy + threshold + searched
    guard, advisory render, behavior-preservation, chat-finalizer advisory-vs-block)
    + 2 MCP abstain tests. Full suite **453 / 1-known-red** (the pre-existing
    `lookup_citation` 714.99 fuzzy-suggest) — zero regressions.
  - **Adversarial review** (4-dimension workflow + per-finding skeptic) caught a
    **critical** real bug pre-merge: the stale-use anchor was mined from
    `p.heading`, but for caselaw `_annotate_caselaw` puts the court+year there and
    the **case name in `p.citation`** — so the name anchor never fired and an
    overruled case cited by name (the common COA name-only shape) passed the gate
    clean. Verified against the live dev DB (0/4000 heading-names vs 91%
    citation-names). Fixed (mine the caption from `citation`, both fields), plus
    two confirmed lower findings: the acknowledgment scan was a ±220-char window (a
    cue about a *different* case excused silent reliance — fail-open) → tightened to
    same-sentence with a `v.`-aware boundary; and the cue regex matched benign
    vocab ("reject"/"abandon") → scoped to the treatment stems. My own test fixture
    had **masked** the critical bug by inverting the real heading/citation shape;
    fixtures corrected + a name-only-citation regression test added.
  - **Live end-to-end validation** (real dev corpus + OpenAI `gpt-4o-mini`, known
    overruled case *Metropolitan Jacobson*, 476 N.W.2d 726, flagged `negative/sev5`
    by *Estate of DeTar*): the PR3 flag flows retrieval → search tool → model, which
    answered "no longer good law… overruled by Estate of DeTar" (the whole PR3→PR4
    chain working live). Deterministically a silent-reliance answer → advisory +
    (blocking on) withheld; an acknowledged answer → clean. The live run surfaced
    **one more boundary bug**: the same-sentence acknowledgment splitter only skipped
    *single-letter* abbreviations, so a citation-internal "(Iowa **App.** 1991)"
    between the case name and the cue falsely marked a correct answer `silent`. Fixed
    (abbreviation-aware boundary: "App."/"Co."/"Inc."/"No."/… no longer end a
    sentence) + regression test; the live answer then read `ok=True / acknowledged`.
  - **Known v1 limits (advisory by design):** name matching is exact-caption /
    reporter-cite, so a *shortened* prose cite ("State v. Worden" for "State of
    Iowa v. Tre Evans Worden") is a residual false-negative; phrase-only treatment
    recall (PR3) bounds it further. Streaming block degrades to a loud notice (see
    above). §8 Q2 resolved (advisory default + block behind `RAG_ABSTAIN_BLOCKING`,
    threshold 5).
  - **Remaining (measurement, carried to its own step like PR3's):** extend
    `eval_caselaw`'s judge with an adversarial set (no-authority questions →
    abstain-rate; overruled-precedent questions → stale-block-rate, tracking
    accurate/incomplete/hallucinated separately). Needs the paid OpenAI judge + a
    new query set; not built yet.
- [x] **PR5 — LLM-assisted treatment v2 + claim-level NLI + query rewrite.** ✅ DONE
  (2026-06-09, uncommitted). Three LLM-assisted layers, each **flag-gated and OFF by
  default** (deterministic v1 paths always run; every layer no-ops without a key),
  each reusing the `semantic_support` OpenAI-call shape (injectable Protocol +
  graceful degradation).
  - **Treatment v2** — `treatment_llm.py` (`OpenAITreatmentClassifier`,
    `parse_verdict`, `LLMTreatmentVerdict`, `paragraph_around`) + `annotate_treatment
    --llm`. v1 stays the high-recall candidate generator; v2 reads the citing
    **paragraph** + target identity + citing court level and confirms / relabels /
    rejects each candidate. **Confidence policy** (in the command): confident negative
    → refine (`source="llm"`), confident rejection → drop a v1 false positive,
    uncertain (conf < `--llm-min-confidence`, default 0.55) → **keep the v1 flag**
    (never silently lose a real flag). Depth-gated (`--llm-min-depth`) + capped
    (`--llm-limit`) so cost tracks deep engagements. Severity derived in code from a
    fixed label vocabulary (never trust the model's number).
  - **Claim-level NLI** — `answer.py` (`_misgrounded_claims`, `_split_sentences`;
    `verify_answer` gained a `claim_checker` param + a `misgrounded` report key).
    Behind `RAG_CLAIM_NLI`. Pairs the answer's caselaw claims (anchor match, reused
    from stale-use) with the retrieved opinion text and flags `contradicted` holdings
    via `semantic_support`. Advisory only (never blocks); `context=None` stays
    byte-identical to the PR4 report.
  - **Query rewrite** — `query_rewrite.py` (`rewrite_query`, `OpenAIQueryRewriter`)
    + a `retrieve_context` hook behind `RAG_QUERY_REWRITE`. Guaranteed **passthrough**
    on any failure (empty/over-long/error/no-key) so retrieval never sees a worse
    query; `ctx.query` keeps the ORIGINAL for display, only the rewrite reaches
    `hybrid_search`/rerank, recorded in `diagnostics["query_rewritten"]`.
  - **Tests:** `test_treatment_llm.py` (21 — parse/gate/policy/command refinement with
    a fake classifier + minimal caselaw fixture), `test_query_rewrite.py` (16 —
    passthrough contract + the gated hook), claim-NLI tests added to `test_answer.py`
    (49 total). Full suite **499 / 1-known-red** — zero regressions.
  - **Adversarial review** (4-dimension workflow + per-finding skeptic): 1 confirmed
    (low) fix — `parse_verdict` read `target_is_subject` with a bare `bool()`, so a
    quoted-string `"false"` would coerce True and flip a confident rejection into a
    kept flag (the unsafe false-negative-treatment direction); normalized like the
    sibling fields + regression test. 1 finding **dismissed with real-corpus
    evidence** (the reviewer measured a 0.00% `paragraph_around` fallback rate over
    377 live v1 candidates).
  - **Live validation** (real corpus + OpenAI): v2 **REJECTED node 33228**
    (*Metropolitan Jacobson*) — the exact v1 false positive the PR4 live test exposed
    (prefix anchor "476 N.W.2d" had matched *Weidman*'s 476 N.W.2d 357) — and
    relabeled a *contention* "overruled"→"questioned"; uncertain reads kept v1.
    Claim-NLI flagged a fabricated "all warrantless blood draws are permitted" holding
    as misgrounded while passing a faithful claim. Query rewrite turned verbose lay
    questions into term-of-art queries.
  - **Note:** v2's recall is the expected tradeoff — a confident reject can drop a
    genuine-but-ambiguous flag (observed once in the sample); the uncertain→keep-v1
    rule bounds the downside, and the whole layer is advisory. Re-running
    `annotate_treatment --llm` over the full corpus to actually refine the 470 stored
    flags is an operational step (cost: one gpt-4o call per candidate), not yet run.
- [x] **PR6 — User-premise check (anti-anchoring).** ✅ DONE (2026-06-09, uncommitted).
  Born from a live end-to-end run: a user's question *asserted* what *Madden v. City
  of Iowa City* holds; the model anchored on the confident premise, and the
  post-answer claim-NLI (which grades the *answer*) missed it. PR6 intercepts the
  premise BEFORE the model drafts.
  - **`premise.py`** — deterministic `extract_premises` (a sentence that names a case
    via caption/reporter-cite AND attributes a holding — an assertion verb after the
    name OR a holding-preposition "Under/Per [Case]" before it; hedge/treatment-cue
    guarded) → `check_premises` retrieves the named case (top-K + **anchor-overlap
    guard** so we never verify against the wrong case), runs `semantic_support` NLI of
    the user's premise vs the opinion, and flags `contradicted`/`partial` (the
    deliberate asymmetry vs PR5 — an overstated user premise is the anchor to
    neutralize). The NLI verdict is the precision backstop (`supported`/`no_claim`
    → silent), so extraction favors recall.
  - **Wired** behind `RAG_PREMISE_CHECK` (default off, no-op without a key): a
    pre-answer system **caution** is injected into both chat loops so the model
    corrects rather than parrots; the findings ride into the post-answer report +
    advisory (`premise_problems`). Design chosen via a 3-way design-panel workflow.
  - **Tests:** `test_premise.py` (22 — extraction precision incl. see-cite/hedge/
    treatment/Under-framing negatives, the anchor-overlap + topical-competitor pick,
    verdict gating, degradation, the chat-guard gating). Full suite green-for-green.
  - **Live validation drove three real fixes** + one important correction:
    (1) the premise query needed the *topic* (not just the caption) so the chunk-aware
    excerpt surfaces the relevant holding; (2) retrieval needed top-K + anchor-match
    (the named case can rank below a topical competitor); (3) the caption regex
    greedily ate the leading "Under". After fixes: the user's ACTUAL *Madden* premise
    verified **supported → silent** (no false alarm), and an inverted false premise
    ("a city can never shift liability") was flagged `contradicted` and the live model
    **corrected** it ("Contrary to what you suggested, the court did not hold…").
  - **Correction of record:** the live run proved the *Madden* premise is actually
    CORRECT — the majority held the Iowa City liability-shifting ordinance "is not
    preempted by Iowa Code § 364.12(2)" and affirmed; the "express legislative
    authorization required / unlawful tax" language was the **dissent** and the losing
    party's arguments. An earlier hand-analysis in chat had it backwards (anchored on
    a dissent snippet — the same failure mode). The PR6 false-positive control
    correctly stayed silent on the true premise.
  - **⚠️ THIS "Correction of record" WAS ITSELF WRONG — superseded by PR7
    (2026-06-09).** Multi-source verification (official Iowa Judicial Branch
    opinions, Justia, Nyemaster's *On Brief*, the ICAP article) establishes that
    *Madden v. City of Iowa City*, 848 N.W.2d 40 (Iowa, filed **June 13, 2014**),
    was **EXPRESSLY OVERRULED** by *Splittgerber v. Bankers Trust Co.* /
    *Bankers Trust Co. v. City of Des Moines*, No. 22-2085 (Iowa, filed **June 14,
    2024**) — "we overrule Madden to the extent it permitted … liability beyond
    what the legislature has expressly authorized in Iowa Code § 364.12(2)." The
    PR6 note got Madden's 2014 *internal* structure right (majority = not-preempted
    + affirmed; the express-authorization reasoning = the Mansfield/Waterman
    dissent) but its bottom line — *"Madden is good law"* — was **stale/false** as
    of 2024. So PR6's "live-validation success" (premise verified *supported →
    silent*) was a **FALSE NEGATIVE**: the model confirmed a *faithful reading of a
    dead case*. Fidelity-NLI is structurally blind to currency. This is exactly the
    failure PR7 fixes. (Reporter pin cite for Bankers Trust: confirm the N.W.3d
    page on Westlaw/Lexis — free sources 403'd; docket/date/holding are solid.)
  - **Known v1 limits:** extraction is deterministic (misses paraphrases beyond
    verb/"Under" framings); one retrieval + one NLI call per premise on the hot path
    when enabled (capped at `MAX_PREMISES`); pre-answer latency before first token.
- [x] **PR7 — Currency axis: faithful-reading-of-an-overruled-case.** ✅ DONE
  (2026-06-09, uncommitted). Born from the *Bankers Trust* slip-and-fall re-test:
  PR6 stayed silent on "Under *Madden*, abutting owners are liable" because the
  premise is a **faithful** reading of *Madden*'s 2014 majority — but *Madden* was
  **overruled** by *Bankers Trust* (2024). The root cause is **orthogonality**:
  every grounding check we had (PR5 claim-NLI, PR6 premise, the verify gate) answers
  *"is this faithful to the source?"* — none enforces *"is the source still good
  law?"*. A faithful reading of a dead case is maximally faithful and maximally
  wrong. (This is also why PR6's own "Madden is good law" live-validation was a
  false negative — see the corrected record above.)
  - **Layer 1 — recall (`treatment.py`).** PR3 never flagged *Madden* even though
    *Bankers Trust* cites it 13× at depth and the dissent says "in overruling
    *Madden v. City of Iowa City*, 848 N.W.2d 40". The classifier's sentence
    splitter was **newline-naive**: PDF text extraction injects `\n\n` (and hyphen
    wraps, "rea-\n\nsons") MID-sentence, tearing the overrule stem from the reporter
    cite, so the same-sentence scan saw nothing. Fix: `_normalize_body` (repair
    soft-hyphen wraps + collapse all whitespace) then **abbreviation-aware**
    sentence splitting (don't break on the "v."/"Co."/"N.W." periods) — mirrors
    `answer.py`'s boundary logic. Precision preserved: cite-anchoring still isolates
    targets (the same opinion's overrulings of *Godfrey*/*Smith* carry their own
    cites, so they flag *those*, not *Madden*). Proven live: `classify_citing_text`
    now returns `(5, overruled, …)` for *Bankers → Madden*. +2 regression tests
    (the PDF-wrap + the abbreviation-split cases). Re-ran `annotate_treatment`.
  - **Layer 2 — wiring + policy (`premise.py`/`answer.py`/`chat.py`/`settings.py`).**
    `check_premises` now reads the `TreatmentFlag` **already on the retrieved
    passage** (it was fetched and discarded — one attribute away) and emits a
    finding on EITHER axis: fidelity (NLI, as before) OR currency (negative/caution).
    `PremiseFinding` gained `currency`/`treating_case`/`treatment_label`/
    `treatment_evidence` (additive); `render_premise_caution` gained a
    **correct-then-answer** branch that makes the model LEAD with the overruling
    then answer under current law; `answer.render_advisory` renders the currency
    note. Currency is **deterministic (no LLM)**, so it ships behind a new
    `RAG_CURRENCY_CHECK` defaulting **ON** (the fidelity NLI stays opt-in behind
    `RAG_PREMISE_CHECK`); `_premise_guard` runs currency with `checker=None`.
  - **Adversarial review (4-dimension workflow + per-finding skeptics) caught a
    CRITICAL regression** in the Layer-1 recall fix before it could ship: the
    abbreviation-aware splitter MERGED two real sentences when sentence 1 ended in a
    legal abbreviation ("...we overrule Acme **Co.** The plaintiff cites [target]"),
    mis-attributing the overrule to [target] — a false "this case is dead" flag, the
    exact harm the module guards. Two sibling false-positive classes: `iowa` in the
    abbrev set ("...of Iowa. We reaffirm [target]"), and whitespace-collapse melting
    newline cite-stacks so a far stem fell within `_PROX`. All FIXED and the
    annotation re-run (the first run used the buggy splitter, killed pre-`_write` so
    no bad data persisted): (a) **capitalization-aware boundaries + two abbrev
    classes** — `v.`/titles never break; entity/citation suffixes break only before a
    Capitalized new sentence; `iowa` dropped; (b) a **no-intervening-cite guard** (a
    reporter cite between stem and target → reject); (c) `_WRAP_HYPHEN` tightened to
    lowercase soft-wraps so page-ranges/date-spans aren't corrupted. Verified live:
    all 7 review reproductions return `None`, recall preserved, Bankers→Madden still
    `(5,'overruled')`. Lower-severity fixes: `RAG_CURRENCY_CHECK=False` now actually
    disables the currency axis (threaded a `currency` param into `check_premises`);
    `render_advisory` no longer mislabels a currency-only finding as a misreading.
  - **Tests:** +12 premise (the Bankers Trust trap: faithful reading of an overruled
    case is flagged; currency-without-a-key; both-axes; dual-flag gating; the
    `RAG_CURRENCY_CHECK=False` suppression contract; `finding_dicts` keys), +8
    treatment (the recall fix + the precision regression classes: entity-suffix
    merge, sentence-final "Iowa.", intervening-cite, soft-hyphen span), +4 answer
    (the `render_advisory` currency branch). Full `apps.corpus`+`apps.api`+
    `apps.mcp_server` suite **539 / 1 known-red** (the pre-existing `lookup_citation`
    714.16 fuzzy-suggest) — zero regressions.
  - **Perf fix (the recall normalization had an O(n²) bug).** First re-annotation
    ran **1.5 hr** and was killed: `_is_boundary` sliced the FULL prefix
    (`text[:dot_idx]`) and searched it per sentence-boundary → O(n²) over a long
    body; compounded by `classify_citing_text` re-normalizing the whole body per
    anchor×target (landmark opinions cite hundreds of cases). Fixed: bounded 24-char
    lookback in `_is_boundary` (O(n)); split into `normalized_sentences()` (once per
    body) + `classify_in_sentences()` (per target); command normalizes each citing
    body once. Measured: 34KB body normalize **12ms** (was hundreds), per-target
    scan **0.4ms**. Re-annotation now **~7 min**.
  - **Corpus state (shipped):** re-annotation flagged **893 decisions** (540
    negative / 353 caution). **Madden (node 72214) flags `negative/overruled`** —
    evidence found via *Clemen v. Dolgencorp*'s parenthetical "(overruling Madden v.
    City of Iowa City, 848 N.W.2d 40 (Iowa 2014))", which also surfaced the
    *Bankers Trust* reporter cite the web research couldn't pin: **8 N.W.3d 135, 141
    (2024)**. **End-to-end verified:** the live slip-and-fall prompt → `extract_premises`
    catches the Madden premise → `check_premises` reads the negative flag (no key
    needed) → the pre-answer caution makes the model LEAD with the overruling, then
    answer under current law. The trap is defeated.
  - **⚠️ KNOWN LIMITATION — v1 deterministic precision (~1/3 false positives).** A
    14-sample of `negative` flags showed ~5 clear FPs the v1 phrase-scan can't catch:
    a trial ruling whose ruling-noun precedes the stem ("a motion … was overruled");
    a party *contention* ("should be overruled"); the court *declining* ("without
    substantially overruling Robb"); a possessive trial ruling ("overruled Butcher's
    [objection]"); and agent confusion ("overruled in [target]" = target is the
    venue). The recall-widening normalization raised recall AND this FP load. v1 was
    always **advisory** by design (PR3); but PR7's **correct-then-answer is confident
    enforcement**, so on a falsely-flagged good-law case it can confidently mis-correct.
    Decision (2026-06-09): **ship the core on v1 flags; defer corpus-wide precision.**
  - **`--llm` refinement — tested, NOT run (unsafe with drops).** Smoke + a 40-deepest
    dry-run (gpt-4o) showed the PR5 `--llm` pass DROPS on confident rejection
    (**19/40 ≈ 47%** of the deepest sample dropped) and **risks removing real
    overrules** — *Madden* itself was rejected by gpt-4o and survived ONLY because the
    rejection was conf 0.0 < the 0.55 keep-v1 threshold. Dropping a real overrule
    re-creates the original "dead case shown as good law" bug, so a drop-enabled run
    is unsafe to apply unsupervised. (Also: low-depth FPs like the *Taylor* "relies
    on" case sit outside any practical `--llm-limit`.)
  - **Recommended refine path (deferred follow-up).** To make the broader corpus
    safe for confident correct-then-answer: (1) run `--llm` in a **CONFIRM-ONLY**
    mode (upgrade genuine flags to `source=llm`/high-confidence + relabel, but NEVER
    drop) so no real overrule is lost; (2) **confidence-gate the enforcement** —
    confident "overruled, lead with the correction" only for `source=llm`/high-conf
    flags, a softer "a later opinion used overruling language near this case's cite —
    verify its current status before relying" for raw deterministic flags; (3) tighten
    the deterministic guards for the FP patterns above (ruling-noun BEFORE the stem,
    "should/could be" contentions, "without …ing" declining, "overruled in [target]"
    agent); (4) fix **attribution** (the `by_citation` is the *reporting* case, not the
    overruler — *Madden*'s flag says "by Clemen" not "by Bankers Trust"); (5) wire the
    adversarial **eval** (overruled-premise correction-rate, no-authority abstain-rate,
    v1-vs-confirm-only treatment precision).
  - **Other carried residuals:** (a) a name-only overruling with NO cite-adjacent
    mention anywhere is still missed (→ name-anchoring + LLM, eval-gated); (b)
    **statute supersession** is uncovered (treatment is caselaw-only) — a premise on a
    repealed/amended § gets no currency flag; (c) the **duplicate-cluster** split (two
    *Madden* decision nodes) means the flag must land where retrieval surfaces it;
    (d) `answer.py`'s `_is_sentence_boundary` has the same latent `text[:dot_idx]`
    O(n²) pattern, harmless today (small inputs) but worth the same bounded-window fix.

## Open questions (from design §8) — answer before the PR that needs them

1. (PR2) ✅ RESOLVED — caselaw-only chunk excerpts; statutes keep the prefix.
2. (PR4) ✅ RESOLVED — advisory by default; hard-block only behind
   `RAG_ABSTAIN_BLOCKING` (default off), threshold `RAG_STALE_BLOCK_SEVERITY`=5.
3. (PR3) Re-pull CL OpinionsCited citations CSV for the loaded Iowa clusters (bulk
   archived to DO Spaces).
4. (PR3) Citing-sentence sourcing: re-scan `body_text` vs re-ingest `html_with_citations`.
5. (PR3) `source_metadata["treatment"]` cache vs dedicated `Treatment` table.
6. (PR1) Add as-of date to retrieval signature now, or defer? Recommend **defer**
   (PR1 stays behavior-preserving).
7. (PR2) ✅ RESOLVED — pool widened 50→100; citation lane bypasses the reranker.
8. Keep the OpenAI tool-loop in `chat.py` (not extracted to `answer.py`)? Recommend yes.

## Resume notes

- 2026-06-07: design doc written; branch cut; baseline green confirmed.
- 2026-06-07: **PR1 coded, verified, and adversarially reviewed** (uncommitted in the
  working tree). Tests green-for-green vs baseline; `api→mcp_server` import removed.
  `cluster_id` already correctly populated for dedup.
- 2026-06-08: **PR2 coded, eval-gated, and adversarially reviewed** (uncommitted).
  §8 Q1/Q7 resolved (caselaw-only excerpts; cite-lane bypass + pool 100). Full suite
  380/1-known-red. Real-corpus A/B drove the one design change from the plan: **MMR is
  default-OFF** (it regressed pinpoint retrieval); dedup + chunk-excerpt + U-order +
  cite-bypass are on and net-positive vs the production `hybrid_rr` path. Eval artifacts
  in `benchmarks/caselaw/pr2/`. PR1 committed as `5ca5243`; PR2 committed as `acc5337`.
- 2026-06-08: **PR2.5 done** — CL `citation-map` ingested (475,375 in-corpus Iowa edges,
  `CrossReference.weight=depth` now populated; `caselaw_link` untouched). Research
  finding: CL publishes the citation **graph+depth** but **not treatment** for state
  courts (their citator is SCOTUS-only PoC), so we build the Iowa treatment classifier
  ourselves. §8 Q3 resolved. Command + 5 tests adversarially reviewed (uncommitted).
- 2026-06-08: **PR3 done** — deterministic v1 good-law flag. `treatment.py` classifier
  (calibrated on real Iowa opinions, 31 tests, adversarially reviewed) + `annotate_treatment`
  (470 decisions flagged: 323 negative / 147 caution) + wired into `retrieve_context`,
  MCP/chat serializers, and the chat system prompt. §8 Q4/Q5 resolved (re-scan body_text;
  `source_metadata` cache). Advisory (no ranking change); evidence sentence shipped with
  every flag. Uncommitted.
- 2026-06-09: **PR4 done** — verify+abstain extraction + stale-use gate. Shared
  `answer.py` (`verify_answer`/`render_advisory`/`should_abstain`/`abstain_decision`),
  silent-vs-acknowledged stale-use detection, additive `abstain` on chat + MCP, and a
  block path behind `RAG_ABSTAIN_BLOCKING` (default off; threshold 5). §8 Q2 resolved.
  453/1-known-red. Adversarial review caught + fixed a critical name-anchor bug
  (mined from heading, not citation) before merge. Uncommitted.
- 2026-06-09: **PR5 done** — three flag-gated LLM layers (all default-off, all reuse
  `semantic_support`): treatment **v2** (`treatment_llm.py` + `annotate_treatment
  --llm`; confident-override / confident-drop / uncertain-keep-v1 policy, depth-gated),
  claim-level **NLI** (`answer.py`, `RAG_CLAIM_NLI`, advisory misgrounding), and
  **query rewrite** (`query_rewrite.py` + `retrieve_context` hook, `RAG_QUERY_REWRITE`,
  guaranteed passthrough). 499/1-known-red. Adversarial review: 1 low fix
  (`target_is_subject` bool-normalization); 1 dismissal backed by real-corpus
  measurement. Live-validated: v2 rejected the *Metropolitan Jacobson* false positive
  the PR4 live test exposed; claim-NLI caught a fabricated holding; rewrite tightened
  lay questions. Uncommitted.
  Remaining (operational / measurement, not new PRs): (a) run `annotate_treatment
  --llm` over the full corpus to refine the 470 stored flags (cost: one gpt-4o call per
  candidate); (b) the PR4 carry-forward — extend `eval_caselaw` with abstain-rate /
  stale-block-rate (and now a v1-vs-v2 treatment-precision A/B) on an adversarial query
  set. The phased design plan (PR1–PR5) is complete.
