# Verify Document — Design & Build Plan

A new **Verify Document** feature: a user uploads (or pastes) a legal document, runs the
"verify citations" tool, and gets back every citation in the document with a
🟢 / 🟡 / 🔴 status — checking both that the **citation format is correct** and that the
**language around the citation matches the actual source** (i.e. accurate, not fabricated).

The existing chat "progress module" UI is reused, but in a **citation checklist** mode:
instead of sequential steps, it lists every citation with a status chip and an
expandable diff of *claimed language vs. real source text*.

## Decisions (locked)

- **Accuracy depth:** verbatim match **+ LLM semantic** check. Quotes are matched
  deterministically; paraphrased claims near a citation are checked by an LLM
  ("is this supported / partial / contradicted by the source?").
- **Input formats:** document **upload (PDF/DOCX via docling) AND paste text**.
- **Corpus scope:** verify against **all loaded sources** (Iowa Code + Iowa Court Rules),
  like the existing chat verification gate.

## What we reuse (already in the codebase)

| Capability | Location | Gives us |
|---|---|---|
| Citation extraction w/ char spans | `backend/apps/citations/parser.py` → `find_all()` | every citation substring + offsets |
| Format check + resolution | `backend/apps/corpus/services/lookups.py` → `validate_citations()` | per-cite `valid`/`repealed`/`not_found`/`parse_error` |
| Source text by citation | `lookups.py` → `lookup_citation()` | `Node.heading` + current `NodeVersion.body_text` |
| Quote-vs-source matching | `lookups.py` → `verify_quotes()` / `_match_quote_against_body()` | `exact` / `fuzzy` (SequenceMatcher ≥0.85) + `closest_passage` |
| Combined gate logic | `backend/apps/api/chat.py` → `_verify_answer()` | the green/red decision logic + multi-source `_STATUS_RANK` rollup |
| Progress module | `chat-frontend/.../progress-tracker/` + NDJSON stream | step list w/ status chips |
| LLM call pattern | `backend/apps/corpus/services/query_expansion.py` (`anthropic.Anthropic`, Haiku) | template for the semantic support check |

**Genuinely new:** file upload + text extraction, inverting quote→citation pairing into a
**citation→language rollup**, the semantic support check, and a checklist variant of the
progress tracker.

## Pipeline

```
Upload/paste ─► extract text (docling for PDF/DOCX; pass-through for paste)
            ─► find_all() → citations + spans
            ─► per citation (streamed as each finishes):
                  1. FORMAT   parse() ............. unparseable → RED
                  2. RESOLVE  resolve() ........... not_found → RED · repealed → YELLOW
                  3. LANGUAGE gather text in a window around the cite:
                       • quoted spans → exact/near-verbatim vs body_text
                       • unquoted claims → LLM "supported by source?" check
                  4. ROLL UP to one status (worst-wins)
            ─► stream each result to the checklist UI
            ─► persist a VerificationRun trace
```

### Status rollup (worst-wins)

- 🟢 **Green** — format correct, resolves to current section, **all** attributed language
  matches the source verbatim/near-verbatim (and, if checked, LLM says supported).
- 🟡 **Yellow** — resolves but: repealed/superseded, OR language is a *paraphrase*
  (fuzzy match, not verbatim), OR nonstandard-but-resolvable format, OR LLM
  "partial / could not fully verify", OR parses but belongs to no loaded source (out of scope).
- 🔴 **Red** — unparseable format, citation not in any loaded corpus, a quoted passage
  attributed to it is **not found** in the source (fabricated), or LLM says the source
  **contradicts** the claim.

## Data shapes

```
CitationFinding:
  raw: str                  # "Iowa Ct. R. 32:1.7"
  span: (int, int)
  status: "green" | "yellow" | "red"
  format_ok: bool
  resolution: "valid" | "repealed" | "not_found" | "parse_error"
  source_label: str | None
  language_checks: [LanguageCheck]
  detail: str               # human-readable reason

LanguageCheck:
  claim_text: str           # quoted span OR sentence(s) around the cite
  kind: "quote" | "paraphrase"
  verdict: "exact" | "fuzzy" | "supported" | "partial" | "contradicted" | "not_found"
  match_score: float        # 0..1 where applicable
  source_excerpt: str       # closest_passage from body_text
```

## Build phases

### Phase 1 — Backend core service (no UI)
- **1.1** `backend/apps/api/services/extract.py` — `extract_text()` (docling for PDF/DOCX,
  pass-through for paste). Preserve char offsets so spans line up.
- **1.2** `backend/apps/corpus/services/verify_document.py` — `verify_document(text, *, sources=None)`
  returning `DocumentReport([CitationFinding])`. Inverts `verify_quotes()` pairing:
  iterate citations, gather quoted spans within `_QUOTE_CITATION_WINDOW` + adjacent sentences,
  resolve once via `lookup_citation()`, run quotes through `_match_quote_against_body()` and
  paraphrases through the semantic checker. Multi-source via `_STATUS_RANK` best-across-sources.
- **1.3** `backend/apps/corpus/services/semantic_support.py` — mirror `AnthropicExpander`;
  strict-JSON verdict `{verdict, evidence_span}`; batch per citation; graceful fallback to
  yellow "could not verify" when no `ANTHROPIC_API_KEY`.
- **1.4** Rollup function (worst-wins) + thorough unit tests.

### Phase 2 — Streaming endpoint + trace
- **2.1** `backend/apps/api/verify.py` — `POST /api/verify/document` (multipart or JSON),
  `application/x-ndjson` like `chat_stream`. Generator yields:
  `extract_done` → `citation_start` / `citation_done` (per cite) → `summary` → `done`.
