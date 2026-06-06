"use client";

// Unified search-results pane for the corpus browser. Two columns: a left
// filter rail and the results list. The filter rail drives the REAL server
// search — every facet maps onto a `browseSearch` param via AdvancedFilters
// (content type → doc_type; court/status/decided-year → the caselaw-scoped
// filters), so changing one re-runs the search through the page's URL plumbing
// rather than filtering a single loaded page client-side. (The search endpoint
// returns no facet counts, treatment, or citation metrics, so — unlike the
// design mockup at /browse-mockup/results-v2 — those don't appear here.)
//
// Rows are kind-aware: a caselaw hit (kind="case") shows the case name +
// court/year and routes to /cases/<id>; statute/rule hits show the citation +
// chapter and open in the reader. Snippet/title highlighting is purely cosmetic
// and term-driven on the client (the server already HTML-escapes the text).

import {
	AlertCircleIcon,
	CheckIcon,
	ChevronLeftIcon,
	ChevronRightIcon,
	ListFilterIcon,
	XIcon,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import {
	type AdvancedFilters,
	COURT_LABEL,
	DOC_TYPE_LABEL,
} from "@/components/browse/advanced-search";
import { LoadingBlock } from "@/components/browse/reader";
import { Button } from "@/components/ui/button";
import type {
	BrowseSearchResponse,
	BrowseSearchResult,
} from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

export function SearchResultsPane({
	query,
	loading,
	error,
	data,
	filters,
	onFiltersChange,
	onPick,
	onClose,
	onPageChange,
}: {
	query: string;
	loading: boolean;
	error: string | null;
	data: BrowseSearchResponse | null;
	// Active fielded filters (derived from the URL) and a setter that re-runs the
	// server search with the new filters.
	filters: AdvancedFilters;
	onFiltersChange: (f: AdvancedFilters) => void;
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

	const chips = buildChips(filters, onFiltersChange);

	return (
		<div className="flex min-h-0 min-w-0 flex-1">
			<ResultsFilters
				filters={filters}
				onChange={onFiltersChange}
				loading={loading}
			/>

			<main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
				{/* Sticky results header — fills the column width. */}
				<div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur md:px-8">
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
								<button
									key={c.key}
									type="button"
									onClick={c.clear}
									className="group inline-flex items-center gap-1 rounded-full border border-input bg-muted/40 py-0.5 pr-1 pl-2.5 font-medium text-muted-foreground text-xs transition-colors hover:text-foreground"
								>
									{c.label}
									<span className="flex size-4 items-center justify-center rounded-full text-muted-foreground/70 group-hover:bg-accent group-hover:text-foreground">
										<XIcon className="size-3" />
									</span>
								</button>
							))}
						</div>
					)}
				</div>

				<div className="px-6 py-4 md:px-8">
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
									<span className="text-muted-foreground text-xs">
										Page {page}
									</span>
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
		</div>
	);
}

// ---------------------------------------------------------------------------
// Filter rail — every control maps onto a real browseSearch param.
// ---------------------------------------------------------------------------

const DOC_TYPES: { id: AdvancedFilters["docType"]; label: string }[] = [
	{ id: "all", label: "All content" },
	{ id: "cases", label: "Cases" },
	{ id: "code", label: "Iowa Code" },
	{ id: "rules", label: "Court Rules" },
];

const COURTS: { value: string; label: string }[] = [
	{ value: "", label: "Any court" },
	{ value: "iowa", label: "Supreme Court of Iowa" },
	{ value: "iowactapp", label: "Court of Appeals of Iowa" },
];

const STATUSES: { value: string; label: string }[] = [
	{ value: "", label: "Any status" },
	{ value: "Published", label: "Published" },
	{ value: "Unpublished", label: "Unpublished" },
];

// Court/status/decided-year only mean anything for caselaw (the backend treats
// any caselaw filter as a scope override), so they're disabled outside the
// cases / all scopes — matching the advanced-search panel.
function caselawScoped(docType: AdvancedFilters["docType"]): boolean {
	return docType === "all" || docType === "cases";
}

