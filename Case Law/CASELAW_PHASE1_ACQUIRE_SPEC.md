# Phase 1 (Acquire/Filter) Implementation Spec — `ingestion_caselaw`

**Status:** implementation-ready · **Date:** 2026-06-03 · **App:** `apps.ingestion_caselaw` (new, mirrors `apps.ingestion_iowa_code`)
**Honors locked decisions 1–4 (2026-06-03). No production code below — algorithms, file layout, and exact schemas only.**

> **As-built (2026-06-03):** implemented in `backend/apps/ingestion_caselaw/` (`csv_stream.py`, `acquire.py`, `models.py` + migration `0001`, `acquire_iowa_caselaw` command, golden tests). Adversarially reviewed; 139 app/corpus tests green. Two intentional deltas from the spec text: (1) `rejects.jsonl` decode-isolation uses `errors="surrogateescape"` decode + detect-at-encode (cleaner than a mid-stream catch); (2) **`search_citation.type` is kept nullable** (`_to_int_or_none`) — the real CL export schema allows null, so forcing `int` per §5.3 would discard valid citations. `persist_raw_artifact` hard-links each artifact to `<storage_dir>/<content_hash>.bin` (no disk doubling). `--resume` is deferred (a full re-run is always correct).

---

## 1. Goal + scope recap

Acquire Iowa state caselaw from CourtListener **quarterly bulk-data CSVs** (free, CC0/public-domain) and reduce the ~50 GB national dump to a small local Iowa slice that Phases 2–3 turn into `Source`/`Node`/`NodeVersion` rows in the existing `corpus` schema.

In scope for **Phase 1 only**:
- Two courts: `iowa` (Supreme Court of Iowa) and `iowactapp` (Court of Appeals of Iowa) — `search_court.id` slugs.
- **All** opinions, published + unpublished (locked decision 1). `precedential_status` is captured as a label, never a filter.
- Phase 1 is **read-only relative to the corpus DB**: it streams the bulk CSVs, writes intermediate JSONL files to local disk, and writes one `RawIngestion` audit row per JSONL artifact. It never touches `Node`/`NodeVersion`.
- **Resumable / rerunnable:** a crash mid-stream is recovered by re-running the command; outputs are written atomically (temp file + `os.replace`), so a half-written JSONL is never consumed.

Out of scope for Phase 1 (interfaces defined in §5): parsing/normalization (Phase 2), corpus writes (Phase 3), embeddings (Phase 4), ongoing API delta (Phase 5).

**Note — one required corpus-schema change.** This plan is otherwise "no schema surgery," but Phase 3 idempotency cannot be a pure DB invariant without it: `NodeVersion` currently has **no** unique constraint (only an FK to `node`; verified `corpus/models.py:92–114`). Phase 3 therefore depends on a new migration adding `UniqueConstraint(fields=("node","content_hash"), name="uniq_nodeversion_per_node_hash")`. This is called out explicitly in §7 and is a Phase-3 prerequisite, not a Phase-1 deliverable.

---

## 2. New app layout — `apps/ingestion_caselaw/`

Mirrors `apps/ingestion_iowa_code/` module-for-module. **Phase 1 owns `acquire.py` + `csv_stream.py` + the `RawIngestion`/`IngestionRun` models + the management command's acquire path.** Phase 2/3 modules are listed for context with their interface contracts; they are stubs in the Phase-1 deliverable. (Note: `ingestion_iowa_code` is an HTML/RTF scraper — it has **no CSV precedent**, so `csv_stream.py` is greenfield and cannot inherit a tested dialect; all CSV-correctness rules in §3 must be implemented and tested fresh.)

