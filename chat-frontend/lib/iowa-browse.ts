// Thin fetch helpers for the /api/browse endpoints. Same-origin in dev via
// the Next.js rewrite to Django on :8000. Shapes mirror the Pydantic
// schemas in apps/api/browse.py — keep them in sync.

export type BrowseSource = {
  slug: string;
  name: string;
  abbreviation: string;
  jurisdiction: string;
  // "statutes" → chapter-index browsing; "caselaw" → search-first index.
  kind: "statutes" | "caselaw";
  has_chapters: boolean;
  chapters: number;
  entries: number;
  entry_label: string;
};

export type BrowseChapter = {
  id: number;
  ordinal: string;
  heading: string;
  reserved: boolean;
  child_count: number;
};

export type BrowseChild = {
  id: number;
  type: string;
  ordinal: string;
  citation: string;
  heading: string;
  division: string;
};

export type ChapterDetail = {
  id: number;
  type: string;
  source_slug: string;
  path: string;
  citation: string;
  ordinal: string;
  heading: string;
  reserved: boolean;
  official_url: string;
  metadata: Record<string, unknown>;
  children: BrowseChild[];
};

export type CrossRef = {
  text: string;
  path: string;
  node_id: number;
};

export type NodeDetail = {
  id: number;
  type: string;
  source: string;
  source_slug: string;
  path: string;
  citation: string;
  heading: string;
  chapter: { id: number; citation: string } | null;
  division: string;
  official_url: string;
  history: string[];
  body_text: string;
  effective_from: string | null;
  has_content: boolean;
  cross_refs: CrossRef[];
};

// Iowa caselaw — one decision served by /api/browse/cases/{id}. Shapes mirror
// the hand-serialized dict in apps/api/browse.py case_detail — keep in sync.
// One inline run of opinion text. `case` links to /cases/<id>; `star` is a
// West page break; `sup` a footnote mark; `em` italic; plain otherwise.
export type CaseRun = {
  t?: string;
  em?: boolean;
  case?: number;
  star?: string;
  sup?: string;
};

export type CaseSegment = {
  k: "byline" | "p" | "quote" | "fn";
  runs: CaseRun[];
  mark?: string;
};

export type CaseOpinion = {
  id: number;
  heading: string;
  type: string;
  author_str: string;
  per_curiam: boolean;
  body_text: string;
  // Rich display structure with linked citations; null → render body_text.
  body_segments: CaseSegment[] | null;
  has_content: boolean;
};

export type CitedCase = {
  case_id: number;
  case_name: string;
  count: number;
};

export type CaseDetail = {
  id: number;
  type: string;
  source: string;
  source_slug: string;
  path: string;
  cl_cluster_id: number | null;
  case_name: string;
  case_name_full: string;
  court_id: string;
  court_name: string;
  court_level: number | null;
  date_filed: string;
  docket_number: string;
  precedential_status: string;
  judges: string;
  disposition: string;
  posture: string;
  nature_of_suit: string;
  citations: string[];
  official_url: string;
  // Prefatory caption (court / docket / parties / counsel) lifted from the
  // opinion text; "" when none. Rendered centered + bold.
  caption_block: string;
  head_matter: string | null;
  opinions: CaseOpinion[];
  cited_cases: CitedCase[];
  external_citation_count: number;
};

export type BrowseSearchResult = {
  node_id: number;
  // How the UI opens the hit: "case" → /cases/<case_id>; "code"/"rule" → reader.
  kind: "code" | "rule" | "case";
  // Decision node id for a caselaw hit (opinion hits resolve to their parent
  // decision); null for statutes/rules.
  case_id: number | null;
  case_name: string | null;
  // Caselaw display meta ("" / [] for statutes/rules).
  court_name: string;
  date_filed: string;
  // The case's own reporter citation(s), e.g. ["223 N.W.2d 270"].
  citations: string[];
  type: string;
  citation: string;
  source: string;
  source_slug: string;
  chapter: { ordinal: string; heading: string } | null;
  heading: string;
  snippet: string;
  // True for the pinned exact-citation hit (e.g. user typed "714.16").
  exact: boolean;
};

// One row of the caselaw browse list (GET /api/browse/cases).
export type CaseListItem = {
  id: number;
  case_name: string;
  court_id: string;
  court_name: string;
  court_level: number | null;
  date_filed: string;
  docket_number: string;
  precedential_status: string;
  citations: string[];
};

export type CaseFacetCourt = {
  court_id: string;
  court_name: string;
  court_level: number | null;
  count: number;
};

export type CaseListResponse = {
  results: CaseListItem[];
  limit: number;
  offset: number;
  has_more: boolean;
  facets: { courts: CaseFacetCourt[] } | null;
};

export type BrowseSearchResponse = {
  query: string;
  scope: string | null;
  count: number;
  // Fused hits available across all pages (bounded by the retriever depths).
  // Optional: responses cached before the field shipped may omit it.
  total?: number;
  offset: number;
  limit: number;
  has_more: boolean;
  results: BrowseSearchResult[];
};

