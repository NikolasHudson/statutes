// Thin fetch wrapper for the Iowa Legal Corpus REST API.
//
// Same-origin in dev (Vite proxies /api → backend); override with
// VITE_API_BASE for non-dev hosting. credentials: 'include' is on every
// call so the Django session cookie round-trips for register/login/me.

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export type User = {
  id: number;
  email: string;
  full_name: string;
  tier: string;
  date_joined: string;
};

export type APIKey = {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
};

export type CreatedAPIKey = APIKey & { raw_key: string };

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    ...init,
  });
  const text = await resp.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!resp.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? resp.statusText;
    throw new ApiError(resp.status, detail);
  }
  return body as T;
}

// ---- config ----

export type PublicConfig = {
  mcp_host: string | null;
  source: 'explicit' | 'codespaces' | 'unset';
};

export const fetchPublicConfig = () => request<PublicConfig>('/api/config');

// ---- auth ----

export const register = (data: { email: string; password: string; full_name?: string }) =>
  request<User>('/api/auth/register', { method: 'POST', body: JSON.stringify(data) });

export const login = (data: { email: string; password: string }) =>
  request<User>('/api/auth/login', { method: 'POST', body: JSON.stringify(data) });

export const logout = () =>
  request<{ status: string }>('/api/auth/logout', { method: 'POST' });

export const fetchMe = () => request<User>('/api/auth/me');

export const updateProfile = (data: { full_name?: string; email?: string }) =>
  request<User>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const changePassword = (data: {
  current_password: string;
  new_password: string;
}) =>
  request<{ status: string }>('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify(data),
  });

// ---- api keys ----

export const listKeys = () => request<APIKey[]>('/api/account/api-keys');

export const createKey = (name: string) =>
  request<CreatedAPIKey>('/api/account/api-keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });

export const revokeKey = (id: number) =>
  request<{ status: string; id: number }>(`/api/account/api-keys/${id}`, {
    method: 'DELETE',
  });

// ---- corpus browser (public, read-only) ----

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
  // Citation-native permalink key — for a chapter, the bare number ("714").
  path: string;
  citation: string;
  ordinal: string;
  heading: string;
  reserved: boolean;
  official_url: string;
  metadata: Record<string, unknown>;
  children: BrowseChild[];
};

// One in-text citation that resolved to a live node in the same source.
// `text` is the exact substring as it appears in body_text; the reader
// matches on it (the body is reparsed before render, so byte offsets
// wouldn't survive — the literal phrase does).
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
  // Citation-native permalink key, e.g. "714.16".
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

export const browseSources = () =>
  request<BrowseSource[]>('/api/browse/sources');

export const browseChapters = (slug: string) =>
  request<{ source: { slug: string; name: string }; chapters: BrowseChapter[] }>(
    `/api/browse/sources/${encodeURIComponent(slug)}/chapters`,
  );

export const browseChapter = (id: number) =>
  request<ChapterDetail>(`/api/browse/chapters/${id}`);

export const browseNode = (id: number) =>
  request<NodeDetail>(`/api/browse/nodes/${id}`);

export type ResolveResult =
  | { found: true; node_id: number; path: string; is_chapter: boolean }
  | {
      found: false;
      candidates: { node_id: number; path: string; heading: string }[];
    };

// Resolve a citation-native permalink ("#/iowa-code/714.16") to a node.
// Never guesses: an unresolved cite comes back { found: false } with
// same-chapter candidates.
export const browseResolve = (source: string, cite: string) =>
  request<ResolveResult>(
    `/api/browse/resolve?source=${encodeURIComponent(source)}` +
      `&cite=${encodeURIComponent(cite)}`,
  );

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

// Keyword search (FTS + trigram) over the approved, currently effective
// corpus. `source` scopes to one source slug; omit it to search everything.
export const browseSearch = (q: string, source?: string | null) => {
  const params = new URLSearchParams({ q });
  if (source) params.set('source', source);
  return request<BrowseSearchResponse>(
    `/api/browse/search?${params.toString()}`,
  );
};

// ---- AI chat (server OpenAI key, login required — see apps/api/chat.py) ----

export type ToolCallTrace = {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
};

export type ChatResponse = {
  content: string;
  tool_calls: ToolCallTrace[];
  model: string;
};

export type ChatPayload = {
  model: string;
  messages: { role: 'user' | 'assistant' | 'system'; content: string }[];
  // null / omitted searches every source; a slug scopes the assistant.
  source_slug?: string | null;
};

export const chat = (payload: ChatPayload) =>
  request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