| File | Phase | Responsibility |
|---|---|---|
| `__init__.py` | — | empty |
| `apps.py` | — | `AppConfig`, `name = "apps.ingestion_caselaw"`, `default_auto_field`. |
| `models.py` | 1 | `RawIngestion` + `IngestionRun` (see §6, §7). Same shape as `ingestion_iowa_code/models.py`; adjusted `SOURCE_KIND_CHOICES` and added checkpoint fields on `IngestionRun`. |
| `csv_stream.py` | 1 | Low-level streaming reader: `open_bulk_csv(path_or_url) -> Iterator[dict[str,str]]`. Wraps `bz2` decompression in a `TextIOWrapper(..., encoding="utf-8", newline="")` + Python `csv.DictReader` configured for the CL bulk dialect (see §3). Raises `csv.field_size_limit(sys.maxsize)` inside `open_bulk_csv` (not at import). Selects columns **by header name, never positional**. Asserts `len(row) == len(header)` per row; coerces declared-nullable numeric columns `'' -> None`. **The only module that touches the CSV byte stream.** |
| `acquire.py` | 1 | The memory-bounded streaming JOIN (§3–§4). Functions: `collect_iowa_docket_ids`, `emit_dockets_jsonl`, `collect_iowa_cluster_ids`, `emit_clusters_jsonl`, `emit_citations_jsonl`, `emit_opinions_jsonl`, and the orchestrator `run_acquire(...)`. Emits four JSONL artifacts (§5) and records `RawIngestion` rows (§6). Pure I/O over CSV→JSONL; **no corpus DB writes.** |
| `parser.py` | 2 | Pure, deterministic. JSONL records → `ParsedDecision` / `ParsedOpinion` frozen dataclasses with `path` and `content_hash` properties (mirrors `ParsedChapter`/`ParsedSection`). Joins `dockets.jsonl` (by `docket_id`) for `docket_number`. Text-field selection + whitespace normalization live here. No DB, no I/O. Interface in §5. |
| `differ.py` | 3 | `Changeset` dataclass with `decisions_added/amended/unchanged` + `summary()` (mirrors `ingestion_iowa_code/differ.py`; `decisions_repealed` is intentionally dropped — see §7). `diff_against_db(parsed, source)` selects the open `NodeVersion` per node (`node__source=source, effective_to__isnull=True`, mirroring `differ.py:86–90`) and compares `content_hash`. Read-only DB. |
| `writer.py` | 3 | The only corpus-mutating module. `get_iowa_caselaw_source()` (looks up by `jurisdiction__slug="iowa", slug="iowa-caselaw"` — `Source.slug` is unique only per jurisdiction, `models.py:30–34`), `persist_raw_input(...)` / new `persist_raw_input_from_path(...)` (streaming-hash variant, §6), and `apply_changeset(...)` — per-batch `@transaction.atomic` upsert of **whole decisions** (§7). |
| `validators.py` | 3 | `validate(parsed, changeset) -> list[ValidationIssue]` (`ValidationIssue` fields `severity`, `code`, `path`, `message` — match `validators.py:17–21`). |
| `management/commands/acquire_iowa_caselaw.py` | 1 | Runs Phase 1 (§9 runbook). Args in §9. |
| `management/commands/ingest_iowa_caselaw.py` | 3 | Runs Phase 2→3 over the JSONL artifacts: read JSONL → parse → diff → validate → `apply_changeset` per batch. Mirrors `ingest_iowa_code.py`. |
| `tests/test_csv_stream.py` | 1 | Golden tests (§3): embedded newline; doubled-quote `""` inside a quoted field; a bare `\r` inside a quoted field stays in one field; a single field > 131072 bytes parses; a row with empty `author_id`/`page_count` coerces to JSON `null`. |
| `tests/test_acquire.py` | 1 | Golden test: tiny fixture `courts`/`dockets`/`clusters`/`citations`/`opinions` CSVs → expected JSONL artifacts; **two runs over the same fixture produce byte-identical artifacts (same SHA-256).** |
| `migrations/0001_initial.py` | 1 | `RawIngestion` + `IngestionRun`. |

**`Source` / `NodeType` bootstrap (one-time data migration or fixture; Phase-3 prerequisite, not Phase 1). All NOT-NULL fields must be set:**
- `Source`: `jurisdiction=<iowa>`, `slug="iowa-caselaw"`, `name="Iowa Caselaw"`, `citation_abbreviation="Iowa"` (NOT NULL, no blank — must be a real non-empty value; `models.py:25`), `official_url_template="https://www.courtlistener.com/opinion/{cl_cluster_id}/{slug}/"`.
- `NodeType`: `source=<iowa-caselaw>, key="decision", label_singular="Decision", level=1` and `source=<iowa-caselaw>, key="opinion", label_singular="Opinion", level=2`. `label_singular` is NOT NULL (`models.py:46`); `label_plural`/`abbreviation`/`citation_segment_template` are `blank=True`.

---

## 3. Memory-bounded streaming JOIN algorithm

### Hardware budget
7.8 GB RAM **total**, but only **~4 GB actually available** (measured: Postgres clone + Django + docling on :8001 already hold ~3.5 GB), **0 swap**, 2 cores, 74 GB free disk. The only thing held in RAM is the **join-key integer sets**; full row sets and text bodies must stream and never accumulate.

### CSV dialect — doubled-quote, no escape char (verified against the real file)
The CL bulk CSVs use **standard RFC-4180 doubled-quote escaping**: an embedded `"` is written `""`, not `\"`. Verified on the on-disk `courts-2026-03-31.csv.bz2`: **3193 occurrences of `""` vs 1 of `\"`** (the lone match is a literal backslash in content). Postgres `COPY ... (FORMAT csv)` always doubles the quote char; an `ESCAPE` clause only changes recognition, not output form. Configure Python `csv` as:

