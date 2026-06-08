# Iowa Caselaw — Acquisition + Node Mapping + Ingestion Plan

**Status:** proposed · **Date:** 2026-06-03 · **Scope:** Iowa state caselaw only
(CourtListener courts `iowa` = Supreme Court of Iowa, `iowactapp` = Court of Appeals of Iowa)

## Decisions (locked 2026-06-03)

1. **Coverage:** ingest *all* opinions (published + unpublished); store `precedential_status`
   and treat published-only as a retrieval/display policy, not an ingestion filter.
2. **Source model:** one Source `iowa-caselaw`; court (`iowa`/`iowactapp`) lives in
   `source_metadata` and is filterable. No split by court.
3. **Decision-level NodeVersion:** create one holding syllabus/headnotes/summary *only when
   non-empty*; otherwise the decision node is a pure container.
4. **Embeddings deferred + chunked:** ingest cases now with full text + FTS + metadata (no
   embeddings needed to be useful). Run the embedding pass *later*, via the shared `Chunk`
   model (rules + cases) — never ship single-vector-per-opinion. Decoupling (Phase 3 vs
   Phase 4) makes this free: ingestion isn't blocked on chunking, chunking isn't rushed,
   vector search lights up after the later chunked pass.

## Goal

Ground chat/RAG in Iowa **caselaw** alongside the Iowa Code and Court Rules, reusing the
generic `Source / NodeType / Node / NodeVersion` model and the existing hybrid
FTS+trigram+pgvector search — no schema surgery. Acquire historical opinions free via
CourtListener **bulk data**, keep current via the free **API**, ingest **resumably** so a
crash leaves a usable partial corpus.

## Source data (all free, public-domain / CC0)

- **Backfill:** CourtListener quarterly bulk CSVs (`opinion-clusters` ~2.3 GB,
  `opinions` ~50 GB, `citations` ~120 MB, `dockets` ~4.6 GB for the court join,
  `courts` ~80 kB). Contains all of the Harvard Caselaw Access Project + scraped cases.
