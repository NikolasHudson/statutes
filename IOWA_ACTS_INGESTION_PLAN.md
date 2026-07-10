# Iowa Acts (Session Laws) + Constitutions — Ingestion Plan

_Created 2026-07-10. Owner: Nick. Status: researched (all URL patterns below fetched and
verified today unless tagged UNVERIFIED), ready for parser spike. Follows the IAC plan
format; the freshest implementation to mirror is `backend/apps/ingestion_iowa_admin_code/`._

## Why

Iowa Acts are the **current-awareness backbone**: every act section states which Iowa Code
section it amends/repeals/creates, months before the next Code edition is published. That
is exactly the fuel the supersession pipeline (CITATOR_SUPERSESSION_PLAN.md) needs — a
**bill→Code-section edge set with action type and effective date**, published by the
legislature itself. Secondary wins: citation resolution for `2024 Iowa Acts, ch. 1170`
cites (which appear constantly in caselaw and Code history lines), and corpus breadth vs.
LexIowa. The Iowa/US Constitutions ride along as a near-free add-on.

## What Iowa Acts are (verified 2026-07-10 against legis.iowa.gov)

- The annual compilation of everything enacted by a session of the General Assembly,
  organized **Session → Chapter (one chapter = one enrolled bill) → Section**. Published
  each autumn; the chapter text is the enrolled bill text reprinted with a chapter number.
- **Chapter numbering**: first (odd-year) session of a GA numbers chapters from 1
  (`CH0001…`); second (even-year) session numbers from 1001 (`CH1001…`). Verified counts:
  2020 = 122, 2023 = 168, 2024 = 187 (1001–1187), 2025 = 170, 2026 = 201 (1001–1201).
- **Citation form** (Iowa Code § 3.3): `2024 Iowa Acts, ch. 1170, §12`.
- **Acts are frozen documents** — unlike Code/IAC they are never amended after
  publication. One NodeVersion per section, forever open. No update job needed beyond a
  once-a-session ingest (plus mid-session ingest of newly signed chapters if we want
  edges before the autumn compilation — the sections-amended table updates continuously).

### Data source & URL patterns (all fetched, HTTP 200)

| What | URL |
|---|---|
| Acts landing | `/law/statutory/acts` |
| Chapter list per session | `/law/statutory/acts/actsChapter?ssid={ssid}` |
| Chapter PDF (official, canonical path) | `/docs/publications/iactc/{ga}.{session}/CH{nnnn}.pdf` |
| Chapter PDF (year alias, 302 → above) | `/docs/acts/{year}/CH{nnnn}.pdf` |
| Enrolled bill RTF (**the parse target**) | `/docs/publications/LGE/{ga}/attachments/{BILL}.rtf` |
| Enrolled bill HTML (print rendering) | `/docs/publications/LGE/{ga}/attachments/{BILL}.html?layout=false` |
| Enrolled bill PDF | `/docs/publications/LGE/{ga}/{BILL}.pdf` |
| Governor's letter | `/docs/publications/LGE/{ga}/Attachments/{BILL}_GovLetter.pdf` |
| Whole-session volume PDF | `/docs/publications/iactc/90.2/2024_Iowa_Acts.pdf` (913 pp, 6.0 MB) |
| **Code & Acts Sections Amended (edge table)** | `/law/statutory/acts/amended?ga={ga}&session={1,2}` |

- `ssid` is a session id enumerable from the dropdown embedded in any `actsChapter` page
  (`<option … ssid=166>General Assembly: 90 (2024 Regular GA)`). Recent values: 2026=168,
  2025=167, 2024=166, 2023=165 (+2023 Extra=187), 2022=164, 2021=163 (+Extra 185/186),
  2020=162. The dropdown goes back to **ssid=1 (1839) / 1838 territorial** — full history
  is enumerable from one page.
- The `actsChapter` listing row gives everything the scraper needs per chapter: chapter
  PDF link, **bill number** (`BillBook?ba=HF2485&ga=90`), governor-letter link, and title.
  `CH{nnnn}` is zero-padded to 4 digits in both PDF paths.
- **Enrolled RTF availability**: verified present for GA 90 (2024: all 187 bills, 0
  404s, 13.45 MB total) and spot-verified back to **GA 83 (2009)**; GA 80 (2003) 404s.
  Exact boundary between GA 80–83 UNVERIFIED. Pre-boundary sessions: chapter **PDF only**
  (verified 200 back to 1965 `61.1/CH0001.pdf`; pre-1965 quality UNVERIFIED, likely scans
  for the oldest decades).

### ⚠ Load-bearing format gotchas (all measured)