- `delimiter=','`, `quotechar='"'`, **`doublequote=True`** (the default), **`escapechar=None`** (no escape char). **Do NOT set `doublequote=False`/`escapechar='\\'`** — that mis-parses every quoted field containing a quote (drops the closing quote, can desync quote-state across the next delimiter and shift `court_id`/`docket_id`/`cluster_id` into the wrong column, silently corrupting the join keys) and would eat any literal `\` as an escape.
- Open the decompressed stream with explicit `newline=''`: `io.TextIOWrapper(bz2.open(path, "rb"), encoding="utf-8", newline="")`. Required by the `csv` docs; without it, universal-newline translation can split a record on a bare `\r` embedded in a quoted opinion body (common in Windows-authored HTML/Columbia imports).
- `csv.field_size_limit(sys.maxsize)` called **inside `open_bulk_csv` immediately before constructing the reader** (NOT at module import — the limit is process-global mutable state and import-order/lazy-import can silently revert it to 131072, killing the 50 GB opinions pass mid-stream). `sys.maxsize` is the idiomatic "effectively unlimited" value, correct on 32- and 64-bit.
- Iterate with `csv.DictReader` (header-name keyed) over the text stream; reconstruct each logical row regardless of how many physical newlines it spans. **Assert `len(row) == len(header)` per row and hard-fail on mismatch** — O(1), catches any residual quote-state desync before a wrong-column value reaches a key-set.

### Why `grep`/`awk`/`split -l`/`for line in f` are forbidden
Text columns (`plain_text`, `html_with_citations`, `xml_harvard`, court `notes`, …) contain **embedded newlines and commas inside double-quoted fields**. A single logical row routinely spans many physical lines — verified: the `courts` CSV is 3383 physical lines for ~3361 logical rows. Any line-splitting tool slices rows mid-quote and corrupts every downstream record. **The reader MUST track quote state**, which only `csv.reader`/`csv.DictReader` does.

### NULL vs empty-string, and nullable numeric columns
Python `csv` surfaces both an unquoted-empty field (`,,`) and a quoted-empty field (`,"",`) as `''` — it does not expose quoting state. **Text columns:** treat `''` as "absent"; Phase 2 tests `field != ""` (all CL text columns are `NOT NULL DEFAULT ''`, so this is correct). **Nullable numeric columns** (`author_id`, `page_count`): these arrive as bare `''` and would crash `int('')` or emit the wrong JSON type. `csv_stream`/the emit functions **must map `'' -> None`** for these declared-nullable numeric columns and serialize them as JSON `null`; all text columns map `'' -> ''`. Per-column nullability is documented in §5.2.

### Encoding / decode-error policy (skip-and-log, not file-abort)
All bulk files are UTF-8; decode strictly (no `errors="replace"`, which would mask a corrupt download). **But** decoding happens at the stream layer, so one bad byte 49 GB into the opinions file would otherwise raise `UnicodeDecodeError`, kill the whole pass, and re-hit the same byte on every restart (not resumable past a poison row — CL data has historically contained latin-1 fragments in old Lawbox/Columbia imports). **Decision: row-level isolation.** Wrap per-row iteration so a `UnicodeDecodeError`/`_csv.Error` is caught at the row level, logged with byte offset and last-good id, the bad row appended to a `rejects.jsonl` sidecar, and the pass continues. This converts "abort the 50 GB pass" into "drop and audit one row," satisfying the §7 resumability goal.

### Stream from local compressed copy, NOT the S3 URL
**Download the five `.csv.bz2` files to local disk first, then stream from the local `.bz2`.** Given 74 GB free:
- Compressed footprint: clusters ~2.3 GB + opinions ~50 GB + dockets ~4.6 GB + citations ~120 MB + courts ~80 kB ≈ **57 GB**, fits with margin. **Never decompress to disk** — `bz2` decompresses in-stream.
- Local files make Phase 1 **rerunnable offline and crash-safe**: a re-run does not re-pull 57 GB; a flaky mid-50 GB S3 stream would otherwise force a full restart.
- The download step records the source URL in `RawIngestion.fetched_from`; the local artifact path is `storage_path`.
- (Streaming directly from S3 is supported by `open_bulk_csv` accepting a URL but is the non-default fallback for a disk-pressured box.)

### Join path and sets held in RAM
The join path is `opinion.cluster_id → opinioncluster.id`, `opinioncluster.docket_id → docket.id`, `docket.court_id → court.id` — **the only path; there is no `court_id` on opinion or cluster.** Inverted into two integer key-sets:

| Set | Built from | Contents | Realistic size |
|---|---|---|---|
| `iowa_docket_ids` | `dockets` stream, keep where `court_id ∈ {"iowa","iowactapp"}` | `set[int]` of `search_docket.id` | Iowa = tens of thousands of dockets. At ~28 B/int even 1 M ids ≈ **~30–60 MB**; measured 1 M large-int set ≈ 62 MB, 3 M ≈ 220 MB. |
| `iowa_cluster_ids` | `opinion-clusters` stream, keep where `docket_id ∈ iowa_docket_ids` | `set[int]` of `search_opinioncluster.id` | Same order of magnitude, **tens of MB worst case.** |

**Only these two integer sets (plus a 2-entry `court_name_by_id` dict) live in RAM. No CSV rows, no text bodies, no JSONL accumulate** — every emit pass writes line-by-line to disk and discards the row. The JSONL writer must `write()` per row, never build a list then dump a batch.

**Docket-derived cluster fields are joined on disk, not carried in RAM.** The cluster record (§5.1) needs `court_id` and `docket_number`, both from `search_docket`. Pass 2 retains only the integer `id` in `iowa_docket_ids` — it does **not** widen the set into a `dict[int, (str, str)]` (that would attach per-docket free-text `docket_number` strings and grow unbounded). Instead, **pass 2 emits a fourth artifact, `dockets.jsonl`** (one line per Iowa docket: `id`, `court_id`, `docket_number`), and Phase 2 joins it to clusters by `docket_id` on disk. RAM stays a pure integer set. (`court_id` *can* additionally be denormalized into `clusters.jsonl` cheaply since its only two values are interned literals `"iowa"`/`"iowactapp"`; `docket_number` is recovered solely via `dockets.jsonl`.)

### Pass ordering (5 passes, each fully streamed)
1. **`courts`** (~80 kB): stream; assert `iowa` and `iowactapp` rows exist with expected `jurisdiction`; capture `full_name` into the 2-entry `court_name_by_id` dict.
2. **`dockets`** (~4.6 GB): stream; for each row with `court_id ∈ {"iowa","iowactapp"}`, add `id` to `iowa_docket_ids` **and emit one `dockets.jsonl` record** (§5.4). Discard every other row immediately.
3. **`opinion-clusters`** (~2.3 GB): stream; for each row with `docket_id ∈ iowa_docket_ids`, **emit one cluster JSONL record** (§5.1) and add `id` to `iowa_cluster_ids`. (Cluster record's `court_id`/`court_name` come from the docket's court via the already-built mapping; `court_name` from `court_name_by_id`.)
4. **`citations`** (~120 MB): stream; for each row with `cluster_id ∈ iowa_cluster_ids`, **emit one citation JSONL record** (§5.3).
5. **`opinions`** (~50 GB — expensive, last): stream; for each row with `cluster_id ∈ iowa_cluster_ids`, **emit one opinion JSONL record** (§5.2), carrying chosen text columns verbatim (selection deferred to Phase 2).

### Why it stays bounded
- RAM ceiling = `iowa_docket_ids` + `iowa_cluster_ids` + the 2-entry court dict = **tens of MB against ~4 GB available** (not 7.8 GB total); the bz2 decompressor's own buffers add only MBs. Safe by two orders of magnitude.
- Both key sets are built before they are needed (dockets before clusters; clusters before opinions), so each pass is a single forward scan with O(1) set membership — no random access, no second pass, no sort.
- The 50 GB opinions pass holds at most one row (`field_size_limit(sys.maxsize)` permits one ~few-MB opinion body, never multiple concatenated) plus the cluster-id set, and writes straight to `opinions.jsonl`. **Never** build a list of opinion rows, and never concatenate multiple bodies before writing.

---

## 4. Exact Iowa filter logic

**Court → docket → cluster → opinion (and citation), the only path:**
1. Court ids: literal set `{"iowa", "iowactapp"}` matched against `search_court.id`.
2. `iowa_docket_ids = { docket.id : docket.court_id ∈ {"iowa","iowactapp"} }`.
3. `iowa_cluster_ids = { cluster.id : cluster.docket_id ∈ iowa_docket_ids }`.
4. Keep `opinion` rows where `opinion.cluster_id ∈ iowa_cluster_ids`.
5. Keep `citation` rows where `citation.cluster_id ∈ iowa_cluster_ids` (citations attach to the **cluster**, not the opinion).

**Opinion text-column preference (carried through Phase 1; *selection* applied in Phase 2):** Phase 2 picks the first **non-empty (`!= ""`)** field in this order (all are `NOT NULL DEFAULT ''`, so test empty-string not NULL):

`html_with_citations` → `html_columbia` → `html_lawbox` → `xml_harvard` → `html_anon_2020` → `html` → `plain_text`.

Notes for Phase 2: `html_with_citations` carries CL `<a>` citation markup (strip tags in Phase 2); `xml_harvard` is CAP XML (not HTML); `plain_text` is last resort and is where `extracted_by_ocr=true` noise lives.

**`precedential_status` handling (locked decision 1):** ingest **all** values (`Published`, `Unpublished`, `Errata`, `Separate`, `In-chambers`, `Relating-to`, `Unknown`); store verbatim in the cluster record → decision `source_metadata.precedential_status`. No filtering anywhere in Phase 1. Published-only is a later retrieval/display policy.

---

## 5. Intermediate JSONL record schemas (Phase 1 output → Phase 2 input)

Four newline-delimited JSON files written under the run directory (§9): `clusters.jsonl`, `opinions.jsonl`, `citations.jsonl`, `dockets.jsonl` (plus the `rejects.jsonl` sidecar, §3). One JSON object per line, UTF-8.

**Serialization is pinned for byte-stable, dedupe-able output across runs and quarters:** `json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)` with the **explicit field order below** (never dict-insertion order from a changing CSV header map), `\n` line terminator, no trailing blank line. Column selection is **by header name, never positional** (CL has reordered/added columns between quarterly exports). All integer ids are JSON numbers; absent/empty text columns serialize as `""` (never null); the declared-nullable numeric columns (`author_id`, `page_count`) serialize as JSON `null` when empty. **The Phase-3 idempotent upsert keys are `cl-cluster-<cluster_id>` (decision Node path) and `cl-cluster-<cluster_id>/op-<opinion_id>` (opinion Node path), both derivable from these records.**

### 5.1 `clusters.jsonl` — decision/cluster record (one per `search_opinioncluster`)
| JSONL field | Type | Source column / derivation |
|---|---|---|
| `cl_cluster_id` | int | `search_opinioncluster.id` |
| `node_path` | string | derived: `"cl-cluster-" + str(cl_cluster_id)` (Phase-3 upsert key) |
| `docket_id` | int | `search_opinioncluster.docket_id` (join key to `dockets.jsonl`) |
| `court_id` | string | docket's `court_id` (`"iowa"`/`"iowactapp"`; interned literal) |
| `court_name` | string | `search_court.full_name` via `court_name_by_id` |
| `case_name` | string | `search_opinioncluster.case_name` (→ Node `heading`, §7) |
| `case_name_short` | string | `search_opinioncluster.case_name_short` |
| `case_name_full` | string | `search_opinioncluster.case_name_full` |
| `date_filed` | string (ISO `YYYY-MM-DD`) | `search_opinioncluster.date_filed` (NOT NULL; → `effective_from`, §7) |
| `precedential_status` | string | `search_opinioncluster.precedential_status` (verbatim) |
| `judges` | string | `search_opinioncluster.judges` |
| `citation_count` | int | `search_opinioncluster.citation_count` |
| `scdb_id` | string | `search_opinioncluster.scdb_id` |
| `slug` | string | `search_opinioncluster.slug` (for `official_url_template`) |
| `syllabus` | string | `search_opinioncluster.syllabus` |
| `headnotes` | string | `search_opinioncluster.headnotes` |
| `summary` | string | `search_opinioncluster.summary` |
| `disposition` | string | `search_opinioncluster.disposition` |
| `posture` | string | `search_opinioncluster.posture` |
| `nature_of_suit` | string | `search_opinioncluster.nature_of_suit` |

(`docket_number` is **not** on this record — recovered in Phase 2 via `dockets.jsonl`, §5.4.)

### 5.2 `opinions.jsonl` — opinion record (one per `search_opinion`, 1..n per cluster)
| JSONL field | Type | Source column |
|---|---|---|
| `cl_opinion_id` | int | `search_opinion.id` |
| `cl_cluster_id` | int | `search_opinion.cluster_id` (parent link) |
| `node_path` | string | derived: `"cl-cluster-" + cluster + "/op-" + opinion` (Phase-3 upsert key) |
| `type` | string | `search_opinion.type` (e.g. `010combined`, `020lead`, `030concurrence`, `040dissent`; source label `015unamimous` is misspelled in CL data) |
| `author_str` | string | `search_opinion.author_str` |
| `author_id` | int \| null | `search_opinion.author_id` (nullable FK; `'' -> null`) |
| `per_curiam` | bool | `search_opinion.per_curiam` |
| `joined_by_str` | string | `search_opinion.joined_by_str` |
| `page_count` | int \| null | `search_opinion.page_count` (nullable; `'' -> null`) |
| `download_url` | string | `search_opinion.download_url` |
| `extracted_by_ocr` | bool | `search_opinion.extracted_by_ocr` |
| `sha1` | string | `search_opinion.sha1` |
| `plain_text` | string | `search_opinion.plain_text` |
| `html` | string | `search_opinion.html` |
| `html_lawbox` | string | `search_opinion.html_lawbox` |
| `html_columbia` | string | `search_opinion.html_columbia` |
| `html_anon_2020` | string | `search_opinion.html_anon_2020` |
| `xml_harvard` | string | `search_opinion.xml_harvard` |
| `html_with_citations` | string | `search_opinion.html_with_citations` |

(Text columns carried verbatim; Phase 2 applies the §4 preference chain and tag-stripping. Booleans: CL exports `t`/`f`/`true`/`false`; `csv_stream` normalizes to Python `bool`.)

### 5.3 `citations.jsonl` — citation record (one per `search_citation`, attaches to cluster)
| JSONL field | Type | Source column |
|---|---|---|
| `cl_citation_id` | int | `search_citation.id` |
| `cl_cluster_id` | int | `search_citation.cluster_id` (parent link; cites attach to cluster) |
| `volume` | string | `search_citation.volume` |
| `reporter` | string | `search_citation.reporter` (e.g. `N.W.2d`) |
| `page` | string | `search_citation.page` |
| `type` | int | `search_citation.type` (1 Federal, 2 State, 3 State regional, 4 Specialty, 5 Scotus early, 6 Lexis, 7 West, 8 Neutral, 9 Journal) |

Phase 2 builds the display string `"{volume} {reporter} {page}"` (e.g. `987 N.W.2d 123`) and groups parallel cites by `cl_cluster_id` into decision `source_metadata.citations[]`.

### 5.4 `dockets.jsonl` — Iowa docket record (one per Iowa `search_docket`, emitted in pass 2)
| JSONL field | Type | Source column |
|---|---|---|
| `docket_id` | int | `search_docket.id` (join key from `clusters.jsonl.docket_id`) |
| `court_id` | string | `search_docket.court_id` (`"iowa"`/`"iowactapp"`) |
| `docket_number` | string | `search_docket.docket_number` (may be `""`) |

---

## 6. `RawIngestion` audit records written in Phase 1

`RawIngestion` mirrors `ingestion_iowa_code/models.py` (field list verified exact against the real model) with caselaw `SOURCE_KIND_CHOICES`:

```
SOURCE_KIND_CHOICES = [
  ("cl_bulk_clusters",  "CourtListener bulk opinion-clusters CSV"),
  ("cl_bulk_opinions",  "CourtListener bulk opinions CSV"),
  ("cl_bulk_citations", "CourtListener bulk citations CSV"),
  ("cl_bulk_dockets",   "CourtListener bulk dockets CSV"),
]
```
Fields unchanged: `source_kind` (CharField/32, choices), `code_year` (PositiveIntegerField — **reused to store the bulk export year**, e.g. `2026`), `fetched_at` (auto), `fetched_from` (CharField/500 — source S3 URL of the bulk file), `content_hash` (CharField/64, **unique** — dedupe), `byte_size` (PositiveBigIntegerField), `storage_path` (CharField/500), `notes` (TextField).

**One `RawIngestion` row per emitted JSONL artifact** (`clusters.jsonl`, `opinions.jsonl`, `citations.jsonl`, `dockets.jsonl`), written via a **new streaming-hash helper** (see below):
- `content_hash` = **SHA-256 of the produced JSONL artifact bytes**. This is what Phase 2/3 consume, giving a meaningful audit key and letting a re-run detect "same slice already produced."
- `storage_path` = absolute path of the artifact (`<storage_dir>/<content_hash>.bin` per the existing convention; the human-named `*.jsonl` files in the run dir are operator-convenience copies/symlinks).
- `byte_size` = artifact length; `fetched_from` = originating bulk-file S3 URL; `notes` = run id + court ids + record count.

**Must add a streaming-hash variant.** The shared `persist_raw_input(payload_bytes: bytes, ...)` hashes via `hashlib.sha256(payload_bytes)` — it requires the **entire artifact in memory**. The opinions JSONL is ~2–4 GB; loading it into a `bytes` violates the §3 "never accumulate" rule and the RAM budget. Phase 1 therefore adds `persist_raw_input_from_path(*, path, source_kind, code_year, fetched_from, storage_dir, notes)` that hashes the file in chunks (e.g. 1 MiB reads), keeping the existing `<content_hash>.bin` storage and dedupe-returns-existing-row behavior. `persist_raw_input` keeps its `bytes` signature for the small artifacts; the opinions artifact uses the streaming variant.

**Idempotency caveat (do not oversell):** this dedupe is **content-addressed**, a weaker guarantee than "rerunning the same quarter is a no-op." Identical input → identical artifact bytes → same `content_hash` → short-circuit. But a corrected re-download of the *same* quarter that differs by even one byte (a new opinion, a reordered COPY) yields a *new* `content_hash` and a new row. That is correct, acceptable behavior; describe it as content-addressed, not as unconditional quarter-level idempotency.

---

## 7. Resumability / crash-safety

### Phase 1 (this spec): read-only + atomic artifacts
- Touches **no corpus tables.** Builds integer key-sets in RAM, streams CSV→JSONL.
- Each artifact is written to a temp file (`<name>.jsonl.partial`) and **`os.replace`-renamed** to its final name only after the producing pass completes. A consumer never sees a half-written file; a crash leaves a `.partial` the next run overwrites. (`os.replace` is atomic on POSIX same-filesystem.)
- Re-run from scratch is fully **idempotent**: identical input re-derives identical key-sets and re-emits byte-identical JSONL (pinned serialization §5 + forward-scan order); `RawIngestion` content-hash dedupe short-circuits.

### `--resume` must rebuild key-sets, only skip artifact *writes*
The integer key-sets are **in-memory only** and are dependencies of later passes (`iowa_docket_ids` built in pass 2 feeds pass 3; `iowa_cluster_ids` built in pass 3 feeds pass 5). A naive `--resume` that skips a finalized pass entirely would leave the dependent set **empty**, silently producing a **truncated `opinions.jsonl`** (zero opinions). Therefore:
- `--resume` **always executes the set-building portion of every prior pass** (the cheap streaming scan that fills `iowa_docket_ids`/`iowa_cluster_ids`), and skips only the *artifact write* for already-finalized artifacts. Equivalently, persist the two key-sets to disk and reload them on resume.
- `--resume` is a **time optimization only**; re-running from scratch is always correct. Each artifact is independently atomic, but the four artifacts are **not** a committed set — `--resume` correctness depends entirely on the unconditional set rebuild above.

### `IngestionRun` checkpoint fields
`IngestionRun` mirrors `ingestion_iowa_code/models.py` (`raw` FK PROTECT, `started_at`, `finished_at`, `status` ∈ {pending, approved, rejected, failed}, `nodes_added/amended/repealed/unchanged`, `validation_errors` JSONField, `log` TextField) **plus two checkpoint fields added for caselaw:**

```
phase            = CharField(max_length=16, choices=[("acquire","Acquire"),("write","Write")])
last_cluster_id  = PositiveBigIntegerField(null=True, blank=True)   # high-water mark, logging only
```

- Phase 1 writes one `IngestionRun` (`phase="acquire"`) on completion. **`status` stays `"pending"` on success** (true mirror of `apply_changeset`, which writes `status="pending"` because approval is a human admin gate; `writer.py:144`); set `"failed"` on exception. The acquire run's `status` is the review-workflow gate and is **independent of** `NodeVersion.review_status` (the auto-approve below). `log` = JSON `{clusters, opinions, citations, dockets, rejects}` counts.
- Phase 3 writes one `IngestionRun` **per batch** (`phase="write"`), created **inside the same `@transaction.atomic` block as that batch's NodeVersion inserts** (mirrors the Iowa Code writer), so the run row is durable iff the batch commits. `nodes_repealed` is hardcoded `0` for caselaw (cases are immutable; the differ has no `decisions_repealed`). `last_cluster_id` records the batch's max `cl_cluster_id` for progress logging only — see resume rule below.

### Phase 3 crash-safety (interface defined here so the Phase-1 schema supports it)
- **The atomic unit is the whole decision.** A batch is a set of **complete decisions** (~100–500), and each decision's cluster Node + all its opinion child Nodes + all their NodeVersions commit in **one** `@transaction.atomic` block — never a partial decision. A crash thus leaves whole decisions present or absent, never a decision missing an expected opinion (which would be indistinguishable from a legitimate 0-opinion container, §8).
- **Required schema change for DB-enforced idempotency.** Add `UniqueConstraint(fields=("node","content_hash"), name="uniq_nodeversion_per_node_hash")` to `NodeVersion` (it currently has none; `models.py:92–114`). This turns the "no-op on rerun" from a trust-the-app read-then-write into a DB invariant: a double-insert raises `IntegrityError` instead of silently creating a duplicate open version that pollutes `effective_to IS NULL` lookups forever (and would double-embed in Phase 4). Flagged as the one corpus-schema change in this plan.
- **Upsert keys:** decision Node `get_or_create(source, path="cl-cluster-<id>")`; opinion Node `get_or_create(source, path="cl-cluster-<id>/op-<opinion_id>")` (both on the DB-unique `(source, path)`, `models.py:78`). `NodeVersion` is created **only when `content_hash` differs** from the open version (`effective_to IS NULL`), backstopped by the new unique constraint.
- **Heading must be set on the Node before its NodeVersion is inserted.** The `corpus_nodeversion_search_vector` trigger fires `BEFORE INSERT` and reads `heading` from `corpus_node` (weight A) at insert time (migration `0005`). Phase 3 must `get_or_create`/update and `save` the Node `heading` (= `case_name` for the decision Node; an opinion-appropriate heading for opinion Nodes) **before** inserting that node's NodeVersion, or case-name search silently misses. A later `case_name` edit only refreshes FTS via the separate `corpus_node_heading_cascade` AFTER-UPDATE trigger, and only when `heading` actually changes.
- **NodeVersion field contract (all NOT-NULL fields set):** `body_text` = chosen opinion text (Phase 2) — preserved verbatim so Phase 4 needs no re-acquire; `effective_from = date_filed` (NOT NULL `DateField`; deterministic per cluster so reruns produce identical versions — never ingest-day, which would break point-in-time/Edition logic); `effective_to = NULL` always (cases are immutable; opinions never close); `enacted_by = ""` (TextField blank; no statutory enactment for caselaw); `content_hash` per the differ; `embedding_source_hash = ""` (gates Phase 4); `review_status = ReviewStatus.APPROVED` (`"approved"`, locked mapping — auto-approve bulk public caselaw; **differs from the Iowa Code writer's `PENDING`**).
- **`ordinal` (NOT-NULL `CharField`, no blank):** opinion Node `ordinal` = the `type` numeric prefix as a **string** (e.g. `"020"`), ordering lead-first; decision Node `ordinal` = `str(cl_cluster_id)` (stable, non-empty).
- **`search_vector`** is populated by the Postgres trigger on insert — **no app code** sets it; FTS is live the instant a batch commits (given the heading-first ordering above).
- **Resume relies on the differ, never on a high-water fast-forward.** Always run the full (read-only, cheap) diff pass; the differ skips already-present rows by `path` + open-version `content_hash`, which is **order-independent and idempotent regardless of `cl_cluster_id` ordering**. CL ids are not monotonic with filing date and batches are not id-sorted, so a scalar `last_cluster_id` "fast-forward" could skip rolled-back lower-id clusters and cause **silent data loss** — do not gate which clusters are considered on it. If the diff is ever too slow, gate on per-Node existence (`Node.objects.filter(source, path__in=batch_paths)`), correct regardless of ordering. `last_cluster_id` is for progress logging only.

---

## 8. Edge cases + risks

| Case | Handling |
|---|---|
| **Doubled-quote / backslash content** | Dialect is `doublequote=True, escapechar=None` (§3, verified 3193 `""` vs 1 `\"`). The wrong dialect would corrupt join keys, not just text. Per-row `len(row)==len(header)` assertion is the guardrail. |
| **Multiline quoted fields** | The core reason line-splitting tools are banned (§3); handled only by quote-state-tracking `csv` + `newline=''`. |
| **Bare `\r` in a quoted field** | `newline=''` on the `TextIOWrapper` keeps it inside the field instead of splitting the record. Tested. |
| **Oversized field** | `csv.field_size_limit(sys.maxsize)` set inside `open_bulk_csv` before reading; tested with a >131072-byte field. |
| **Nullable numeric `''`** | `author_id`/`page_count` coerced `'' -> None` → JSON `null` (§3); tested. |
| **Decode error mid-50 GB** | Strict UTF-8, but row-level catch → `rejects.jsonl` sidecar + continue (§3), so one poison row does not abort the pass or block resume. |
| **OCR-only text** (`extracted_by_ocr=true`) | Not filtered; carried verbatim; flag stored in opinion `source_metadata` for Phase 2/retrieval to label/deprioritize. The §4 chain prefers richer fields, so OCR text is used only when it is the sole non-empty column. |
| **All text columns empty** | Phase 2 yields `body_text=""`; Phase 3 creates the opinion Node (container) but **skips the empty `NodeVersion`** (nothing to embed/search). Logged as a skipped opinion. |
| **Cluster with 0 opinions** | Decision Node created as a pure **container** (no children, no `NodeVersion`) — valid per the 2-level model. Indistinguishable from a lost-opinion cluster *only if* batching split a decision — which §7's whole-decision atomic unit forbids. |
| **Cluster with N opinions** | N opinion child Nodes, each its own `NodeVersion`; `ordinal` orders lead-first by `type` prefix. |
| **Decision-level `NodeVersion`** (locked decision 3) | Create **one** decision-level `NodeVersion` (on the decision Node) holding concatenated `syllabus`/`headnotes`/`summary` **only when at least one is non-empty** (heading set first, §7); else the decision Node stays a pure container. Phase 1 carries the three fields through; the conditional is Phase 3. |
| **`N.W.2d` regional reporter** | Iowa opinions cite the regional reporter `N.W.2d` (`type=3`), not a state reporter. Display `"{volume} N.W.2d {page}"`; store all parallel cites. |
| **Memory blow-up** | Only the two integer key-sets are retained (tens of MB even at millions of ids). The docket-field join is on disk via `dockets.jsonl`, never a dict-of-strings. The 50 GB opinions stream is strictly one row at a time. **Never** build a list of rows or a per-docket string dict. |
| **Disk pressure** | 57 GB compressed sources + ~2–4 GB JSONL fits 74 GB. Delete `opinions.csv.bz2` after the opinions pass if tight; the JSONL slice is the durable artifact. |

