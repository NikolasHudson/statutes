// Thin fetch helpers for the /api/browse endpoints. Same-origin in dev via
// the Next.js rewrite to Django on :8000. Shapes mirror the Pydantic
// schemas in apps/api/browse.py — keep them in sync.

export type BrowseSource = {
  slug: string;
  name: string;
  abbreviation: string;
  jurisdiction: string;
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

export type BrowseSearchResult = {
  node_id: number;
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

export type BrowseSearchResponse = {
  query: string;
  scope: string | null;
  count: number;
  results: BrowseSearchResult[];
};

export type ResolveResult =
  | { found: true; node_id: number; path: string; is_chapter: boolean }
  | {
      found: false;
      candidates: { node_id: number; path: string; heading: string }[];
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

// Keyword search (FTS + trigram) over the approved, currently-effective
// corpus. `source` scopes to one slug; omit to search everything.
export const browseSearch = (q: string, source?: string | null) => {
  const params = new URLSearchParams({ q });
  if (source) params.set("source", source);
  return json<BrowseSearchResponse>(
    `/api/browse/search?${params.toString()}`,
  );
};

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
