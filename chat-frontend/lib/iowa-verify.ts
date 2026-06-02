// Adapter glue between the Verify Document page and the Django
// /api/verify/document endpoint. Mirrors lib/iowa-chat.ts: POST a document,
// read NDJSON events, and yield them as the per-citation checklist fills in.

import { DJANGO_BASE } from "./iowa-chat";

export type CitationStatus = "green" | "yellow" | "red";

export type LanguageVerdict =
  | "exact"
  | "fuzzy"
  | "not_found"
  | "supported"
  | "partial"
  | "contradicted"
  | "unverified";

export type LanguageCheck = {
  claim_text: string;
  kind: "quote" | "paraphrase";
  verdict: LanguageVerdict;
  match_score: number;
  source_excerpt: string;
  span: [number, number];
};

export type CitationForm = {
  status: "ok" | "corrected" | "unresolvable";
  written: string;
  canonical: string | null;
  note: string;
};

export type CitationFinding = {
  raw: string;
  span: [number, number];
  status: CitationStatus;
  format_ok: boolean;
  resolution: "valid" | "repealed" | "not_found" | "parse_error";
  source_label: string | null;
  target_path: string | null;
  detail: string;
  form: CitationForm | null;
  language_checks: LanguageCheck[];
};

export type VerifySummary = {
  total: number;
  green: number;
  yellow: number;
  red: number;
};

export type VerifyEvent =
  | { type: "start"; char_count: number; citations_total: number }
  | { type: "citation_done"; index: number; finding: CitationFinding }
  | ({ type: "summary" } & VerifySummary)
  | { type: "done" }
  | { type: "error"; message: string };

export type VerifyInput = { text: string } | { file: File };

// POST a document to /api/verify/document and yield parsed NDJSON events.
// Buffers partial lines across chunk boundaries (same approach as streamChat).
export async function* streamVerify(
  input: VerifyInput,
  signal: AbortSignal,
  model?: string,
): AsyncGenerator<VerifyEvent, void, void> {
  const form = new FormData();
  if ("file" in input) {
    form.append("file", input.file);
  } else {
    form.append("text", input.text);
  }
  if (model) form.append("model", model);

  let r: Response;
  try {
    r = await fetch(`${DJANGO_BASE}/api/verify/document`, {
      method: "POST",
      credentials: "include",
      signal,
      body: form,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    yield { type: "error", message: (e as Error).message ?? String(e) };
    return;
  }

  if (r.status === 401) {
    yield {
      type: "error",
      message: "Not signed in. Refresh the page to log back in.",
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
    yield { type: "error", message: "No response body from verify endpoint" };
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
            yield JSON.parse(line) as VerifyEvent;
          } catch {
            // ignore malformed lines defensively
          }
        }
        nl = buffer.indexOf("\n");
      }
    }
    if (buffer.trim()) {
      try {
        yield JSON.parse(buffer.trim()) as VerifyEvent;
      } catch {
        /* trailing garbage */
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// Human-readable label for a language-check verdict, used on the per-claim
// badge in the checklist.
export function verdictLabel(verdict: LanguageVerdict): string {
  switch (verdict) {
    case "exact":
      return "Verbatim match";
    case "fuzzy":
      return "Near-verbatim";
    case "not_found":
      return "Not in source";
    case "supported":
      return "Supported";
    case "partial":
      return "Partially supported";
    case "contradicted":
      return "Contradicted";
    case "unverified":
      return "Unverified";
  }
}