---

## 9. Operator runbook

**Prereqs:** dev droplet (PG18 clone); Voyage key not needed for Phase 1–3; `apps.ingestion_caselaw` migrated; the `NodeVersion` unique-constraint migration applied (§7); `Source iowa-caselaw` + the two `NodeType`s bootstrapped (§2).

**Management command (Phase 1):** `acquire_iowa_caselaw`
```
python manage.py acquire_iowa_caselaw \
    --bulk-dir   "/home/dev/statutes/Case Law/bulk-2026-03-31" \
    --out-dir    "/home/dev/statutes/Case Law/iowa-slice-2026-03-31" \
    --export-year 2026 \
    [--court iowa --court iowactapp]   # default both
    [--source-url-base https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data] \
    [--resume]                          # rebuilds key-sets, skips only finalized artifact writes
    [--stream-from-url]                 # non-default: stream .bz2 from S3 instead of local
```

**End-to-end flow:**
```
# 0. Confirm disk
df -h /home/dev/statutes            # need ~60 GB free

# 1. Download the five quarterly bulk .csv.bz2 to --bulk-dir (NOT decompressed):
#    courts, dockets, opinion-clusters, citations, opinions (CL bulk-data S3 bucket).

# 2. Run Phase 1 acquire (streams local .bz2 -> JSONL; read-only on corpus DB)
python manage.py acquire_iowa_caselaw --bulk-dir <dir> --out-dir <out> --export-year 2026
#   -> writes clusters.jsonl, opinions.jsonl, citations.jsonl, dockets.jsonl
#      (+ rejects.jsonl if any) + 4 RawIngestion rows

# 3. Phase 2+3: parse + write the slice in idempotent per-batch (whole-decision) transactions
python manage.py ingest_iowa_caselaw --in-dir <out> [--batch-size 200] [--dry-run]

# 4. (later) Phase 4 embedding pass — separate, deferred (§10)
```