- **2.2** `VerificationRun` model + migration (mirror `ChatTrace`): doc hash/name, extracted
  text, findings JSON, counts, latency; `record_verification_run()` in a `finally`.

### Phase 3 — Frontend
- **3.1** `/verify` route: dropzone (PDF/DOCX) + paste textarea; generic `streamNDJSON()`
  helper factored from `lib/iowa-chat.ts`.
- **3.2** Progress tracker **checklist mode**: schema variant with `status: green|yellow|red`
  + expandable body (claimed language vs. `source_excerpt` diff). Stable `toolCallId: "iowa-verify"`.
- **3.3** Summary header: "12 citations · 8 🟢 · 3 🟡 · 1 🔴".

### Phase 4 — Polish
- Golden-document tests (clean / fabricated quote / paraphrase / repealed / malformed).
- Reuse chat quota/rate-limit (`_enforce_chat_quota`).

## Suggested build order
1. Phase 1.2 + 1.4 against pasted text (no upload, no LLM) — proves the rollup.
2. Add 1.3 semantic layer.
3. Phase 2 streaming endpoint.
4. Phase 3 UI.
5. Phase 1.1 docling upload extraction last (most isolated).

## Two-step check (form + substance)

Each citation is now graded on two independent axes:

1. **Form (Step 1, deterministic — `corpus/services/citation_format.py`)** — renders
   the canonical Iowa citation (source/chapter-aware: `Iowa R. Civ. P. 1.305(1)`,
   `Iowa Code § 714.16`), and per cite returns a `FormResult`:
   `ok` (proper) / `corrected` (resolves but mis-styled → shows the right form) /
   `unresolvable` (no match — offers a typo near-match, e.g. `1.9042` → "did you
   mean `Iowa R. Civ. P. 1.904(2)`?"). Shown as a **separate Form indicator** in
   the checklist, distinct from the accuracy light. Scope is "canonical Iowa form,"
   NOT full Bluebook (year parentheticals/signals/short-forms deferred). Known
   limits: the parser's sigil regex doesn't recognize truly nonstandard prefixes
   (`IA.`, `IRCP`) so it can't echo them as the written form, and it drops a
   malformed trailing subdivision (`6.101(1)b`) — both are Bluebook-phase work.
2. **Substance (Step 2)** — the verbatim + semantic language check (green/yellow/red).

## Build status (updated)

- ✅ **Phase 1** — `corpus/services/verify_document.py` (`verify_document` +
  streaming `iter_verify_document`). Citation-centric, multi-source, worst-wins
  rollup. 14 unit tests green.
- ✅ **Phase 1.3** — `corpus/services/semantic_support.py` (OpenAI `gpt-4o-mini`
  via `settings.OPENAI_API_KEY` + JSON mode — the app is OpenAI-based, no
  Anthropic key. Strict-JSON
  verdicts, graceful no-key fallback). Wired into the rollup; fake-checker tests.
- ✅ **Phase 2** — `api/verify.py` `POST /api/verify/document` (multipart,
  NDJSON: `start` → `citation_done` → `summary` → `done`). `VerificationRun`
  model + migration `0003`, `record_verification_run`, read-only superuser
  admin. 4 endpoint tests green. Full suite: 106 passing.
- ✅ **Phase 3** — frontend `/verify` route. Paste box + file dropzone,
  `lib/iowa-verify.ts` (`streamVerify` NDJSON client + types),
  `components/tool-ui/citation-checklist/` (the green/yellow/red checklist with
  expandable claim-vs-source detail), "Verify Document" link in the chat header.
  `next build` clean; `/verify` route prerenders.
- ✅ **Phase 1.1** — docling PDF/DOCX extraction, as a **separate App Platform
  service** (`docling-service/`: FastAPI + uvicorn, `POST /extract` taking raw
  bytes + `X-Filename`, model weights baked into the image at build via
  `docling-tools models download`). Kept out of the Django image on purpose —
  docling drags in PyTorch + layout models (~2-3 GB). `api/services/extract.py`
  `_extract_richdoc` POSTs uploads to `DOCLING_SERVICE_URL` over stdlib
  `urllib` (no new backend dep) and maps every failure (no service, 4xx, 5xx,
  unreachable, empty result) to a friendly `ExtractionError`. `.do/app.yaml`
  adds the `docling` **internal** service (`internal_ports`, no ingress, health
  check on `/health`) and binds `DOCLING_SERVICE_URL=${docling.PRIVATE_URL}` on
  the Django service. OCR + table-structure off by default (lean/fast; flip
  `DOCLING_OCR=1` for scans). 9 extract unit tests (mocked `urlopen`); full
  suite 258 passing.

Usable end to end now for pasted text / .txt uploads in any environment; PDF
and DOCX upload light up wherever the docling service is reachable
(`DOCLING_SERVICE_URL` set) — paste or upload a brief, watch each citation fill
in green / yellow / red live.

**Frontend style note:** the repo is committed with 2-space indentation even
though `biome` defaults to tabs (no `biome.json` overriding it), so `biome
check` already flags formatting on every existing file. New frontend files
follow the prevailing 2-space style to match their neighbors — do NOT run
`biome check --write`, which retabs the whole repo.

## Risks
- **Paraphrase boundary detection** — start with "sentence containing the cite + preceding
  sentence", then tune.
- **LLM subjectivity** — keep the prompt strict; always surface the source excerpt so the
  color is auditable, never a black box.
- **Offset integrity** through docling extraction — verify early so highlights land right.
