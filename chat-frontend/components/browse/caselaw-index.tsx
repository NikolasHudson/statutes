"use client";

// Search-first caselaw index (76k+ decisions can't be a tree). A scoped search
// box routes to the unified results pane (cases scope + filters); below it, a
// recent-decisions list driven by GET /api/browse/cases, filterable by court
// (facet chips), precedential status, and decided-year range. Rows link
// straight to the /cases/[id] reader. Blue accent per the caselaw convention.

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircleIcon, ScaleIcon, SearchIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  browseCases,
  type BrowseSource,
  type CaseListItem,
  type CaseListResponse,
  type SearchFilters,
} from "@/lib/iowa-browse";
import { LoadingBlock } from "@/components/browse/reader";

const selectCls =
  "h-8 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

function CaseRow({ c }: { c: CaseListItem }) {
  const year = (c.date_filed || "").slice(0, 4);
  const meta = [
    c.court_name,
    year && `Decided ${year}`,
    c.docket_number && `No. ${c.docket_number}`,
  ]
    .filter(Boolean)
    .join("  ·  ");
  return (
    <li>
      <Link
        href={`/cases/${c.id}`}
        className="group flex w-full flex-col gap-1 py-3 transition-colors hover:bg-muted/40"
      >
        <div className="flex items-baseline gap-3">
          <span className="flex-1 font-medium text-foreground/90 text-sm group-hover:text-blue-700 dark:group-hover:text-blue-300">
            {c.case_name}
          </span>
          {c.citations[0] && (
            <span className="shrink-0 font-mono text-muted-foreground text-xs">
              {c.citations[0]}
            </span>
          )}
        </div>
        {meta && <div className="text-muted-foreground text-xs">{meta}</div>}
      </Link>
    </li>
  );
}

function CourtChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-xs transition-colors",
        active
          ? "bg-blue-600 font-medium text-white"
          : "border border-input hover:bg-accent",
      )}
    >
      {label}
      {count != null && (
        <span className={active ? "ml-1 opacity-80" : "ml-1 text-muted-foreground"}>
          {count.toLocaleString()}
        </span>
      )}
    </button>
  );
}

export function CaselawIndex({
  source,
  onSearch,
}: {
  source: BrowseSource | null;
  onSearch: (query: string, filters: SearchFilters) => void;
}) {
  const [q, setQ] = useState("");
  const [court, setCourt] = useState("");
  const [status, setStatus] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");

  const [data, setData] = useState<CaseListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Only build a bound from a complete 4-digit year, so partial keystrokes
  // ("2", "20") don't fire a fetch with a malformed "2-01-01" bound.
  const dateFrom = /^\d{4}$/.test(yearFrom) ? `${yearFrom}-01-01` : null;
  const dateTo = /^\d{4}$/.test(yearTo) ? `${yearTo}-12-31` : null;

  // Reload the recent-decisions list whenever a filter changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    browseCases({
      court: court || undefined,
      status: status || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: 30,
      facets: true,
    })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load decisions.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [court, status, dateFrom, dateTo]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = q.trim();
    if (!query) return;
    onSearch(query, {
      doc_type: "cases",
      court: court || null,
      status: status || null,
      date_from: dateFrom,
      date_to: dateTo,
    });
  };

  const facetCourts = data?.facets?.courts ?? [];
  const filtersActive = !!(court || status || dateFrom || dateTo);

  return (
    <main className="min-w-0 flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wide">
          <ScaleIcon className="size-3.5 text-blue-600 dark:text-blue-400" />
          <span>{source?.jurisdiction ?? "Iowa"}</span>
        </div>
        <h1 className="mt-2 font-semibold text-3xl tracking-tight">
          {source?.name ?? "Iowa Caselaw"}
        </h1>
        <p className="mt-2 text-muted-foreground text-sm">
          {(source?.entries ?? 0).toLocaleString()} decisions — search full text
          or browse recent filings.
        </p>

        <form className="mt-5" onSubmit={submit}>
          <div className="relative">
            <SearchIcon className="-translate-y-1/2 absolute top-1/2 left-3.5 size-4.5 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search Iowa decisions…"
              className="h-11 pr-24 pl-11"
            />
            <Button
              type="submit"
              size="sm"
              className="-translate-y-1/2 absolute top-1/2 right-2"
            >
              Search
            </Button>
          </div>
        </form>

        {/* Filters: court facet chips + status + year range */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <CourtChip
            label="All courts"
            active={!court}
            onClick={() => setCourt("")}
          />
          {facetCourts.map((c) => (
            <CourtChip
              key={c.court_id}
              label={c.court_name}
              count={c.count}
              active={court === c.court_id}
              onClick={() => setCourt(court === c.court_id ? "" : c.court_id)}
            />
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          <select
            className={selectCls}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Precedential status"
          >
            <option value="">Any status</option>
            <option value="Published">Published</option>
            <option value="Unpublished">Unpublished</option>
          </select>
          <Input
            type="number"
            inputMode="numeric"
            min={1839}
            max={new Date().getFullYear()}
            placeholder="From yr"
            className="h-8 w-24 text-xs"
            value={yearFrom}
            onChange={(e) => setYearFrom(e.target.value)}
          />
          <Input
            type="number"
            inputMode="numeric"
            min={1839}
            max={new Date().getFullYear()}
            placeholder="To yr"
            className="h-8 w-24 text-xs"
            value={yearTo}
            onChange={(e) => setYearTo(e.target.value)}
          />
        </div>

        <Separator className="my-6" />

        <h2 className="font-semibold text-muted-foreground text-xs uppercase tracking-[0.18em]">
          {filtersActive ? "Decisions" : "Recent decisions"}
        </h2>

        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : loading && !data ? (
          <div className="mt-4">
            <LoadingBlock label="Loading decisions…" />
          </div>
        ) : !data || data.results.length === 0 ? (
          <p className="mt-4 text-muted-foreground text-sm">
            No decisions match these filters.
          </p>
        ) : (
          <>
            <ul className="mt-3 divide-y border-y">
              {data.results.map((c) => (
                <CaseRow key={c.id} c={c} />
              ))}
            </ul>
            {data.has_more && (
              <p className="mt-3 text-muted-foreground text-xs">
                Showing the {data.results.length} most recent — refine with the
                filters or search above to narrow.
              </p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