**Resume after a crash:**
- Phase 1 crash: re-run the identical command (add `--resume` to skip finalized artifact writes; it still rebuilds the in-memory key-sets, §7). Read-only and deterministic; content-hash dedupe makes a full re-run cheap at the audit layer.
- Phase 3 crash: re-run `ingest_iowa_caselaw --in-dir <out>`; committed whole-decision batches persist, and the differ skips them by `path`+`content_hash` (order-independent). `last_cluster_id` is logging only and never gates which clusters are reconsidered.

**Rough estimates (Iowa slice, 2 cores / ~4 GB available):**
- Download 57 GB compressed: network-bound (tens of minutes to a few hours).
- bz2 decompress + CSV parse is single-threaded: dockets 4.6 GB ≈ several minutes; clusters 2.3 GB ≈ minutes; citations 120 MB ≈ seconds; **opinions 50 GB is the dominant cost, on the order of 1–3 hours**. Whole Phase 1: a few hours.
- Output JSONL: ~2–4 GB total.
- Phase 3 write: per-batch commits, bounded by Postgres insert throughput on the Iowa-sized row count — tens of minutes.

---

## 10. Handoff to Phase 4 (deferred chunked Voyage embedding)

Phase 4 is **deferred and independent** (locked decision 4). At the end of Phase 3 every Iowa opinion is **fully usable with no embeddings**: `NodeVersion.body_text` holds the chosen text, the Postgres trigger has populated `search_vector` (FTS live), and all metadata/citations are queryable. **`body_text` is preserved verbatim on every `NodeVersion`, so Phase 4 needs no re-ingest and no re-acquire** — it reads existing rows only.