function ResultsFilters({
	filters,
	onChange,
	loading,
}: {
	filters: AdvancedFilters;
	onChange: (f: AdvancedFilters) => void;
	loading: boolean;
}) {
	const casesScoped = caselawScoped(filters.docType);
	// Switching to code/rules clears the caselaw-only fields so a stale court/year
	// can't linger behind a disabled control and silently re-scope the search.
	const setDocType = (v: AdvancedFilters["docType"]) =>
		onChange(
			caselawScoped(v)
				? { ...filters, docType: v }
				: {
						...filters,
						docType: v,
						court: "",
						status: "",
						yearFrom: "",
						yearTo: "",
					},
		);

	return (
		<aside className="hidden w-64 shrink-0 flex-col border-r bg-card lg:flex">
			<div className="flex h-12 shrink-0 items-center gap-1.5 border-b px-4 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				<ListFilterIcon className="size-3.5" />
				Refine results
			</div>
			<div
				className={cn(
					"min-w-0 flex-1 divide-y overflow-y-auto transition-opacity",
					loading && "pointer-events-none opacity-60",
				)}
			>
				<FilterSection title="Content type">
					{DOC_TYPES.map((d) => (
						<FacetRow
							key={d.id}
							label={d.label}
							selected={filters.docType === d.id}
							onClick={() => setDocType(d.id)}
						/>
					))}
				</FilterSection>

				<FilterSection title="Court">
					{COURTS.map((c) => (
						<FacetRow
							key={c.value || "any-court"}
							label={c.label}
							selected={(filters.court || "") === c.value}
							disabled={!casesScoped}
							onClick={() => onChange({ ...filters, court: c.value })}
						/>
					))}
				</FilterSection>

				<FilterSection title="Status">
					{STATUSES.map((s) => (
						<FacetRow
							key={s.value || "any-status"}
							label={s.label}
							selected={(filters.status || "") === s.value}
							disabled={!casesScoped}
							onClick={() => onChange({ ...filters, status: s.value })}
						/>
					))}
				</FilterSection>

				<FilterSection title="Decided year">
					<YearRange
						filters={filters}
						onChange={onChange}
						disabled={!casesScoped}
					/>
					{!casesScoped && (
						<p className="px-2 pt-1.5 text-[11px] text-muted-foreground">
							Court, status, and year apply to cases.
						</p>
					)}
				</FilterSection>
			</div>
		</aside>
	);
}

function FilterSection({
	title,
	children,
}: {
	title: string;
	children: ReactNode;
}) {
	return (
		<div className="p-3">
			<h3 className="px-2 pb-1 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				{title}
			</h3>
			<div className="space-y-0.5">{children}</div>
		</div>
	);
}

function FacetRow({
	label,
	selected,
	onClick,
	disabled,
}: {
	label: string;
	selected: boolean;
	onClick: () => void;
	disabled?: boolean;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			disabled={disabled}
			className={cn(
				"group flex w-full items-center gap-2 rounded px-2 py-1 text-left transition-colors",
				disabled ? "cursor-not-allowed opacity-40" : "hover:bg-accent/40",
			)}
		>
			<span
				className={cn(
					"flex size-3.5 shrink-0 items-center justify-center rounded-full border",
					selected
						? "border-primary bg-primary text-primary-foreground"
						: "border-muted-foreground/40",
				)}
			>
				{selected && <CheckIcon className="size-2.5" />}
			</span>
			<span
				className={cn(
					"min-w-0 flex-1 truncate text-[13px]",
					selected
						? "font-medium text-foreground"
						: "text-muted-foreground group-hover:text-foreground",
				)}
			>
				{label}
			</span>
		</button>
	);
}

// Year inputs commit on blur / Enter (not per keystroke) so a partial year
// doesn't fire a search; local draft re-syncs when the URL filters change.
function YearRange({
	filters,
	onChange,
	disabled,
}: {
	filters: AdvancedFilters;
	onChange: (f: AdvancedFilters) => void;
	disabled?: boolean;
}) {
	const [from, setFrom] = useState(filters.yearFrom);
	const [to, setTo] = useState(filters.yearTo);
	useEffect(() => {
		setFrom(filters.yearFrom);
		setTo(filters.yearTo);
	}, [filters.yearFrom, filters.yearTo]);

	const commit = () => {
		if (from !== filters.yearFrom || to !== filters.yearTo)
			onChange({ ...filters, yearFrom: from, yearTo: to });
	};
	const inputCls =
		"h-8 w-full rounded-md border border-input bg-background px-2 text-[13px] tabular-nums outline-none transition focus:border-ring focus:ring-[3px] focus:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

	return (
		<div className="flex items-center gap-1.5 px-2">
			<input
				type="number"
				inputMode="numeric"
				placeholder="From"
				aria-label="Decided from year"
				disabled={disabled}
				value={from}
				onChange={(e) => setFrom(e.target.value)}
				onBlur={commit}
				onKeyDown={(e) => {
					if (e.key === "Enter") e.currentTarget.blur();
				}}
				className={inputCls}
			/>
			<span className="text-muted-foreground text-xs">to</span>
			<input
				type="number"
				inputMode="numeric"
				placeholder="To"
				aria-label="Decided to year"
				disabled={disabled}
				value={to}
				onChange={(e) => setTo(e.target.value)}
				onBlur={commit}
				onKeyDown={(e) => {
					if (e.key === "Enter") e.currentTarget.blur();
				}}
				className={inputCls}
			/>
		</div>
	);
}