- **Ongoing:** CourtListener REST API filtered `?court=iowa&court=iowactapp` (free token;
  Iowa's weekly volume is well under the 125/day default rate limit). Fallback: scrape
  `iowacourts.gov` or re-pull the quarterly bulk delta.
- **Embeddings are NOT reused.** CL ships 768-dim fine-tuned-ModernBERT vectors (~2 TB);
  incompatible with our 1024-dim Voyage Law 2 space and our fixed `VectorField(1024)`.
  We re-embed case text with Voyage Law 2 via the existing embeddings job.

## CourtListener data model → our model

CL shape: `Court → Docket → OpinionCluster → Opinion(s)` + `Citation(s)`.
A **cluster** = one decision; it groups 1..n **opinions** (lead / concurrence / dissent).
We model a decision as a 2-level hierarchy, mirroring Code's chapter→section:

```
Source "iowa-caselaw"
  NodeType level 1: "decision"   (the case / cluster — container + metadata)
  NodeType level 2: "opinion"    (lead/concurrence/dissent — carries the text + version)
```

### Source (one new row under existing `iowa` Jurisdiction)

| field | value |
|---|---|
| `slug` | `iowa-caselaw` |
| `name` | `Iowa Caselaw` |
| `citation_abbreviation` | per-case (built from reporter + court); source value generic |
| `official_url_template` | `https://www.courtlistener.com/opinion/{cl_cluster_id}/{slug}/` |

(Option: split into `iowa-supreme-court` + `iowa-court-of-appeals`. Recommended: keep one
source, store court on the node — simpler, and source-scoped search still works.)

### Node — level 1 "decision"  (from `OpinionCluster`)

| Node field | From CL |
|---|---|
| `node_type` | `decision` |
| `parent` | null |
| `path` | stable key `cl-cluster-<cluster_id>` (unique, immutable) |
| `ordinal` | `date_filed` (sortable) |
| `heading` | `case_name_short` (fallback `case_name`) e.g. `State v. Smith` |
| `is_repealed` | always `False` (precedential history tracked in metadata, not here) |
| `source_metadata` (JSON) | `cl_cluster_id`, `court_id` (`iowa`/`iowactapp`), `court_name`, `date_filed`, `precedential_status` (Published/Unpublished/…), `judges`, `docket_number`, `citations[]` (all parallel reporter cites), `citation_count`, `scdb_id`, `disposition`, `posture`, `nature_of_suit`, `syllabus`, `headnotes`, `summary`, `source_url` |

Decision node is a **container** (no `NodeVersion` required, like Code chapters).
*Optional:* attach a `NodeVersion` holding `syllabus`/`summary` so the case head-matter is
itself retrievable/embeddable.

### Node — level 2 "opinion"  (from `Opinion`, 1..n per cluster)

| Node field | From CL |
|---|---|
| `node_type` | `opinion` |
| `parent` | the decision node |
| `path` | `cl-cluster-<cluster_id>/op-<opinion_id>` |
| `ordinal` | opinion order (lead first) |
| `heading` | type + author, e.g. `Majority Opinion (Mansfield, J.)` |
| `source_metadata` (JSON) | `cl_opinion_id`, `type` (lead/concurrence/dissent/combined), `author_str`, `author_id`, `per_curiam`, `joined_by_str`, `page_count`, `download_url`, `extracted_by_ocr`, `sha1` |

### NodeVersion — one per opinion node (cases are immutable → single version)

| NodeVersion field | Value |
|---|---|
| `body_text` | best available text, preferring `plain_text`; else strip `html_with_citations` → `html_columbia`/`html_lawbox`/`xml_harvard` (CAP cases arrive as `xml_harvard`) |
| `effective_from` | `cluster.date_filed` |
| `effective_to` | `null` (always current) |
| `enacted_by` | e.g. `Decided <date_filed> · <court_name> · <precedential_status>` |
| `content_hash` | SHA-256 of normalized `body_text` (existing convention) |
| `search_vector` | `tsvector(body_text)` — FTS available immediately on write |
| `embedding` / `embedding_source_hash` | `null` initially → filled by Voyage Law 2 embeddings job |
| `review_status` | `APPROVED` (auto-approve: bulk public caselaw, no human review) |

### Citations & cross-references

- `Citation` rows (`volume`, `reporter`, `page`) → build `987 N.W.2d 123`; store all
  parallel cites in decision `source_metadata.citations[]`.
- New `CitationFormat` row, e.g. `{case_name}, {citation} ({court} {year})`.
- `CrossReference` (phase 2):
  - CL `citation-map` → case→case links (`from_version` = citing opinion, `to_node` =
    cited case if in-corpus, else `external_text`).
    - **As-built note (2026-06-08):** the case→case edges were first built from the
      inline `<a>` links in `html_with_citations` (`backfill_caselaw_cross_references`,
      `source=caselaw_link`, ~693K edges) — which carry **no depth**
      (`CrossReference.weight` = NULL). The `citation-map` bulk file
      (`search_opinionscited`, the table that carries `depth`) was **not** ingested
      until the RAG pipeline's PR2.5 (`build_caselaw_citation_graph`,
      `source=caselaw_graph`, `weight=depth`), which the treatment/good-law pass
      needs. The two passes coexist on different `source` values.
  - **High-value:** parse Iowa Code §/Court Rule references in opinion text → link cases to
    statute/rule nodes. This is the payoff — grounding cases *to* the existing corpus.

### Edition

Not applicable to caselaw (no annual snapshots). Skip; cases are point-in-time by
`date_filed`. The as-of-date/Edition machinery stays statute-only.

---

## Ingestion plan — new app `ingestion_caselaw` (mirrors `ingestion_iowa_code`)

