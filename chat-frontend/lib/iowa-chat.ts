// Adapter glue between assistant-ui's runtime and our Django /api/chat
// endpoints. The streaming variant reads NDJSON events from
// /api/chat/stream; the tool_calls surface as a Markdown "Sources" footer
// appended to the streamed text so the existing react-markdown pipeline
// renders linked citations for free.

// Empty base = same-origin (Next.js rewrites forward /api/* to Django).
export const DJANGO_BASE = "";

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

export type BrowseSource = {
  slug: string;
  name: string;
  abbreviation: string;
  jurisdiction: string;
};

const SOURCE_LABELS: Record<string, string> = {
  "iowa-code": "Iowa Code",
  "iowa-court-rules": "Iowa Court Rules",
  "iowa-admin-code": "Iowa Admin. Code",
};

type ApiNode = {
  id: number;
  heading: string;
  citation: string;
  official_url: string;
  source_slug: string;
  path?: string;
};

function isNode(v: unknown): v is ApiNode {
  return (
    !!v &&
    typeof v === "object" &&
    "id" in v &&
    "citation" in v &&
    "heading" in v
  );
}

export function citationsMarkdown(
  trace: ToolCallTrace[],
  answer: string,
): string {
  const byId = new Map<number, ApiNode>();
  const add = (n: ApiNode) => {
    if (!byId.has(n.id)) byId.set(n.id, n);
  };

  for (const call of trace) {
    const r = call.result as Record<string, unknown> | null;
    if (!r) continue;
    if (Array.isArray(r.hits)) {
      for (const h of r.hits as Record<string, unknown>[]) {
        if (isNode(h.node)) add(h.node);
      }
    }
    const section = r.section as Record<string, unknown> | null;
    if (section && isNode(section.node)) add(section.node);
    const chapter = r.chapter as Record<string, unknown> | null;
    if (chapter && isNode(chapter.node)) add(chapter.node);
    if (chapter && Array.isArray(chapter.sections)) {
      for (const n of chapter.sections) if (isNode(n)) add(n);
    }
    if (Array.isArray(r.candidates)) {
      for (const n of r.candidates) if (isNode(n)) add(n);
    }
  }

  if (byId.size === 0) return "";

  const all = [...byId.values()];
  const key = (n: ApiNode) =>
    (n.path && n.path.trim()) || n.citation.trim().split(/\s+/).pop() || "";
  const cited = all.filter((n) => key(n) && answer.includes(key(n)!));
  const chosen = (cited.length ? cited : all).slice(0, 8);

  // Next.js basePath isn't automatically applied to raw <a href> strings
  // (only to <Link>). The markdown renderer turns these into raw <a>, so
  // we have to prepend the basePath ourselves. NEXT_PUBLIC_BASE_PATH is
  // set by us at build time when basePath is configured in next.config.ts.
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

  const lines = chosen.map((n) => {
    const label = SOURCE_LABELS[n.source_slug] ?? n.source_slug;
    const bareCite =
      (n.path && n.path.trim()) ||
      n.citation.trim().split(/\s+/).pop() ||
      "";
    const browseUrl = `${basePath}/browse#/${n.source_slug}/${bareCite}`;
    return `- [**${n.citation}** — ${n.heading}](${browseUrl}) · ${label} · [official ↗](${n.official_url})`;
  });
  return `\n\n---\n\n**Sources**\n\n${lines.join("\n")}`;
}

// Helpers to format args from the backend's tool schemas. Arg names mirror
// the Python tool handlers in apps/api/chat.py — keep them in sync.
const str = (v: unknown): string =>
  typeof v === "string" ? v.trim() : "";
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

// Friendly two-line progress label for an in-flight tool call. The first
// element is the short label (verb + object); the second is the detail
// (the actual query text, citation, etc.) shown under it in the tracker.
export type ToolStepText = { label: string; description?: string };

export function toolLabel(
  name: string,
  args: Record<string, unknown>,
): ToolStepText {
  if (name === "search_statutes") {
    const q = str(args.query);
    return {
      label: q ? `Searching the corpus` : "Searching the corpus",
      description: q ? `“${q}”` : undefined,
    };
  }
  if (name === "lookup_citation") {
    const c = str(args.citation);
    return {
      label: c ? "Reading section" : "Reading a section",
      description: c || undefined,
    };
  }
  if (name === "get_section_at_date") {
    const id = num(args.section_id);
    const date = str(args.on_date);
    const parts = [
      id ? `§${id}` : null,
      date ? `as of ${date}` : null,
    ].filter(Boolean) as string[];
    return {
      label: "Resolving section by date",
      description: parts.length ? parts.join(" ") : undefined,
    };
  }
  if (name === "get_version_history") {
    const id = num(args.section_id);
    return {
      label: "Pulling amendment history",
      description: id ? `§${id}` : undefined,
    };
  }
  if (name === "get_cross_references") {
    const id = num(args.section_id);
    return {
      label: "Following cross-references",
      description: id ? `from §${id}` : undefined,
    };
  }
  if (name === "get_definitions") {
    const term = str(args.term);
    const chapter = str(args.chapter);
    return {
      label: term ? "Looking up definition" : "Pulling definitions",
      description: [term && `“${term}”`, chapter && `in ch. ${chapter}`]
        .filter(Boolean)
        .join(" ") || undefined,
    };
  }
  if (name === "list_recent_amendments") {
    const since = str(args.since);
    return {
      label: "Listing recent amendments",
      description: since ? `since ${since}` : undefined,
    };
  }
  return { label: `Running ${name}`, description: undefined };
}

export async function fetchSources(): Promise<BrowseSource[]> {
  try {
    const r = await fetch(`${DJANGO_BASE}/api/browse/sources`, {
      credentials: "include",
    });
    if (!r.ok) return [];
    return (await r.json()) as BrowseSource[];
  } catch {
    return [];
  }
}

export type StreamEvent =
  | { type: "tool_start"; name: string; arguments: Record<string, unknown> }
  | { type: "delta"; text: string }
  | { type: "done"; tool_calls: ToolCallTrace[]; model: string }
  | { type: "error"; message: string };

// Generator that POSTs to /api/chat/stream and yields parsed NDJSON events.
// Handles partial lines across chunk boundaries (the network can split a
// JSON line anywhere, so we buffer until we see a newline).
export async function* streamChat(
  body: {
    model: string;
    messages: { role: "user" | "assistant" | "system"; content: string }[];
    source_slug: string | null;
  },
  signal: AbortSignal,
): AsyncGenerator<StreamEvent, void, void> {
  const r = await fetch(`${DJANGO_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    signal,
    body: JSON.stringify(body),
  });

  if (r.status === 401) {
    yield {
      type: "error",
      message:
        "Not signed in. Refresh the page to log back in.",
    };
    return;
  }
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* not JSON */
    }
    yield { type: "error", message: detail };
    return;
  }
  if (!r.body) {
    yield { type: "error", message: "No response body from stream endpoint" };
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl = buffer.indexOf("\n");
      while (nl !== -1) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) {
          try {
            yield JSON.parse(line) as StreamEvent;
          } catch {
            // ignore malformed lines defensively
          }
        }
        nl = buffer.indexOf("\n");
      }
    }
    if (buffer.trim()) {
      try {
        yield JSON.parse(buffer.trim()) as StreamEvent;
      } catch {
        /* trailing garbage */
      }
    }
  } finally {
    reader.releaseLock();
  }
}
