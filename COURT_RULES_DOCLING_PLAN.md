# Iowa Court Rules — Docling + Chunking + PDF Highlighting Plan

**Status:** proposed · **Date:** 2026-05-30 · **Scope:** Iowa Court Rules (`iowa-court-rules`) only

## Goal

Rework Court Rules processing so we can (1) retrieve the *precise* section or comment a
user is looking for and (2) **highlight that exact span in the original PDF**. Four
decisions drive the design:

1. **Docling replaces pdfplumber** as the extractor — emits structured content **plus
   provenance** (page number + bounding boxes).
2. **New `Chunk` model** (FK → `NodeVersion`): each rule's body and comment fan out into
   chunk rows, each with its own embedding + provenance. Versioning/citation semantics
   stay on `NodeVersion`.
3. **Highlight target = the original PDF** rendered in the browser, using docling's
   page+bbox provenance.
4. **Embed chunks; the rule is the result** — retrieval ranks chunks, then groups/dedupes
   to the parent rule and surfaces the best-matching chunk as the highlight span.

## Why now

Long official Comments (some 4,700+ chars) are currently concatenated into one
`NodeVersion.body_text` under a `\n\nComment\n\n` banner (`apps/ingestion_iowa_rules/parser.py`
`combined_text`) and embedded as a single vector (`apps/corpus/services/embeddings.py`
`_text_for_embedding`). That dilutes both retrieval precision and embedding signal, and
flattened pdfplumber text carries no coordinates, so there is nothing today to drive PDF
highlighting.

---

## Current state (baseline)

- **Extraction:** `Iowa Court Rules/probe.py` (pdfplumber, `x_tolerance=1.5`) → `probe.json`
  (70 chapters, 1,205 rules). Body/comment split at a literal `Comment` line; no coordinates.
- **Ingestion:** `apps/ingestion_iowa_rules/` parser → differ → validators → writer creates
  one `Node` + one `NodeVersion` per rule. Comment folded into `body_text`.
- **Search:** `apps/corpus/services/search.py` — FTS + trigram + pgvector (1024-dim) fused
  with RRF, all keyed on `NodeVersion.id`. One embedding per `NodeVersion`
  (`heading + body_text`). Trigram is heading-only by design.
- **Frontend:** Next.js `chat-frontend` (assistant-ui). No PDF viewer dependency.
- **PDFs:** committed under `Iowa Court Rules/pdfs/chapter-NN.pdf`; URL pattern recorded in
  the source README. Sizes range from <100 KB to 23 MB (ch 7 Probate, ch 2 Criminal).

---

## Workstreams

### A. Docling extractor → `probe.json` v2  *(replaces `Iowa Court Rules/probe.py`)*

- New docling-based probe emitting the same chapter→rule shape, but each rule's body and
  comment carry **provenance**: `page_no` + `bbox` (PDF coords) per text segment, and the
  body/comment split comes from docling's *structural* heading detection rather than the
  literal-line heuristic.
- Gate output against current counts (70 chapters / 1,205 rules) to catch parse regressions.
- **Risk — non-determinism:** docling is an ML pipeline, not byte-deterministic. Mitigation:
  the committed `probe.json` remains the stable golden artifact; golden-test the
  parser/chunker *against the JSON*, not docling itself (the existing "probe.json is the
  contract" pattern).
- **Deliverables:** new probe script + `requirements` entry for `docling`; regenerated
  `probe.json` (v2 schema documented in `Iowa Court Rules/README.md`).

### B. `Chunk` model  *(`apps/corpus/models.py` + migration)*

- FK → `NodeVersion`; fields: `ordinal`, `kind` (`body` | `comment`), `text`, char range
  within the body, `page_no`, `bbox` (JSON), `embedding` VectorField(1024), `search_vector`,
  `content_hash`, `embedding_source_hash`.
- HNSW index on `embedding` (cosine), GIN on `search_vector` — mirrors `NodeVersion`.
- **Deliverables:** model + migration; admin registration for inspection.

### C. Chunking service  *(`apps/corpus/services/chunking.py`)*

- Structure-aware split: rule prose by paragraph; Comments by their numbered `[1]/[2]`
  paragraphs; char/token target with small overlap. Attach docling provenance per chunk.
- Hook into `apps/ingestion_iowa_rules/writer.py`: regenerate a `NodeVersion`'s chunks
  whenever it is (re)written. Add a `rechunk_corpus` management command for backfill.
- **Deliverables:** service + writer hook + management command + golden tests.

### D. Embeddings over chunks  *(extend `apps/corpus/services/embeddings.py`)*

- Same `content_hash != embedding_source_hash` contract, iterating `Chunk` rows. Voyage
  client unchanged. `embed_corpus` command embeds chunks.

### E. Chunk-level retrieval  *(`apps/corpus/services/search.py`)*

- `vector_search` + FTS query **chunks**; trigram stays heading-level on `Node`.
- RRF fuses chunk hits, then **group by parent `NodeVersion`, keep the best chunk** →
  `SearchHit` gains `best_chunk` (text + page + bbox).
- Thread highlight provenance through the API (`apps/api/`), MCP server, and chat.

### F. Frontend PDF highlight  *(`chat-frontend`)*

- Add a pdf.js / react-pdf viewer; serve the chapter PDF via a backend endpoint
  (page-scoped, given 6–23 MB chapters) and draw the highlight rectangle from `bbox`.
- **Coordinate note:** docling bbox origin (bottom-left) must be converted to the viewer's
  coordinate space.

### Cross-cutting

- Re-seed / re-embed Court Rules; run `manage.py eval_search` precision@5 **before/after**
  to prove chunking helped.
- App-specific test suite (still deferred per `TASKS.md`): golden-file parser/chunker +
  idempotency, mirroring the 42 Iowa Code tests.

---

## Open decisions (to discuss before/while building)

1. **Starting point — chosen:** save this plan first (this document). Build order proposed:
   *spike docling on one representative chapter (e.g. ch 32 Prof. Conduct) to confirm clean
   body/comment structure + usable bboxes → A → B → C → D → E → F.*
2. **Iowa Code coexistence — UNDECIDED.** Iowa Code has live NodeVersions + embeddings on
   the whole-NodeVersion retrieval path. Options on the table:
   - leave Iowa Code on rule-level retrieval; only Court Rules get chunks (retrieval handles
     both kinds of hit);
   - hard-scope all new retrieval/highlight to `iowa-court-rules` only;
   - design chunks generically and backfill Iowa Code later.
   **Needs a decision** because it determines whether `search.py` fuses chunk hits and
   nv hits together or branches by source.
3. **PDF serving:** stream from backend (page-scoped) vs. proxy legis.iowa.gov vs. object
   storage. Affects highlight overlay feasibility (cross-origin) and cost.
4. **Embedding model:** still the open `voyage-law-2` vs `cohere embed-v3 legal` eval from
   `TASKS.md` — chunking changes the eval inputs, so re-run on chunks.

---

## Definition of done

- Docling probe regenerates `probe.json` v2 with provenance; counts match baseline.
- `Chunk` rows exist for every approved Court Rules `NodeVersion`, embedded.
- Search returns rules ranked by best-chunk relevance, with highlight provenance attached.
- Frontend renders the chapter PDF with the matched span highlighted.
- `eval_search` precision@5 ≥ current baseline (target: improvement on long-comment rules).
