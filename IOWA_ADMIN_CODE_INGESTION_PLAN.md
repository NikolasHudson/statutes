# Iowa Administrative Code — Ingestion Plan

_Created 2026-07-10. Owner: Nick. Status: scoped, ready to build. This is P1 in
`COMPETITIVE_PLAN_LEXIOWA.md` — the top corpus gap vs. LexIowa._

## Why

LexIowa advertises the Iowa Administrative Code (IAC); we don't have it. Adding it
closes the most visible coverage gap and, as a bonus, produces a **statute↔regulation
citation graph** — every IAC rule names its enabling Iowa Code chapter — which is a
differentiator, not just parity. The data is a Iowa government publication (no copyright),
and the ingest skeleton is a near-copy of the existing Iowa Court Rules app, so the risk
is low and the leverage is high.

## What the IAC is (verified 2026-07-10 against legis.iowa.gov)

- The composite of all executive-branch agency rules, organized **Agency → Chapter →
  Rule → subrule/paragraph**. A rule citation is `441—65.2(234)`: agency `441`, chapter
  `65`, rule `2`, and `(234)` is the **enabling Iowa Code chapter** the rule implements.
- **~85 agencies**, roughly **2,500–3,500 real (non-reserved) chapters** (agency 441/HHS
  alone has 129; 481 has 355), on the order of **30k–50k rules** and **~6–10M tokens** →
  embedding cost is trivial (~$1–3 on voyage-law-2). The scraper will produce exact counts.
- Updated **biweekly** (Iowa Code ch. 17A); each publication has a `pubDate` (e.g.
  `07-08-2026`) that is a natural **edition** key.

### Data source & URL patterns

| What | URL |
|---|---|
| Agency list | `/law/administrativeRules/agencies` |
| Chapter list for an agency | `/law/administrativerules/chapters?agency={id}&pubDate={MM-DD-YYYY}` |
| Chapter document (editable) | `/docs/iac/chapter/{pubDate}.{agency}.{chapter}.rtf` |
| Chapter document (print) | `/docs/iac/chapter/{pubDate}.{agency}.{chapter}.pdf` |
| Whole-agency print | `/docs/iac/agency/{pubDate}.{agency}.pdf` |

> **⚠ Load-bearing gotcha: the `.rtf` links are actually DOCX** (Office Open XML — a ZIP
> with `word/document.xml`; `file` reports "Microsoft Word 2007+"). We **cannot** reuse the
> Iowa Code `striprtf` parser. Parse with **`python-docx`** (clean paragraph iteration) —
> not hand-rolled XML, and not the docling service (which is wired only to Verify-Document
> and returns markdown). This is the one real deviation from the existing ingesters.

### Real text structure (from agency 441, chapters 1 and 65)

Paragraph stream after DOCX extraction looks like:

```
CHAPTER 65
SUPPLEMENTAL NUTRITION ASSISTANCE PROGRAM ADMINISTRATION
[Prior to 7/1/83, Social Services[770] Ch 65]      ← renumbering history
441—65.1(234) Definitions.                          ← RULE head: agency—chap.rule(enabling)
“Notice of expiration” means …                      ← definition line (rule body)
[ARC 9310C, IAB 5/28/25, effective 8/1/25]          ← history/effective-date bracket
441—65.2(234) Administration of program. SNAP will…
1.3(1)⁠General. …                                    ← SUBRULE: chap.rule(subrule)
```

Grounded parser rules:
- **Rule head**: `^(?P<agency>\d+[A-Z]?)—(?P<chap>\d+)\.(?P<rule>\d+)\((?P<enabling>[0-9A-Z, ]+)\)\s*(?P<heading>.+?)\.`
- **Subrule**: `^(?P<chap>\d+)\.(?P<rule>\d+)\((?P<sub>\d+)\)` (em-space ` ` before heading) — kept inside the rule body for v1.
- **History bracket**: `^\[ARC ([0-9A-Z]+), IAB (\d+/\d+/\d+), effective (\d+/\d+/\d+)` → `effective_from` + `enacted_by=ARC #`.
- **Renumbering history**: `^\[Prior to …\]` → store in `source_metadata["prior_agencies"]` (this encodes the old agency numbers, e.g. `[770]`, `[498]` — the crosswalk fuel for historical-citation resolution; see Risks).

## How it maps onto our data model

