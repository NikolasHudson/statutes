"use client";

// Unified search-results pane for the corpus browser. Rows are kind-aware: a
// caselaw hit (kind="case") shows the case name + court/year and routes to
// /cases/<id>; statute/rule hits show the citation + chapter and open in the
// reader. Active advanced-search filters render as read-only chips. Snippet
// highlighting is purely cosmetic and term-driven on the client (the server
// already HTML-escapes the snippet text).

import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  XIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { BrowseSearchResponse, BrowseSearchResult } from "@/lib/iowa-browse";
import { LoadingBlock } from "@/components/browse/reader";

export function SearchResultsPane({
  query,
  loading,
  error,
  data,
  chips,
  onPick,
  onClose,
  onPageChange,
}: {
  query: string;
  loading: boolean;
  error: string | null;
  data: BrowseSearchResponse | null;
  chips: string[];
  onPick: (r: BrowseSearchResult) => void;
  onClose: () => void;
  onPageChange: (page: number) => void;
}) {
  const count = data?.results.length ?? 0;
  const pageSize = data?.limit || 10;
  const offset = data?.offset ?? 0;
  const page = Math.floor(offset / pageSize) + 1;
  const hasMore = data?.has_more ?? false;
  const showPager = !!data && count > 0 && (page > 1 || hasMore);
  return (
    <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
      {/* Sticky results header — fills the window width. */}
      <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur md:px-10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate font-semibold text-xl tracking-tight">
              Results for{" "}
              <span className="font-mono text-foreground/90">
                &ldquo;{query}&rdquo;
              </span>
            </h1>
            <p className="mt-1 text-muted-foreground text-sm">
              {loading
                ? "Searching the corpus…"
                : count === 0
                  ? "No results"
                  : `Showing ${offset + 1}–${offset + count}`}
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="shrink-0"
          >
            <XIcon className="size-3.5" /> Close
          </Button>
        </div>
        {chips.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground text-xs">Filters:</span>
            {chips.map((c) => (
              <span
                key={c}
                className="rounded-full border border-input bg-muted/40 px-2.5 py-0.5 font-medium text-muted-foreground text-xs"
              >
                {c}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="px-6 py-4 md:px-10">
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : loading ? (
          <LoadingBlock label="Searching the corpus…" />
        ) : !data || data.results.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/30 px-4 py-12 text-center text-muted-foreground text-sm">
            No matches for{" "}
            <span className="font-mono">&ldquo;{query}&rdquo;</span>.
          </div>
        ) : (
          <>
            <ul className="divide-y">
              {data.results.map((r, i) => (
                <SearchResultRow
                  key={`${r.node_id}-${i}`}
                  result={r}
                  query={query}
                  onPick={onPick}
                />
              ))}
            </ul>
            {showPager && (
              <div className="mt-4 flex items-center justify-between border-t pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => onPageChange(page - 1)}
                >
                  <ChevronLeftIcon className="size-4" /> Previous
                </Button>
                <span className="text-muted-foreground text-xs">Page {page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasMore}
                  onClick={() => onPageChange(page + 1)}
                >
                  Next <ChevronRightIcon className="size-4" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

// Split the snippet on the query terms and wrap matches in <mark>. The snippet
// is rendered as plain JSX children, so React auto-escapes every fragment —
// no raw HTML ever reaches the DOM. Highlighting is purely cosmetic.
function highlightSnippet(snippet: string, query: string): ReactNode {
  const terms = [
    ...new Set(
      query
        .toLowerCase()
        .split(/\s+/)
        .map((t) => t.trim())
        .filter((t) => t.length >= 2),
    ),
  ].sort((a, b) => b.length - a.length);
  if (terms.length === 0) return snippet;

  const re = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi",
  );
  const parts = snippet.split(re);
  // String.split with a capturing group interleaves matches at odd indices.
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark
        // biome-ignore lint/suspicious/noArrayIndexKey: static split output
        key={i}
        className="rounded-sm bg-primary/15 px-0.5 font-medium text-foreground"
      >
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

// Per-kind type pill so results are scannable at a glance.
const KIND_BADGE: Record<
  BrowseSearchResult["kind"],
  { label: string; cls: string }
> = {
  case: { label: "Case", cls: "bg-blue-600/10 text-blue-700 dark:text-blue-300" },
  code: { label: "Iowa Code", cls: "bg-primary/10 text-primary" },
  rule: {
    label: "Court Rules",
    cls: "bg-amber-600/10 text-amber-700 dark:text-amber-300",
  },
};

function Pill({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 font-medium text-xs ${className}`}
    >
      {children}
    </span>
  );
}

function ResultShell({
  onPick,
  result,
  title,
  meta,
  cite,
  badges,
  query,
  accentHover,
}: {
  onPick: () => void;
  result: BrowseSearchResult;
  title: ReactNode;
  meta: string;
  cite?: string;
  badges: ReactNode;
  query: string;
  accentHover: string;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        className="group block w-full py-3.5 text-left transition-colors hover:bg-muted/40"
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h3
              className={`line-clamp-2 font-semibold text-[15px] leading-snug ${accentHover}`}
            >
              {title}
            </h3>
            {meta && (
              <p className="mt-0.5 truncate text-muted-foreground text-xs">{meta}</p>
            )}
            {cite && (
              <p className="mt-0.5 truncate font-mono text-foreground/70 text-xs">
                {cite}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">{badges}</div>
        </div>
        {result.snippet && (
          <p className="mt-1.5 line-clamp-2 text-foreground/70 text-sm leading-relaxed">
            {highlightSnippet(result.snippet, query)}
          </p>
        )}
      </button>
    </li>
  );
}

function SearchResultRow({
  result,
  query,
  onPick,
}: {
  result: BrowseSearchResult;
  query: string;
  onPick: (r: BrowseSearchResult) => void;
}) {
  const badge = KIND_BADGE[result.kind] ?? KIND_BADGE.code;

  // Caselaw: case name + court/year, blue accent, routes to /cases/<id>.
  if (result.kind === "case") {
    const year = (result.date_filed || "").slice(0, 4);
    return (
      <ResultShell
        onPick={() => onPick(result)}
        result={result}
        query={query}
        accentHover="text-foreground group-hover:text-blue-700 dark:group-hover:text-blue-300"
        title={result.case_name || result.heading || "(unnamed case)"}
        meta={[result.court_name, year].filter(Boolean).join("  ·  ")}
        cite={result.citations?.[0]}
        badges={
          <>
            {result.exact && (
              <Pill className="bg-primary/10 text-primary">Exact</Pill>
            )}
            <Pill className={badge.cls}>{badge.label}</Pill>
          </>
        }
      />
    );
  }

  // Statute / rule: citation + heading, chapter context.
  const tail = result.citation.trim().split(/\s+/).pop();
  const chapterMeta = result.chapter
    ? `Chapter ${result.chapter.ordinal}${
        result.chapter.heading ? ` — ${result.chapter.heading}` : ""
      }`
    : "";
  return (
    <ResultShell
      onPick={() => onPick(result)}
      result={result}
      query={query}
      accentHover="text-foreground group-hover:text-primary"
      title={
        <>
          <span className="mr-2 font-mono text-sm tabular-nums">{tail}</span>
          <span className="font-medium">{result.heading || "(no heading)"}</span>
        </>
      }
      meta={chapterMeta}
      badges={
        <>
          {result.exact && (
            <Pill className="bg-primary/10 text-primary">Exact</Pill>
          )}
          <Pill className={badge.cls}>{badge.label}</Pill>
        </>
      }
    />
  );
}