// Results per search page (kept in sync with the backend default).
export const SEARCH_PAGE_SIZE = 10;

export type ResolveResult =
  | { found: true; node_id: number; path: string; is_chapter: boolean }
  | {
      found: false;
      candidates: { node_id: number; path: string; heading: string }[];
    };

export type Edition = {
  year: number;
  label: string;
  as_of_date: string;
};

export type EditionsResponse = {
  source: { slug: string; name: string };
  editions: Edition[];
  default: { from_year: number; to_year: number } | null;
};

export type CompareRef = {
  node_id: number;
  path: string;
  citation: string;
  heading: string;
  chapter: string;
};

export type CompareSummary = {
  source: string;
  from_year: number;
  to_year: number;
  from_as_of: string;
  to_as_of: string;
  counts: { added: number; amended: number; repealed: number; unchanged: number };
  covered_chapters: number;
  added: CompareRef[];
  amended: CompareRef[];
  repealed: CompareRef[];
  error?: string;
};

export type DiffSegment = { op: "equal" | "insert" | "delete"; text: string };

export type SectionDiff = {
  node_id: number;
  path: string;
  citation: string;
  heading: string;
  from: { year: number; as_of: string; present: boolean; body_text: string };
  to: { year: number; as_of: string; present: boolean; body_text: string };
  changed: boolean;
  diff: DiffSegment[];
  error?: string;
};

export class BrowseError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function json<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* response wasn't JSON */
    }
    throw new BrowseError(r.status, detail);
  }
  return (await r.json()) as T;
}

export const browseSources = () => json<BrowseSource[]>("/api/browse/sources");

export const browseChapters = (slug: string) =>
  json<{
    source: { slug: string; name: string };
    chapters: BrowseChapter[];
  }>(`/api/browse/sources/${encodeURIComponent(slug)}/chapters`);

export const browseChapter = (id: number) =>
  json<ChapterDetail>(`/api/browse/chapters/${id}`);

export const browseNode = (id: number) =>
  json<NodeDetail>(`/api/browse/nodes/${id}`);

// One Iowa caselaw decision: metadata + head-matter + opinions + cited cases.
export const browseCase = (id: number) =>
  json<CaseDetail>(`/api/browse/cases/${id}`);

// Advanced-search filters. `source` scopes to a slug directly; `doc_type`
// (code/rules/cases/all) is the friendly alias; the caselaw filters
// (court/status/date) imply the cases scope server-side.
export type SearchFilters = {
  source?: string | null;
  doc_type?: string | null;
  court?: string | null;
  status?: string | null;
  date_from?: string | null;
  date_to?: string | null;
};

// Keyword search (FTS + trigram, RRF-fused) over the approved, currently
// effective corpus. Pass filters to scope/facet; `page` (1-based) paginates.
export const browseSearch = (
  q: string,
  filters: SearchFilters = {},
  page = 1,
) => {
  const params = new URLSearchParams({ q });
  for (const [k, v] of Object.entries(filters)) {
    if (v) params.set(k, v);
  }
  params.set("limit", String(SEARCH_PAGE_SIZE));
  params.set("offset", String((Math.max(1, page) - 1) * SEARCH_PAGE_SIZE));
  return json<BrowseSearchResponse>(`/api/browse/search?${params.toString()}`);
};

// Caselaw browse list — recent decisions, optionally filtered by
// court/status/year/date and faceted. Powers the search-first caselaw index.
export type CaseListFilters = {
  court?: string | null;
  status?: string | null;
  year?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  limit?: number;
  offset?: number;
  facets?: boolean;
};

export const browseCases = (filters: CaseListFilters = {}) => {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return json<CaseListResponse>(`/api/browse/cases${qs ? `?${qs}` : ""}`);
};

// Editions registered for a source, newest first, plus a default compare pair.
export const browseEditions = (source: string) =>
  json<EditionsResponse>(
    `/api/browse/editions?source=${encodeURIComponent(source)}`,
  );

// Summary of what changed between two editions (no body text — buckets only).
export const browseCompare = (source: string, fromYear: number, toYear: number) =>
  json<CompareSummary>(
    `/api/browse/compare?source=${encodeURIComponent(source)}` +
      `&from_year=${fromYear}&to_year=${toYear}`,
  );

// Both bodies + a word-level diff for one section.
export const browseCompareSection = (
  nodeId: number,
  fromYear: number,
  toYear: number,
) =>
  json<SectionDiff>(
    `/api/browse/compare/section?node_id=${nodeId}` +
      `&from_year=${fromYear}&to_year=${toYear}`,
  );

export const browseResolve = (source: string, cite: string) =>
  json<ResolveResult>(
    `/api/browse/resolve?source=${encodeURIComponent(source)}` +
      `&cite=${encodeURIComponent(cite)}`,
  );

// Format an ISO date string like "2024-01-01" → "Jan 1, 2024". Falls back to
// the input on bad data so the UI never shows "Invalid Date".
export function fmtEffective(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
