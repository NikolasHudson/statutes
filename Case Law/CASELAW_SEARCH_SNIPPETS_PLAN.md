# Caselaw search — highlighted snippets & matching chunks (design, do later)

Captured 2026-06-04. Not yet built. The case *display* layer (linked citations
via `NodeVersion.body_segments`) is done; this doc is about the **search results
experience**: highlighted terms and matching text chunks on a results page.

## The three representations (what gets searched)

| Field | Derived from | Job | Searched? |
|---|---|---|---|
| `NodeVersion.body_text` | source HTML, stripped+normalized | `content_hash`, FTS `search_vector`, embeddings | **Yes — canonical search corpus** |
| `NodeVersion.embedding` (1024-dim, **deferred for caselaw**) | `body_text` | semantic retrieval | it *is* an index of body_text |
| `NodeVersion.body_segments` (display-only) | source HTML | rich render + citation links | **No — never searched** |

Snippets/highlights come from `body_text` (or chunks), never from
`body_segments`, so highlights always match what was searched. As of 2026-06-04
all 111,323 caselaw versions have `search_vector` populated (FTS live); caselaw
`embedding` count = 0 (semantic deferred, needs chunking).

## Highlighted snippets — `ts_headline`

Postgres generates the highlighted excerpt from the searched text:

```sql
ts_headline('english', v.body_text, q,
  'StartSel=<mark>,StopSel=</mark>,MaxFragments=2,MaxWords=22,MinWords=10,FragmentDelimiter= … ')
```

- `MaxFragments=N` → up to N separate matching **chunks** per case (joined by the
  delimiter) — this is "chunks of text that match the term."
- `MaxWords`/`MinWords` → fragment length. `StartSel`/`StopSel` → highlight wrapper.

Verified real output (caselaw, query "exhausted administrative remedies"):
`…failed to «exhaust» «administrative» «remedies» with PERB … «remedies» had not
been «exhausted». … we concluded that «exhaustion»…`

### Current gap
`apps/api/browse.py:_search_snippet` (`SNIPPET_CHARS=240`) is a hand-rolled
window around the first match, HTML-escaped, with **no term highlighting** and a
single fragment. Upgrade path: replace it with `ts_headline` (highlighted terms +
multi-fragment chunks). Small, contained change to the existing browse-search
endpoint. Keep the HTML-escaping discipline (see Rendering safely).

### Whitespace caveat
`body_text` is the stripped text, so fragmented-citation opinions contain `\n\n`
breaks (e.g. snippet shows `Id.\n\nat 522`). `ts_headline` preserves them →
collapse whitespace on the headline output before display (`" ".join(s.split())`).
(The render-time reflow in `case-console.tsx` fixes the *full-doc* view; snippets
just need the collapse.)

## Keyword vs. semantic snippets
- **Keyword/boolean** (live): `ts_headline` gives highlighted matching fragments
  directly. `to_tsquery` / `websearch_to_tsquery` support AND/OR/NOT/phrase;
  `pg_trgm` for fuzzy. Works on all caselaw today.
- **Semantic** (after chunking): the match is a passage, not a literal term, so
  the **matched chunk is the snippet**. Optionally run `ts_headline` over the
  chunk to highlight any literal query-word overlap (may be partial/none — that's
  expected for semantic). Requires the deferred `Chunk` model (chunk text + vector
  + offset). Chunking also sharpens keyword results (return the passage, not "page
  17 of a 40-page opinion").

## Highlighting in the opened case
On click, the case view renders `body_segments` (linked citations). To carry the
highlight: pass the query terms to `/cases/[id]`, and wrap matching substrings
**inside the segment runs** in `<mark>` (and/or scroll to the matched chunk).
Segment text == body_text content, so the same terms highlight consistently on
both the results list and the full document.

## Rendering safely (no XSS)
Don't `dangerouslySetInnerHTML` raw `ts_headline` output. Either (a) HTML-escape
the text then insert `<mark>` (the current snippet already escapes), or (b) use a
non-HTML sentinel for StartSel/StopSel, split it in the frontend, and wrap matches
in `<mark>` React elements. Same pattern for highlighting segment runs.

## Implementation steps (when picked up)
1. Backend: swap `_search_snippet` → `ts_headline` (sentinel sel markers,
   MaxFragments=2–3, whitespace-collapse). Return either escaped-HTML-with-`<mark>`
   or structured `{text, hit}` runs.
2. Frontend: caselaw search results page rendering highlighted snippets; style
   `<mark>`. (No caselaw-specific results UI exists yet — `/api/browse/search`
   already returns hits + a `snippet`.)
3. Case view: accept `?q=` (or highlight terms), `<mark>` matches in segment runs,
   scroll to first match.
4. After chunking lands: semantic retrieval returns chunks; snippet = chunk text;
   hybrid (RRF, already in `apps/corpus/services/search.py`) fuses keyword+vector.

## Dependencies
- Chunking / shared `Chunk` model (deferred) — gates semantic snippets and
  passage-level retrieval. See `CASELAW_INGESTION_PLAN.md` Phase 4.
- Caselaw embeddings pass (deferred) — re-embed `body_text` chunks with Voyage.