// Removable filter chips, built straight from AdvancedFilters so they mirror
// exactly what the rail (and the server search) has active.
function buildChips(
	filters: AdvancedFilters,
	onChange: (f: AdvancedFilters) => void,
): { key: string; label: string; clear: () => void }[] {
	const out: { key: string; label: string; clear: () => void }[] = [];
	if (filters.docType !== "all")
		out.push({
			key: "doc_type",
			label: DOC_TYPE_LABEL[filters.docType] ?? filters.docType,
			clear: () => onChange({ ...filters, docType: "all" }),
		});
	if (!caselawScoped(filters.docType)) return out;
	if (filters.court)
		out.push({
			key: "court",
			label: COURT_LABEL[filters.court] ?? filters.court,
			clear: () => onChange({ ...filters, court: "" }),
		});
	if (filters.status)
		out.push({
			key: "status",
			label: filters.status,
			clear: () => onChange({ ...filters, status: "" }),
		});
	if (filters.yearFrom || filters.yearTo)
		out.push({
			key: "year",
			label: `${filters.yearFrom || "earliest"}–${filters.yearTo || "latest"}`,
			clear: () => onChange({ ...filters, yearFrom: "", yearTo: "" }),
		});
	return out;
}

// ---------------------------------------------------------------------------
// Result rows
// ---------------------------------------------------------------------------

// Split the snippet/title on the query terms and wrap matches in <mark>. The
// text is rendered as plain JSX children, so React auto-escapes every fragment —
// no raw HTML ever reaches the DOM. Highlighting is purely cosmetic.
function highlight(text: string, query: string): ReactNode {
	const terms = [
		...new Set(
			query
				.toLowerCase()
				.split(/\s+/)
				.map((t) => t.trim())
				.filter((t) => t.length >= 2),
		),
	].sort((a, b) => b.length - a.length);
	if (terms.length === 0) return text;

	const re = new RegExp(
		`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
		"gi",
	);
	const parts = text.split(re);
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
const KIND: Record<
	BrowseSearchResult["kind"],
	{ label: string; tint: string }
> = {
	case: {
		label: "Case",
		tint: "bg-blue-600/10 text-blue-700 dark:text-blue-300",
	},
	code: {
		label: "Iowa Code",
		tint: "bg-primary/10 text-primary",
	},
	rule: {
		label: "Court Rules",
		tint: "bg-amber-600/10 text-amber-700 dark:text-amber-300",
	},
};

function SearchResultRow({
	result: r,
	query,
	onPick,
}: {
	result: BrowseSearchResult;
	query: string;
	onPick: (r: BrowseSearchResult) => void;
}) {
	const k = KIND[r.kind] ?? KIND.code;
	const isCase = r.kind === "case";

	const title = isCase ? r.case_name || r.heading || "(unnamed case)" : null;
	const year = isCase ? (r.date_filed || "").slice(0, 4) : "";
	const context = isCase
		? [r.court_name, year].filter(Boolean).join("  ·  ")
		: r.chapter
			? `Chapter ${r.chapter.ordinal}${
					r.chapter.heading ? ` — ${r.chapter.heading}` : ""
				}`
			: r.source;
	// Citation rides with the row: the reporter cite(s) for a case, the code/rule
	// cite otherwise. For code/rule, lead the heading with the cite's last token.
	const cite = isCase ? r.citations.join("  ·  ") : r.citation;
	const tail = isCase ? "" : r.citation.trim().split(/\s+/).pop();

	return (
		<li>
			<button
				type="button"
				onClick={() => onPick(r)}
				className="group flex w-full items-start gap-3 py-3.5 pr-1 text-left transition-colors hover:bg-muted/40"
			>
				<div className="min-w-0 flex-1">
					<div className="flex flex-wrap items-center gap-x-2 gap-y-1">
						<span
							className={cn(
								"inline-flex items-center rounded px-1.5 py-0.5 font-medium text-[10px]",
								k.tint,
							)}
						>
							{k.label}
						</span>
						<span className="text-[11px] text-muted-foreground">{r.type}</span>
						{r.exact && (
							<span className="rounded bg-primary/10 px-1.5 py-px font-medium text-[10px] text-primary">
								Exact match
							</span>
						)}
					</div>

					<h3 className="mt-1 font-semibold text-[15px] leading-snug group-hover:text-primary group-hover:underline">
						{isCase ? (
							highlight(title ?? "", query)
						) : (
							<>
								<span className="mr-2 font-mono text-sm tabular-nums">
									{tail}
								</span>
								<span>{highlight(r.heading || "(no heading)", query)}</span>
							</>
						)}
					</h3>

					<p className="mt-0.5 truncate text-muted-foreground text-xs">
						{isCase && cite && (
							<span className="font-mono text-foreground/80">{cite}</span>
						)}
						{isCase && cite && context ? "  ·  " : ""}
						{context}
					</p>
					{!isCase && cite && (
						<p className="mt-0.5 truncate font-mono text-foreground/70 text-xs">
							{cite}
						</p>
					)}

					{r.snippet && (
						<p className="mt-1.5 line-clamp-2 text-foreground/75 text-[13px] leading-relaxed">
							{highlight(r.snippet, query)}
						</p>
					)}
				</div>

				<ChevronRightIcon className="mt-1 size-4 shrink-0 text-muted-foreground/40 transition-all group-hover:translate-x-0.5 group-hover:text-foreground" />
			</button>
		</li>
	);
}