(Model recipe confirmed in `backend/apps/corpus/models.py`; there is **no `kind` column** —
structure is data via `NodeType`, and browse/search/resolution are slug-driven off `Source`.)

- **Source** (one row, seed migration): `slug="iowa-admin-code"`,
  `citation_abbreviation="Iowa Admin. Code"`,
  `official_url_template="https://www.legis.iowa.gov/docs/iac/chapter/{pubDate}.{path}.pdf"`.
- **NodeType** rows (hierarchy is data): `agency` (level 0), `chapter` (level 1),
  `rule` (level 2, the leaf). **Include a `chapter` key** — browse's `list_sources`
  (`browse.py:110`) checks `"chapter" in node_types` to render a source as statute-style;
  and `rule` is already a recognized leaf key (`browse.py:113`).
- **Node** (`path` is the citation key, unique per source):
  - agency → `path="441"`, `heading="Health and Human Services Department"`, `parent=None`
  - chapter → `path="441.65"`, `ordinal=65`, `heading="SNAP Administration"`, `parent=agency`
  - rule → `path="441.65.2"`, `ordinal=2`, `heading="Administration of program"`, `parent=chapter`
  - Display citation `441—65.2` rendered via `CitationFormat`; the dotted `path` is the
    internal key (clean ordinal splitting, matches the Iowa Code `chapter.section` pattern).