Phase 4 contract (not built here):
- Runs later via the **shared `Chunk` model** (rules + cases workstream). Opinions **fan out into chunk rows**; each chunk is embedded with **Voyage Law 2, 1024-dim** (`VOYAGE_LAW_2 = "voyage-law-2"`, `EMBEDDING_DIM = 1024`, matching `NodeVersion.embedding = VectorField(dimensions=1024)`, `INPUT_TYPE_DOCUMENT`). **Do not ship a single vector per opinion.**
- Reuses the existing embedding driver contract: a row needs (re)embedding when `content_hash != embedding_source_hash` (the `pending_versions()`/`_process_batch` pattern, `batch_size=64`), applied at chunk grain once `Chunk` exists. Since `embedding_source_hash=""` on a new version and a Phase-3 rerun that no-ops on `content_hash` creates **no** new version (enforced by §7's unique constraint), there is no re-embedding storm and no duplicate-embedding cost.
- CourtListener's own 768-dim ModernBERT vectors are **not reused** — incompatible with the fixed `VectorField(1024)`.
- Independently runnable/resumable; vector/semantic search lights up only after this pass, with zero impact on the already-searchable, already-citable corpus from Phases 1–3.

**Files referenced (all absolute):** new app `/home/dev/statutes/backend/apps/ingestion_caselaw/` (to be created, mirroring `/home/dev/statutes/backend/apps/ingestion_iowa_code/`); corpus models `/home/dev/statutes/backend/apps/corpus/models.py` (`Node` unique `(source,path)` at :78; `NodeVersion` :92–114 has no unique constraint — add per §7); search trigger `/home/dev/statutes/backend/apps/corpus/migrations/0005_search_indexes.py`; writer `/home/dev/statutes/backend/apps/ingestion_iowa_code/writer.py` (`get_iowa_code_source` :36, `persist_raw_input` :42); differ `/home/dev/statutes/backend/apps/ingestion_iowa_code/differ.py` (open-version query :86–90); embedding driver `/home/dev/statutes/backend/apps/corpus/services/embeddings.py`; existing plan `/home/dev/statutes/Case Law/CASELAW_INGESTION_PLAN.md`; sample bulk file `/home/dev/statutes/Case Law/courts-2026-03-31.csv.bz2`.