1. **The enrolled `.rtf` is genuine RTF** (Arbortext `CDocsPublishRtf`, `file` says "Rich
   Text Format data, version 1") — the opposite of the IAC gotcha where `.rtf` was DOCX.
   `striprtf` (already a dependency, used by `ingestion_iowa_code`) extracts it cleanly…
2. **…but `striprtf` is superlinearly slow**: measured 39 KB → 0.18 s, 262 KB → 38.9 s,
   552 KB → >110 s (timeout), 1.38 MB (SF 2385, the boards omnibus) → **killed after
   18 min**. Per session only ~13 bills are >150 KB and 6 >300 KB, but those are exactly
   the omnibus bills we care about. → Write a **small custom linear RTF tokenizer**
   (state machine over `{}\` groups, ~100 lines), which we need anyway because…
3. **Stricken text pollution.** Amendatory sections reprint the amended Code text showing
   the change: deleted words carry `\strike` runs, added words `\ul` runs (SF 2385: 6,382
   strike-on runs, 2,923 ul-on). Both **naive striprtf output and the official PDF text
   layer include stricken (repealed) words inline with no marker** — e.g. CH1170's text
   reads "…appointed by the secretary from a list of names of persons recommended by…"
   where "from a list of names of persons recommended by" is actually struck. Only the
   RTF control words let us recover old-vs-new. The parser must be **strike/ul-aware**:
   emit clean "resulting law" text (drop `\strike`, keep `\ul`) for `body_text`/embedding,
   and preserve del/ins runs in `body_segments` for faithful display.
4. The enrolled **HTML** is a print rendering of absolutely-positioned word spans (group
   by `top` px / order by `left` px reconstructs lines; parses SF 2385 in 0.4 s) but
   strikethrough appears to be drawn as separate 1 px line elements (`span.l`) —
   recovering del/ins from it is fragile (UNVERIFIED). Use it only as a debugging aid.
5. **PDF fallback** (pre-RTF sessions): `pypdf` (already installed, v6.13) extracts the
   chapter PDFs fine after whitespace normalization — CH1170 (115 pp) parsed in seconds
   and regex counts on it validated the section grammar below — but with per-glyph
   spacing artifacts in headings ("W A TERCRAFT") and **no strike recovery** (see #3).

### Real text structure (from HF 2485 RTF, SF 2385, CH1170 PDF)

```
HF 2485 (LSB 5179HV (8) 90)                        ← LSB line
RELATING TO REGULATION OF WATERCRAFT …             ← title ("AN ACT relating to …" in PDF)
BE IT ENACTED BY THE GENERAL ASSEMBLY OF THE STATE OF IOWA:
   Section 1.  NEW SECTION.  462A.17A  Common interest communities — …
   1.  As used in this section: …                  ← subsection body
   Sec. 2.  NEW SECTION.  462A.17B  Nonprofit corporations — …
   Sec. 3.  EFFECTIVE DATE.  This Act, being deemed of immediate importance, takes
   effect upon enactment.
```

Grounded parser rules (NBSP `\xa0` separators in RTF output; counts from CH1170, 512
sections):

- **Section head**: `^\s*(Section|Sec\.)\s+(?P<num>\d+)\.` — first section is spelled
  `Section 1.`, the rest `Sec. N.`.
- **Amendatory lead-ins** (immediately after the head; 472/512 sections in CH1170 carry a
  `Code 20XX` lead-in):
  - `Section {code_sec}[, subsection …], Code {year}[, as amended by …], is amended to read as follows:` (408×)
  - `… is amended by adding the following new {subsection|paragraph|section}` (21×)
  - `… is amended by striking …` (44×)
  - `Section(s) {code_sec}[ and …], Code {year}, {is|are} repealed.` (19×; also
    self-repeals: "This section is repealed December 31, 2028")
  - `Sec. N. NEW SECTION. {code_sec} {heading}` (14×)
- **Boilerplate sections**: `EFFECTIVE DATE.`, `RETROACTIVE APPLICABILITY.`,
  `APPLICABILITY.`, `CODE EDITOR DIRECTIVE.`, `TRANSITION …` — capture as ordinary
  sections; the effective-date section's text feeds `effective_from` for the chapter.
- Trailer: signature block (Speaker/President/certification/"Approved {date}, {year}" /
  Governor) — strip; the approval date is on the listing + amended table anyway.

## The supersession edge capture (the point of this ingest)

Two independent, mutually-checking channels — build **both**:

1. **The authoritative table** — `/law/statutory/acts/amended?ga={ga}&session={s}`
   (verified: the page's `ssid` param is **ignored**; the picker is `data-ga`/
   `data-session`, and the GET params `ga`/`session` work). Plain HTML table, columns:
   `Reference | Action | Bill/Section | Eff Date | App Date | Gov's Action | Gov's Action
   Date`. Verified rows: 2026 session = 1,826; 2024 = 2,871; works back to **GA 84 / 2011**
   (2,096 rows; that is the dropdown's floor). Sample:
   `['2024 Code - 2.69', 'Repeal', 'SF2385, §53', '2024-07-01', '', 'Signed', '2024-05-17']`.
   - References carry **subunit granularity** (`2024 Code - 2.47A (1)(b)`) and `New Code`
     for not-yet-codified sections.
   - **Action taxonomy** (2024 distribution): Amend 1,784 · Repeal 265 · New 255 · Add 220
     · Strike 157 · **Transfer Directive 91** (Code-editor renumbering — crosswalk fuel!)
     · Strike and Replace 67 · Amend New 24 · Repeal New 8.
   - Governor's-action column excludes/flags vetoed material for us.
2. **Parser-extracted lead-ins** from the act text itself (grammar above), which localize
   the edge to the exact **act section node** and recover old/new text via strike/ul runs.

Storage: on each act-section Node,
`source_metadata = {"ga": 90, "session": 2, "bill": "SF2385", "affects": [{"code_ref":
"2.69", "action": "repeal", "eff_date": "2024-07-01"}], "gov_action": "Signed", …}` —
then a backfill command joins `Bill/Section ↔ chapter/section` (the enrolled bill's
section numbers are the act chapter's section numbers — verified CH1170 ≡ SF 2385) and
writes **cross-source `CrossReference` edges act-section → iowa-code section** plus the
supersession-pipeline events. Note (same gap as the IAC plan): **no cross-source citation
resolver exists yet** — the IAC Phase 3 enabling-statute backfill is the same new code
path; build it once, share it.

## How it maps onto our data model

- **Source** (seed migration, mirror `corpus/migrations/0022_seed_iowa_admin_code.py`):
  `slug="iowa-acts"`, `name="Iowa Acts"`, `citation_abbreviation="Iowa Acts"`,
  `official_url_template="https://www.legis.iowa.gov/docs/acts/{year}/CH{chapter:0>4}.pdf"`.
- **NodeType** rows: `session` (level 0), `chapter` (level 1), `section` (level 2, leaf).
  Reusing the `chapter`/`section` keys keeps browse's statute-style rendering
  (`browse.py:110` checks `"chapter" in node_types`) and `compare_editions`' `section`
  leaf working with zero generalization (unlike IAC's `rule`).
- **Node** paths (`path` unique per source, dotted like Code/IAC):
  - session → `path="2024"` (extra sessions: `"2023E1"`, `"2021E2"`), heading
    "2024 — 90th G.A., Regular Session", `source_metadata={"ga":90,"session":2,"ssid":166}`
  - chapter → `path="2024.1170"`, `ordinal=1170`, heading = listing title,
    `source_metadata={"bill":"SF2385", …}`
  - section → `path="2024.1170.12"`, `ordinal=12`, heading = post-lead-in heading for NEW
    SECTIONs / the affected Code cite otherwise.
- **NodeVersion**: one per section, `effective_from` = the section's effective date
  (amended-table `Eff Date`; default July 1 following enactment; "immediate importance" →
  approval date), `effective_to=NULL` forever, `enacted_by="{BILL} (GA {ga})"`,
  `body_text` = strike-resolved text, `body_segments` = del/ins runs.
- **CitationFormat**: `{year} Iowa Acts, ch. {chapter}` / section segment `, §{section}`.
- **Embedding**: act sections are Code-section-sized → whole-NodeVersion embedding,
  voyage-law-2, auto-detected granularity — no retrieval changes (proven by IAC).

## Scale & cost (measured)

- **~120–200 chapters/session**, ~2,500–3,500 sections/session (CH1170 alone has 512;
  the 2024 amended table has 2,871 Code-ref rows).
- 2024 volume = **913 PDF pages ≈ 3.7 M chars ≈ ~1.0 M tokens**; independently, 187
  enrolled RTFs = 13.45 MB ≈ ~4.3 M chars text (measured 3.1× RTF-to-text ratio) ≈ ~1.2 M
  tokens. Call it **~1 M tokens/session**.
- **Scope v1: GA 88–91 (2019–2026, 8 regular + 3 extra sessions) ≈ ~8–9 M tokens ≈ ~$1**
  on voyage-law-2. Back to GA 83/2009 (RTF floor) ≈ ~18 M tokens ≈ ~$2–3. Deeper history
  is PDF-territory and can wait for a demand signal.
- Requests: ~190 RTFs + 1 listing + 1 amended page per session — trivial with the cached
  `Fetcher`.

## Implementation phases

### Phase 0 — Parser spike (~0.5–1 day)
Custom linear RTF tokenizer with `\strike`/`\ul` state (replaces striprtf here; keep
striprtf for Iowa Code where files are small). Prove on: HF 2485 (clean new-law bill),
SF 2435 (mid-size), SF 2385 (1.38 MB omnibus — must parse in seconds, not minutes), and
one appropriations bill (dollar-table layout risk, UNVERIFIED). Deliverable:
`parse_enrolled_rtf(bytes) -> ParsedAct` probe JSON; eyeball section splits, lead-in edge
extraction vs. the amended table for the same bill (recall/precision numbers), and
strike-resolved text vs. the current Iowa Code section text (they should converge).

### Phase 1 — Core ingest app (~2 days)
Mirror `ingestion_iowa_admin_code/` as **`ingestion_iowa_acts/`**:
1. Seed migration: Source + 3 NodeTypes + CitationFormat (pattern: `0022_seed_iowa_admin_code.py`).
2. `scraper.py`: enumerate ssids from the dropdown → per-session `actsChapter` listing →
   chapter/bill/title/gov-letter map → fetch enrolled RTF (fallback: chapter PDF via
   pypdf for pre-RTF sessions) → parse → probe JSON. Also scrape the amended table per
   session into the probe JSON (it's one page).
3. `parser.py`/`differ.py`/`validators.py`/`writer.py` — near-copies; validator asserts
   section-number contiguity and that parser-extracted edges ⊆ amended-table edges
   (± known gaps). Shared `RawIngestion`/`IngestionRun` from `ingestion_iowa_code.models`.
4. Commands `scrape_iowa_acts [--ga N --session N]` + `ingest_iowa_acts <json> [--dry-run]`.
5. Ingest GA 88–91 → approve → `embed_corpus --source iowa-acts`. Prod caveat: seed
   migration must be run manually in prod (no migrate job), same as 0020/0022.

### Phase 2 — Surface wiring (~0.5 day)
Same hardcode list as IAC Phase 2: `_DOC_TYPE_SLUG` (`search_common.py:168`) add
`"session_law": "iowa-acts"`; `_render_citation` + `_search_row` kind map; citation
parser (`citations/parser.py`) taught `20\d\d Iowa Acts, ch\. \d+(, §\d+)?` →
`path {year}.{ch}[.{sec}]`; browse works as statute-style (3-level session tier shares
whatever agency-tier solution IAC Phase 2 lands, or flatten sessions into the chapter
list since there are only ~11 in scope).

### Phase 3 — Supersession edges (the payoff) (~2 days)
- `backfill_acts_code_edges` command: amended-table rows + parser edges →
  `CrossReference` act-section → `iowa-code` node (shared new cross-source resolver with
  IAC Phase 3) + emit supersession events (Repeal/Transfer Directive rows are the
  headline wins — they catch Madden-class staleness for *statutes*).
- Wire into the currency tripwire: a retrieved Code section with a pending
  amend/repeal edge whose `eff_date` has passed but whose Code edition predates it gets
  the PR9-style warning.
- Mid-session cadence: `update_iowa_acts` re-scrapes the current session's amended table
  + newly listed chapters (content-hash no-ops the rest) — this is how we know about a
  repeal **months before the new Code edition ships**.

### Phase 4 — Constitutions (the cheap add-on) (~1 day)
- **Iowa Constitution** (verified): `/law/statutory/constitution` offers PDF only —
  codified `/docs/publications/ICP/1518288.pdf` (**27 pages**, amendments incorporated,
  Iowa-Code styling), original `/docs/publications/ICP/1518289.pdf`, amendments list at
  `/law/statutory/constitution/amendmentCitations` (HTML). Ingest the codified PDF via
  pypdf: Source `iowa-constitution` ("Iowa Const."), NodeTypes `article` (level 0) /
  `section` (level 1, leaf), path `I.7` style (article Roman numeral normalized), citation
  `Iowa Const. art. I, §7`. ~150 sections — small enough to hand-review the whole parse
  before approval. One-time; amendments are rare (track the amendmentCitations page).
- **US Constitution** (verified): archives.gov clean HTML transcripts —
  `/founding-docs/constitution-transcript` (Preamble + Arts. I–VII),
  `/founding-docs/bill-of-rights-transcript` and `/founding-docs/amendments-11-27`
  (both UNVERIFIED-fetched but linked from the transcript page). Alternative official
  source with Iowa provenance: `legis.iowa.gov/docs/publications/ICP/1207140.pdf` (the
  US Constitution as printed with the Iowa Code). Source `us-constitution`
  ("U.S. Const."), NodeTypes `article`/`amendment` at level 0, `section` leaf; paths
  `I.8`, `am14.1`; citations `U.S. Const. art. I, §8` / `U.S. Const. amend. XIV, §1`.
  Note: `Source.jurisdiction` — add a `us` Jurisdiction row (model requires one;
  currently Iowa-only). ~60 nodes, ~50k tokens; negligible cost.

### Phase 5 — Assistant + eval (~0.5 day)
- Confirm `lookup_citation` source routing (`_default_source` hardcoded to Iowa Code,
  `lookups.py:1123`) accepts `iowa-acts`/constitution slugs.
- Eval additions: (a) "what did the legislature change about X in 2024" retrieves an act
  section; (b) verification gate validates a `2024 Iowa Acts, ch. 1170, §12` cite+quote;
  (c) a question about a Code section repealed this session surfaces the tripwire warning.

## Risks & wrinkles

1. **striprtf performance** — measured unusable above ~300 KB (see numbers above). The
   custom tokenizer is mandatory, not an optimization. Mitigation: it's also what gives
   us strike/ul, so one piece of work retires two risks.
2. **Stricken-text pollution** — if we ever fall back to PDF text (pre-2009 sessions),
   amendatory sections embed repealed words invisibly. Acceptable for historical acts
   (flag `"strike_resolved": false` in metadata); never acceptable for the GA 88+ corpus.
3. **Appropriations bills** — dollar-amount tabular layouts inside sections; parser
   behavior UNVERIFIED until the Phase 0 spike. Worst case: keep raw lines as body.
4. **Item vetoes** — chapters enacted with portions item-vetoed; how the enrolled RTF /
   acts chapter marks the vetoed matter is UNVERIFIED. The amended table's Gov's Action
   column ("Signed w/ item veto") flags which bills to hand-check.
5. **Amended-table floor is GA 84 (2011)** — earlier sessions get parser-extracted edges
   only (or none, pre-RTF). Fine: supersession value is concentrated in recent sessions.
6. **Effective dates are per-section and conditional** (immediate importance, retroactive,
   contingent) — take the amended table's per-row `Eff Date` as truth where present;
   default July 1 otherwise; store the effective-date section text for the rest.
7. **Bill-number reuse across GAs** — `HF 2485` means a different bill each GA; every
   join must be keyed `(ga, bill)`, never bill alone.
8. **`Code {year}` in lead-ins ≠ act year** — a 2024 act amends "Code 2024"; keep the
   referenced Code year in the edge metadata for edition-accurate diffing.

## Effort & acceptance

- **MVP (GA 88–91 searchable + citable + edge table captured): ~4 days** = Phases 0–2 +
  the amended-table scrape.
- **Full v1 (supersession wiring + constitutions + eval): ~7–8 days.**
- **Acceptance:** (a) `2024 Iowa Acts, ch. 1170, §12` resolves, browses, and is
  retrievable; (b) chat about a 2024 law change cites an act section that the
  verification gate validates; (c) Iowa Code § 2.69 (repealed by SF 2385 §53) carries a
  supersession edge with eff-date 2024-07-01, and the tripwire fires on it; (d) `Iowa
  Const. art. I, §7` and `U.S. Const. amend. XIV, §1` resolve and retrieve; (e) SF 2385
  (1.38 MB) parses in <10 s with strike-resolved text.

## The one-source-of-truth checklist

1. Custom linear strike/ul-aware RTF tokenizer + `parse_enrolled_rtf` (Phase 0 spike).
2. Seed migration: `iowa-acts` Source + `session`/`chapter`/`section` NodeTypes +
   CitationFormat.
3. `ingestion_iowa_acts/` app (scraper incl. amended-table capture, parser, differ,
   validators, writer + `scrape_iowa_acts`/`ingest_iowa_acts`).
4. Ingest GA 88–91 → approve → `embed_corpus --source iowa-acts` (~$1).
5. Surface wiring: `_DOC_TYPE_SLUG`, citation render/parse for `{year} Iowa Acts, ch. N, §M`.
6. `backfill_acts_code_edges` (shares the new cross-source resolver with IAC Phase 3) +
   tripwire wiring + `update_iowa_acts` mid-session job.
7. Constitutions: `us` Jurisdiction row, `iowa-constitution` + `us-constitution` seeds,
   one-time PDF/HTML ingests, hand-review, embed.
8. Assistant/MCP source wiring + the three eval regressions.