- **NodeVersion** (append-only, the load-bearing text): `body_text` = rule text incl.
  subrules; `effective_from` from the history bracket (default to `pubDate` if none);
  `content_hash` over normalized body only (so a heading fix doesn't re-embed);
  `review_status=PENDING` until approved. `body_segments` (display-only) can hold the
  subrule structure for rich rendering.
- **Embedding**: rules are section-sized → **embed whole NodeVersions** (like statutes/
  rules, not chunked). `voyage-law-2`, dim 1024. The retriever auto-detects granularity via
  `_embedding_granularities` (`search.py:849`) — **no routing code needed**.

**Design decision — 3-level hierarchy (Agency→Chapter→Rule).** Agency is a real node
level because chapter numbers repeat across agencies (chapter "1" exists ~85 times) and
attorneys navigate the IAC by agency. Trade-off: the current browse UI assumes 2 levels
(chapter→leaf); a 3-level source needs a small **agency browse tier** (or an agency facet).
See Phase 2. (Alternative considered: flatten agency into the chapter node's path prefix to
avoid any browse change — faster v1, but a ~3,000-row flat chapter list. Rejected for v1
navigation quality; kept as a fallback if the browse tier slips.)

## Implementation phases

### Phase 0 — Parser spike (~0.5 day) — ✅ DONE 2026-07-10
Prove the DOCX parser on 2–3 agencies. Deliverable: `parse_chapter_docx(bytes) ->
ParsedChapter` emitting probe JSON; eyeball rule/subrule/history splitting and the
enabling-statute capture.

**Results** (spike at `scratchpad/iac_parse_spike.py`, stdlib `zipfile`+ElementTree; run
over 441 ch. 1/8/65/75 + 191 ch. 1 = 74 rules): rule-head, subrule, enabling-statute,
effective-date/ARC, and prior-agency capture **all validated**. **80 enabling-statute
edges from 74 rules, 0 rules missing an enabling chapter** — the statute↔reg graph is real
and dense. Multi-statute parentheticals split correctly (`191—1.1(502,505)`); internal
cross-refs (`441—Chapter 2506`) and subrules preserved in body; 0 rules missing a parsed
effective date. Heading/body split (partition on first period) was clean on all 74 — the 5
long headings flagged were genuinely long, not mis-split.

**Refinements for production** (surfaced by the spike):
1. **Use `python-docx` + bold-run detection** for the heading/body split. Rule headings are
   bold in the DOCX; splitting on the bold run is more robust than period-partitioning
   against the abbreviation-period edge case (none hit in the sample, but they exist). Add
   `python-docx` to `backend/requirements`.
2. **PDF fallback for some agencies.** Letter-suffix / small agencies (e.g. 193A) expose
   only an **agency-level PDF** (`/docs/iac/agency/{pubDate}.{agency}.pdf`), no per-chapter
   DOCX. The scraper must detect "no chapter DOCX" and fall back to the PDF (docling extract
   path) or skip if genuinely all-reserved.
3. **Chunk the longest rules.** Confirmed a few giant rules (Medicaid `441—75.3` ≈ 19.6k
   chars ≈ ~5k tokens). Embed whole for v1; chunk rules above a token threshold via the
   caselaw chunker if eval shows recall misses on them.

### Phase 1 — Core ingest (~2–3 days) — ✅ APP BUILT & PROVEN 2026-07-10
**Status:** the app is built and validated end-to-end on real data (agencies 601 + 7:
9 chapters, 78 rules, 0 failures). Seed migration `0022_seed_iowa_admin_code` applied on
dev; scrape → ingest (idempotent re-ingest = 78 unchanged) → approve → embed all green;
retrieval returns IAC rules **both scoped and unscoped**, blending with the Iowa Code
enabling statute (§ 17A) and caselaw automatically — no retrieval-routing code touched.
Remaining in Phase 1: run the **full scrape** (all ~85 agencies) and add golden-file parser
tests (mirror `ingestion_iowa_code/tests/test_parser.py`). **Prod caveat:** migration `0022`
must be run in prod (manual — no migrate job), same as PR9's `0020`.

Mirror `backend/apps/ingestion_iowa_rules/` as a new app **`ingestion_iowa_admin_code/`**:
1. **Seed migration** (copy `corpus/migrations/0007_seed_iowa_court_rules.py`): `Source` +
   the three `NodeType` rows + `CitationFormat`.
2. **`scraper.py`** — reuse the Iowa Code `Fetcher` pattern (polite rate-limit + on-disk
   sha256 URL cache + backoff; the site is a government server). `enumerate_agencies()` →
   per-agency `enumerate_chapters()` (skip "Reserved") → fetch each chapter DOCX →
   `parse_chapter_docx()`. Emit probe JSON:
   `{pub_date, agencies:[{agency, agency_name, chapters:[{chapter, chapter_title, title_group, prior_agencies, rules:[{number, heading, body_text, enabling_statutes, subrules, arc, effective_from}]}]}]}`.
3. **`parser.py` / `differ.py` / `validators.py` / `writer.py`** — near-duplicates of the
   rules app. `writer.get_iowa_admin_code_source()` by slug; `apply_changeset` writes
   PENDING NodeVersions and is the only mutation point; import the shared
   `RawIngestion`/`IngestionRun` from `ingestion_iowa_code.models`. Path convention
   `agency.chapter.rule`; `content_hash` over body only; idempotent re-ingest via the
   existing open-version diffing.
4. **Commands** `scrape_iowa_admin_code` + `ingest_iowa_admin_code <json> [--dry-run]`.
5. Run full scrape → ingest to PENDING → **approve** → `python manage.py embed_corpus
   --source iowa-admin-code`. **Now retrievable in search/chat with zero retrieval changes.**

### Phase 2 — Browse / search / citation surface (~1 day)
Concrete hardcode extensions (all identified with file anchors):
- **Search filter**: add `"admin_code": "iowa-admin-code"` to `_DOC_TYPE_SLUG`
  (`search_common.py:168`).
- **Citation rendering**: add the em-dash `r.` form for this slug in
  `corpus_tools._render_citation` (`:88`) and the kind map in `search_common._search_row`
  (`:94`).
- **Inline cross-refs**: extend `browse.node_detail`'s `slug == "iowa-code"` check (`:230`)
  to include `iowa-admin-code`.
- **Agency browse tier**: add agency grouping/facet to `list_chapters` (or a new
  `/agencies` browse endpoint) so navigation is Agency → Chapter → Rule. (Fallback:
  agency facet on a flat chapter list.)

### Phase 3 — Statute↔regulation graph, editions, currency (~2–3 days)
- **Enabling-statute cross-source edges (the differentiator).** New backfill command:
  for each IAC rule version, resolve each `enabling_statutes` chapter → the `iowa-code`
  chapter Node → write a `CrossReference(from_version=rule, to_node=code_chapter,
  source=STATUTE)`. **Note: no cross-source resolver exists** (`citations/resolver.resolve`
  takes a single `source`) — this is genuinely new code. Model on
  `corpus/management/commands/backfill_cross_references.py`.
- **Citation parser** (`citations/parser.py`): teach `_SIGIL_TOKEN_RE` / `_BODY_RE` /
  `_ITER_RE` the `Iowa Admin. Code` / `IAC` / `r.` sigils and the `441—65.2(…)` em-dash
  form; normalize to the dotted `path`. **Disambiguation nuance**: a parenthetical on a
  *rule* is the enabling statute; on a *subrule* it's the subrule index — resolve by
  whether the number matches a known Iowa Code chapter, else treat as subrule and resolve
  best-effort to the parent rule (like Iowa Code resolving `714.16(2)` → `714.16`).
- **Editions**: `register_edition --source iowa-admin-code --as-of <pubDate>` for the
  current publication; **generalize `compare_editions`'s `node_type__key="section"` filter**
  (`editions.py:97,103`) to also accept `"rule"` so IAC gets the diff feature. Biweekly is
  too frequent to snapshot every edition — snapshot quarterly.
- **Biweekly update job**: a `update_iowa_admin_code` command (model on
  `update_iowa_caselaw`) that reads the latest `pubDate`, re-scrapes changed chapters, and
  lets the `content_hash` differ no-op the unchanged ones. Wire into the current-awareness
  cadence.

### Phase 4 — Assistant + eval (~1 day)
- Add IAC to the assistant tool surface so chat/MCP retrieve and cite it (the system prompt
  and `corpus_tools` already route by source; confirm `lookup_citation` accepts an explicit
  `source=iowa-admin-code` — `_default_source` is hardcoded to Iowa Code, `lookups.py:1123`).
- Add IAC queries to the retrieval eval set; add a regression that the verification gate
  validates an `Iowa Admin. Code r. 441—65.2` citation + quote end-to-end.

## Risks & wrinkles

1. **2023–24 rules reorganization (biggest).** Under Executive Order 10, agencies were
   renumbered/consolidated and ~½ of rules rewritten. The *current* IAC uses new numbering,
   but historical caselaw cites *old* rule numbers (e.g. old DHS chapters). Citation
   resolution of historical cites will miss. Mitigation: capture the `[Prior to …]`
   renumbering brackets into metadata now (Phase 1) as crosswalk fuel; a full old→new rule
   map is future work, out of scope for v1.
2. **3-level browse tier** — the agency level needs a small browse addition (Phase 2) or
   the flatten fallback. Not a blocker for search/chat, only for browse navigation.
3. **`compare_editions` is section-only** — one-line filter generalization for the `rule`
   leaf (Phase 3).
4. **Enabling-statute vs subrule parenthetical ambiguity** — handle in the parser by
   number-shape/known-chapter check (Phase 3).
5. **Long rules** — a few IAC rules are very long; whole-version embedding may hurt recall
   on those. Ship whole for v1; if eval shows misses, `chunk_caselaw` generalizes to any
   source.
6. **DOCX quality / politeness** — some chapters may have malformed DOCX; fall back to the
   PDF via the existing docling extract path per-chapter. Scrape off-hours with the cached
   `Fetcher`; ~3,000 requests total.

## Effort & acceptance

- **MVP (searchable + chat-citable IAC): ~3–4 days** = Phase 0 + Phase 1 + the search/render
  slug wiring from Phase 2.
- **Solid v1 (browse tier + statute graph + editions + update job): ~1.5–2 weeks.**
- **Acceptance:** (a) `441—65.2` browsable and retrievable; (b) a chat question about a
  regulated topic cites a real IAC rule that the verification gate validates against source
  text; (c) that rule links to its enabling Iowa Code chapter in the graph; (d) the
  biweekly update job no-ops an unchanged chapter and ingests a changed one.

## The one-source-of-truth checklist

1. `python-docx` dependency + `parse_chapter_docx`.
2. Seed migration: `Source` + `agency`/`chapter`/`rule` NodeTypes + `CitationFormat`.
3. `ingestion_iowa_admin_code/` app (scraper/parser/differ/validators/writer + 2 commands).
4. Scrape → ingest PENDING → approve → `embed_corpus --source iowa-admin-code`.
5. Surface wiring: `_DOC_TYPE_SLUG`, `_render_citation`, `_search_row`, `node_detail`
   cross-refs, agency browse tier.
6. Cross-source enabling-statute `CrossReference` backfill (new code — no cross-source
   resolver today).
7. Citation parser extension for `441—65.2(…)`.
8. `register_edition` + generalize `compare_editions`; `update_iowa_admin_code` biweekly job.
9. Assistant/MCP source wiring + eval regression.