Designed so **"stops halfway → keep half the cases"** holds: per-batch commits +
idempotent upserts + a checkpoint. Two phases keep the expensive 50 GB pass read-only.

### Phase 1 — Acquire/filter (read-only; rerunnable; touches no DB)

Stream-filter the bulk CSVs to the tiny Iowa slice. **Never decompress to disk; never use
`grep`/`awk`** (opinion bodies contain newlines/commas inside quoted fields — line tools
corrupt rows). Use a streaming CSV parser (Python `bz2` + `csv` with raised
`field_size_limit`).

1. `courts` → confirm court ids `iowa`, `iowactapp`.
2. Stream `dockets` → set of `docket_id` where `court_id ∈ {iowa, iowactapp}` (held in RAM,
   trivial).
3. Stream `opinion-clusters` → `clusters.jsonl` for clusters whose `docket_id` is in the set
   (capture metadata); collect their `cluster_id`s.
4. Stream `citations` → cite rows for those clusters.
5. Stream `opinions` (50 GB) → `opinions.jsonl` for rows whose `cluster_id` is in the set.

Output: small local JSONL (~2–4 GB, fits the 74 GB disk). Record the blob in
`RawIngestion` (`content_hash`, `storage_path`, `fetched_from`) for audit.
If Phase 1 dies, just rerun — it's read-only.

### Phase 2 — Parse (pure, golden-file testable)

JSONL → `ParsedDecision` / `ParsedOpinion` dataclasses (mirror `ParsedChapter`/
`ParsedSection`). Pick best text field, normalize whitespace, compute `content_hash`.
No DB, no I/O — deterministic.

### Phase 3 — Write (atomic, batched, idempotent → crash-safe)

`apply_changeset` per batch (~100–500 decisions), each in its own transaction:

- upsert decision Node (`get_or_create` on `path = cl-cluster-<id>`)
- upsert opinion child Nodes
- create `NodeVersion` per opinion **only if `content_hash` changed** (idempotent re-runs)
- set `review_status = APPROVED`, populate `search_vector`
- write an `IngestionRun` row with counts **and the last processed `cluster_id` (checkpoint)**
- **commit per batch** → durable partial progress

Resume = rerun: existing nodes are skipped via the stable `path`/`content_hash`; the
`IngestionRun` checkpoint lets a resume run fast-forward.

### Phase 4 — Embed (separate, idempotent, independently resumable)

**Deferred by decision #4.** Cases are useful at end of Phase 3 (full text + FTS + metadata,
searchable + citable) with **no embeddings**. The embedding pass runs *later*, over the
already-ingested cases, via the shared **`Chunk`** model (see `COURT_RULES_DOCLING_PLAN.md`)
— opinions fan out into chunk rows, each embedded with Voyage Law 2 (1024-dim). We do **not**
ship single-vector-per-opinion. The existing job's `content_hash != embedding_source_hash`
trigger still drives it, just at the chunk grain. Independently runnable/resumable; vector
search lights up after this pass. `body_text` is preserved at ingestion so this needs no
re-ingest.

### Phase 5 — Ongoing updates (free)

Weekly: API `GET /clusters?court=iowa&court=iowactapp&date_filed__gte=<last_run>` →
same Parse→Write→Embed path. Well under the free 125/day rate limit.

## Resumability summary

| Phase | Crash behavior |
|---|---|
| 1 Acquire | read-only; rerun freely |
| 3 Write | per-batch commit → **half done = half the cases persisted**; idempotent rerun finishes |
| 4 Embed | independent; embeds whatever rows exist; resumes on next run |

## Remaining open items (post-decision)

- **Retrieval policy for unpublished:** ingest-all is locked; still to decide whether default
  retrieval serves unpublished opinions and how the UI/verification layer labels them.
- **`Chunk` model design** is a shared workstream with Court Rules — sequencing of that build
  vs. the caselaw embed pass.
