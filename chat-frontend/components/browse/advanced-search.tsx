"use client";

// Search-first landing for the corpus browser plus the shared advanced-search
// panel. The panel's fielded state (AdvancedFilters) is converted to the
// `browseSearch` query params and to display chips via the helpers below, so the
// home view, the header bar, and the results pane all agree on what's active.

import { useState } from "react";
import {
  BookOpenIcon,
  ChevronDownIcon,
  FileTextIcon,
  LandmarkIcon,
  ScaleIcon,
  SearchIcon,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { BrowseSource, SearchFilters } from "@/lib/iowa-browse";

// ---------------------------------------------------------------------------
// Shared filter model + adapters
// ---------------------------------------------------------------------------

export type AdvancedFilters = {
  docType: "all" | "code" | "admin" | "rules" | "cases";
  court: string; // "" | "iowa" | "iowactapp"
  status: string; // "" | "Published" | "Unpublished"
  yearFrom: string;
  yearTo: string;
};

export const EMPTY_FILTERS: AdvancedFilters = {
  docType: "all",
  court: "",
  status: "",
  yearFrom: "",
  yearTo: "",
};

export const COURT_LABEL: Record<string, string> = {
  iowa: "Supreme Court",
  iowactapp: "Court of Appeals",
};

export const DOC_TYPE_LABEL: Record<string, string> = {
  code: "Iowa Code",
  admin: "Iowa Admin. Code",
  rules: "Court Rules",
  cases: "Cases",
};

// Court/status/date only mean anything for caselaw, so the cases + all scopes
// carry them; code/rules drop them (the backend treats any caselaw filter as a
// scope override, so emitting a stale court on a Code search would silently
// hijack it).
function caselawScoped(docType: AdvancedFilters["docType"]): boolean {
  return docType === "all" || docType === "cases";
}

// Build an ISO bound only from a complete 4-digit year, so partial keystrokes
// ("2", "20") never produce a malformed "2-01-01" that the backend would
// compare lexicographically.
function yearBound(year: string, suffix: string): string | null {
  return /^\d{4}$/.test(year) ? `${year}${suffix}` : null;
}

// AdvancedFilters → the params browseSearch sends.
export function toSearchFilters(f: AdvancedFilters): SearchFilters {
  const cases = caselawScoped(f.docType);
  return {
    doc_type: f.docType === "all" ? null : f.docType,
    court: cases ? f.court || null : null,
    status: cases ? f.status || null : null,
    date_from: cases ? yearBound(f.yearFrom, "-01-01") : null,
    date_to: cases ? yearBound(f.yearTo, "-12-31") : null,
  };
}

// Read-only chips summarizing the *active* filters — mirrors toSearchFilters so
// the chips match what is actually sent.
export function filterChips(f: AdvancedFilters): string[] {
  const chips: string[] = [];
  if (f.docType !== "all") chips.push(DOC_TYPE_LABEL[f.docType]);
  if (!caselawScoped(f.docType)) return chips;
  if (f.court) chips.push(COURT_LABEL[f.court] ?? f.court);
  if (f.status) chips.push(f.status);
  const from = yearBound(f.yearFrom, "");
  const to = yearBound(f.yearTo, "");
  if (from || to) chips.push(`${from ?? "earliest"}–${to ?? "latest"}`);
  return chips;
}

// ---------------------------------------------------------------------------
// Advanced-search panel
// ---------------------------------------------------------------------------

function Seg<T extends string>({
  value,
  current,
  onClick,
  children,
}: {
  value: T;
  current: T;
  onClick: (v: T) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={cn(
        "rounded-md px-3 py-1.5 font-medium text-sm transition-colors",
        value === current
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-semibold text-muted-foreground text-xs uppercase tracking-wide">
      {children}
    </span>
  );
}

const selectCls =
  "h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

// Iowa's earliest reported decision is 1839; cap at the current year.
const MIN_YEAR = 1839;
const MAX_YEAR = new Date().getFullYear();

export function AdvancedSearch({
  filters,
  onChange,
}: {
  filters: AdvancedFilters;
  onChange: (f: AdvancedFilters) => void;
}) {
  const set = (patch: Partial<AdvancedFilters>) =>
    onChange({ ...filters, ...patch });
  // Switching to code/rules clears the caselaw-only fields so a stale court/year
  // can't linger behind a disabled control (and silently re-scope the search).
  const setDocType = (v: AdvancedFilters["docType"]) =>
    onChange(
      caselawScoped(v)
        ? { ...filters, docType: v }
        : { ...filters, docType: v, court: "", status: "", yearFrom: "", yearTo: "" },
    );
  const casesScoped = caselawScoped(filters.docType);

  return (
    <div className="mt-3 space-y-4 rounded-lg border bg-muted/20 p-4 text-left">
      <div className="flex flex-col gap-1.5">
        <FieldLabel>Document type</FieldLabel>
        <div className="flex flex-wrap gap-1 rounded-lg border bg-background p-1">
          <Seg value="all" current={filters.docType} onClick={setDocType}>
            All
          </Seg>
          <Seg value="code" current={filters.docType} onClick={setDocType}>
            Iowa Code
          </Seg>
          <Seg value="admin" current={filters.docType} onClick={setDocType}>
            Admin. Code
          </Seg>
          <Seg value="rules" current={filters.docType} onClick={setDocType}>
            Court Rules
          </Seg>
          <Seg value="cases" current={filters.docType} onClick={setDocType}>
            Cases
          </Seg>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <FieldLabel>Court</FieldLabel>
          <select
            className={selectCls}
            value={filters.court}
            disabled={!casesScoped}
            onChange={(e) => set({ court: e.target.value })}
          >
            <option value="">Any court</option>
            <option value="iowa">Supreme Court of Iowa</option>
            <option value="iowactapp">Court of Appeals of Iowa</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <FieldLabel>Status</FieldLabel>
          <select
            className={selectCls}
            value={filters.status}
            disabled={!casesScoped}
            onChange={(e) => set({ status: e.target.value })}
          >
            <option value="">Any status</option>
            <option value="Published">Published</option>
            <option value="Unpublished">Unpublished</option>
          </select>
        </label>
      </div>

      <div className="flex flex-col gap-1.5">
        <FieldLabel>Decided / effective year</FieldLabel>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={MIN_YEAR}
            max={MAX_YEAR}
            placeholder="From"
            className="h-9 w-28"
            value={filters.yearFrom}
            onChange={(e) => set({ yearFrom: e.target.value })}
          />
          <span className="text-muted-foreground text-sm">to</span>
          <Input
            type="number"
            inputMode="numeric"
            min={MIN_YEAR}
            max={MAX_YEAR}
            placeholder="To"
            className="h-9 w-28"
            value={filters.yearTo}
            onChange={(e) => set({ yearTo: e.target.value })}
          />
        </div>
      </div>

      <p className="text-muted-foreground text-xs">
        Court and status apply to cases. The query box supports{" "}
        <span className="font-mono">AND</span>,{" "}
        <span className="font-mono">OR</span>,{" "}
        <span className="font-mono">-exclude</span>, and{" "}
        <span className="font-mono">&ldquo;exact phrases&rdquo;</span>.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Home / landing view
// ---------------------------------------------------------------------------

export const SOURCE_ICON: Record<string, LucideIcon> = {
  "iowa-code": BookOpenIcon,
  "iowa-admin-code": LandmarkIcon,
  "iowa-court-rules": FileTextIcon,
  "iowa-caselaw": ScaleIcon,
};

function SourceCard({
  source,
  onClick,
}: {
  source: BrowseSource;
  onClick: () => void;
}) {
  const Icon = SOURCE_ICON[source.slug] ?? BookOpenIcon;
  const caselaw = source.kind === "caselaw";
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col gap-2 rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <span
        className={cn(
          "flex size-9 items-center justify-center rounded-lg",
          caselaw
            ? "bg-blue-600/10 text-blue-700 dark:text-blue-300"
            : "bg-primary/10 text-primary",
        )}
      >
        <Icon className="size-4.5" />
      </span>
      <span className="font-semibold text-sm">{source.name}</span>
      <span className="text-muted-foreground text-xs">
        {source.entries.toLocaleString()} {source.entry_label.toLowerCase()}
      </span>
    </button>
  );
}

export function HomeView({
  sources,
  query,
  onQueryChange,
  filters,
  onFiltersChange,
  onSubmit,
  onOpenSource,
}: {
  sources: BrowseSource[] | null;
  query: string;
  onQueryChange: (q: string) => void;
  filters: AdvancedFilters;
  onFiltersChange: (f: AdvancedFilters) => void;
  onSubmit: () => void;
  onOpenSource: (slug: string) => void;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <main className="min-w-0 flex-1 overflow-y-auto px-6 py-12 md:px-10">
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <SearchIcon className="size-6" />
          </span>
          <h1 className="mt-4 font-semibold text-3xl tracking-tight">
            Search the corpus
          </h1>
          <p className="mt-2 text-muted-foreground text-sm">
            Iowa Code, Court Rules, and 76,000+ Iowa decisions — one search box.
          </p>
        </div>

        <form
          className="mt-7"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          <div className="relative">
            <SearchIcon className="-translate-y-1/2 absolute top-1/2 left-4 size-5 text-muted-foreground" />
            <Input
              autoFocus
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Search statutes, rules, and cases…"
              className="h-13 pr-28 pl-12 text-base"
            />
            <Button
              type="submit"
              size="sm"
              className="-translate-y-1/2 absolute top-1/2 right-2"
            >
              Search
            </Button>
          </div>

          <div className="mt-2.5 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="inline-flex items-center gap-1 text-muted-foreground text-sm hover:text-foreground"
            >
              Advanced search
              <ChevronDownIcon
                className={cn(
                  "size-3.5 transition-transform",
                  showAdvanced && "rotate-180",
                )}
              />
            </button>
            {filterChips(filters).length > 0 && (
              <span className="text-muted-foreground text-xs">
                {filterChips(filters).join(" · ")}
              </span>
            )}
          </div>

          {showAdvanced && (
            <AdvancedSearch filters={filters} onChange={onFiltersChange} />
          )}
        </form>

        <div className="mt-12">
          <h2 className="font-semibold text-muted-foreground text-xs uppercase tracking-[0.18em]">
            Browse a source
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {sources?.map((s) => (
              <SourceCard
                key={s.slug}
                source={s}
                onClick={() => onOpenSource(s.slug)}
              />
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
