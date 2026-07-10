"use client";

// Search results — the Carbon results screen wired to the real
// /api/browse/search endpoint. Query, filters, and page live in the URL
// (same param scheme as the legacy /browse via lib/search-url.ts) so back
// and share work across both skins. Every rail control maps onto a real
// browseSearch param; facets the endpoint doesn't provide (counts,
// treatment, cited-by) don't appear here — that's the mockup's fiction.
//
// Case hits open /cases/<id>; statute/rule hits open the legacy /browse
// reader.

import { ArrowRightIcon, ListFilterIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
	type ReactNode,
	Suspense,
	useCallback,
	useEffect,
	useState,
} from "react";
import {
	type AdvancedFilters,
	COURT_LABEL,
	DOC_TYPE_LABEL,
	toSearchFilters,
} from "@/components/browse/advanced-search";
import {
	Notification,
	Tag,
	type TagKind,
} from "@/components/carbon/primitives";
import { CarbonSearchBar } from "@/components/carbon/search-bar";
import {
	type BrowseSearchResult,
	type ResearchSearchResponse,
	type ResearchSearchResult,
	researchSearch,
	SEARCH_PAGE_SIZE,
	type SearchFacets,
} from "@/lib/iowa-browse";
import {
	advancedFromParams,
	buildSearchQuery,
	modeFromParams,
	searchFiltersFromParams,
	sortFromParams,
} from "@/lib/search-url";
import { cn } from "@/lib/utils";

// Session-lifetime response cache keyed by the full serialized query string.
// Back/forward navigation (results → case → back) re-mounts this page with
// the same URL; serving the cached response makes that instant and skips
// re-paying the embed/rerank cost for a search the user already ran. The
// corpus only changes via the daily ingest, so within-session staleness is a
// non-issue. Module scope survives client-side route changes; a hard reload
// clears it.
const RESULTS_CACHE = new Map<string, ResearchSearchResponse>();
const RESULTS_CACHE_MAX = 30;

// useSearchParams() must be read inside a Suspense boundary.
export default function V2ResultsPage() {
	return (
		<Suspense
			fallback={
				<div className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
					Loading…
				</div>
			}
		>
			<ResultsScreen />
		</Suspense>
	);
}

function ResultsScreen() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const spStr = searchParams.toString();

	const query = (searchParams.get("q") ?? "").trim();
	const page = Math.max(1, Number(searchParams.get("page")) || 1);
	const filters = advancedFromParams(searchParams);
	const modeOverride = modeFromParams(searchParams);
	const sort = sortFromParams(searchParams);

	const [data, setData] = useState<ResearchSearchResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// The URL is the single source of truth: any change (new query, filter,
	// page, mode override) lands here and re-runs the server search. Everything
	// the effect needs is re-derived from the serialized params, so spStr is
	// the one dep.
	useEffect(() => {
		const sp = new URLSearchParams(spStr);
		const q = (sp.get("q") ?? "").trim();
		if (!q) {
			setData(null);
			return;
		}
		const cached = RESULTS_CACHE.get(spStr);
		if (cached) {
			setData(cached);
			setError(null);
			setLoading(false);
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		researchSearch(
			q,
			searchFiltersFromParams(sp),
			Math.max(1, Number(sp.get("page")) || 1),
			modeFromParams(sp),
			sortFromParams(sp),
		)
			.then((d) => {
				if (cancelled) return;
				setData(d);
				RESULTS_CACHE.set(spStr, d);
				if (RESULTS_CACHE.size > RESULTS_CACHE_MAX) {
					const oldest = RESULTS_CACHE.keys().next().value;
					if (oldest !== undefined) RESULTS_CACHE.delete(oldest);
				}
			})
			.catch((e) => !cancelled && setError((e as Error).message))
			.finally(() => !cancelled && setLoading(false));
		return () => {
			cancelled = true;
		};
	}, [spStr]);

	const pushSearch = useCallback(
		(
			q: string,
			f: AdvancedFilters,
			nextPage = 1,
			nextMode: string | null = modeOverride,
			nextSort: string = sort,
		) => {
			const p = new URLSearchParams(
				buildSearchQuery(q, toSearchFilters(f), nextMode, nextSort),
			);
			if (nextPage > 1) p.set("page", String(nextPage));
			router.push(`/results?${p.toString()}`);
		},
		[router, modeOverride, sort],
	);

	const onFilters = (f: AdvancedFilters) => pushSearch(query, f);
	// A new query drops the mode override — the classifier should get first say.
	const onQuery = (q: string) => pushSearch(q, filters, 1, null);
	const onSort = (s: string) => pushSearch(query, filters, 1, modeOverride, s);

	// Stale = the data on screen answers a different query than the URL asks
	// for. A new query shows skeletons; a refinement of the same query (page,
	// filter, sort) keeps the old rows dimmed, which reads as less jarring.
	const stale = !data || data.query !== query;

	const count = data?.results.length ?? 0;
	const offset = data?.offset ?? 0;
	// `total` shipped after `count`; older cached responses may omit it.
	const total = data?.total;
	const hasMore = data?.has_more ?? false;
	const showPager = !!data && count > 0 && (page > 1 || hasMore);
	const totalPages =
		total !== undefined && total > 0
			? Math.ceil(total / SEARCH_PAGE_SIZE)
			: null;

	return (
		<div className="px-5 py-8 sm:px-8">
			<CarbonSearchBar initial={query} onSearch={onQuery} />

			<div className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
				<h1 className="font-light text-2xl sm:text-3xl">
					{query ? <>Results for &ldquo;{query}&rdquo;</> : "Search the corpus"}
				</h1>
				<p className="text-[var(--cds-helper)] text-sm">
					{loading
						? "Searching the corpus…"
						: !query
							? "Enter a query above."
							: count === 0
								? "No results"
								: data?.total_exact === false
									? `Top ${total?.toLocaleString() ?? count} results · showing ${offset + 1}–${offset + count}`
									: `Showing ${offset + 1}–${offset + count}${
											total !== undefined ? ` of ${total.toLocaleString()}` : ""
										}`}
				</p>
				{data && query && (
					<ModeChip
						data={data}
						override={modeOverride}
						onMode={(m) => pushSearch(query, filters, 1, m)}
					/>
				)}
			</div>

			{data && data.detection?.unsupported?.length > 0 && (
				<div className="mt-4 max-w-2xl">
					<Notification kind="warning" title="Connector not supported yet">
						{data.detection.unsupported.map((u) => u.message).join(" ")}
					</Notification>
				</div>
			)}

			<FilterChips filters={filters} onChange={onFilters} />

			<div className="mt-6 grid gap-10 lg:grid-cols-[17rem_1fr] xl:grid-cols-[19rem_1fr]">
				<RefineRail
					filters={filters}
					onChange={onFilters}
					loading={loading}
					facets={data?.facets ?? null}
				/>

				<div className="min-w-0">
					{data && count > 0 && (
						<div className="mb-3 flex items-center justify-end gap-2">
							<label
								htmlFor="results-sort"
								className="text-[11px] text-[var(--cds-helper)]"
							>
								Sort
							</label>
							<select
								id="results-sort"
								value={sort}
								onChange={(e) => onSort(e.target.value)}
								className="h-8 border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-2 text-[13px] outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
							>
								<option value="relevance">Relevance</option>
								<option value="date_desc">Newest first</option>
								<option value="date_asc">Oldest first</option>
							</select>
						</div>
					)}
					{error ? (
						<Notification kind="error" title="Search failed">
							{error}
						</Notification>
					) : !query ? (
						<div className="border border-[var(--cds-border)] px-6 py-14 text-center text-[var(--cds-text-2)] text-sm">
							Type a query to search {`case law, statutes, and rules`}.
						</div>
					) : loading && stale ? (
						<SkeletonResults />
					) : !data || data.results.length === 0 ? (
						<div className="border border-[var(--cds-border)] px-6 py-14 text-center text-[var(--cds-text-2)] text-sm">
							No matches for <span className="font-mono">“{query}”</span>.
						</div>
					) : (
						<>
							<div
								className={cn(
									"divide-y divide-[var(--cds-border)] border border-[var(--cds-border)] transition-opacity",
									loading && "opacity-60",
								)}
							>
								{data.results.map((r, i) => (
									<ResultRow
										// biome-ignore lint/suspicious/noArrayIndexKey: the pinned exact-citation hit can repeat a node_id
										key={`${r.node_id}-${i}`}
										r={r}
										query={query}
									/>
								))}
							</div>
							{showPager && (
								<div className="flex items-center justify-between border border-[var(--cds-border)] border-t-0">
									<button
										type="button"
										disabled={page <= 1}
										onClick={() => pushSearch(query, filters, page - 1)}
										className={cn(
											"h-11 px-4 text-sm",
											page <= 1
												? "cursor-not-allowed text-[var(--cds-helper)]"
												: "text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)]",
										)}
									>
										Previous
									</button>
									<span className="font-mono text-[var(--cds-helper)] text-xs tabular-nums">
										Page {page}
										{totalPages !== null && ` of ${totalPages}`}
									</span>
									<button
										type="button"
										disabled={!hasMore}
										onClick={() => pushSearch(query, filters, page + 1)}
										className={cn(
											"flex h-11 items-center gap-3 px-4 text-sm",
											!hasMore
												? "cursor-not-allowed text-[var(--cds-helper)]"
												: "text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)]",
										)}
									>
										Next
										<ArrowRightIcon className="size-4" />
									</button>
								</div>
							)}
						</>
					)}
				</div>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Skeleton rows — shown while a NEW query is in flight (a refinement of the
// same query keeps the previous rows dimmed instead). Shapes mirror
// ResultRow: tag line, title, citation line, two snippet lines.
// ---------------------------------------------------------------------------

function SkeletonResults() {
	return (
		<output
			aria-label="Searching the corpus"
			className="block divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]"
		>
			{Array.from({ length: 5 }, (_, i) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: static placeholder list
				<div key={i} className="animate-pulse bg-[var(--cds-layer)] p-4 sm:p-5">
					<div className="flex items-center gap-2">
						<div className="h-5 w-14 bg-[var(--cds-layer-hover)]" />
						<div className="h-3 w-20 bg-[var(--cds-layer-hover)]" />
					</div>
					<div className="mt-3 h-4 w-3/5 bg-[var(--cds-layer-hover)]" />
					<div className="mt-2 h-3 w-2/5 bg-[var(--cds-layer-hover)]" />
					<div className="mt-3 h-3 w-full max-w-3xl bg-[var(--cds-layer-hover)]" />
					<div className="mt-1.5 h-3 w-4/5 max-w-3xl bg-[var(--cds-layer-hover)]" />
				</div>
			))}
		</output>
	);
}

// ---------------------------------------------------------------------------
// Mode chip — shows how the server routed the query (terms & connectors vs
// natural language vs citation), with a one-click override. Westlaw-Precision
// style: auto-detect by default, the chip makes the routing visible and
// reversible. Implementation words ("vector", "semantic") never appear.
// ---------------------------------------------------------------------------

const MODE_LABEL: Record<string, { label: string; kind: TagKind }> = {
	boolean: { label: "Terms & connectors", kind: "blue" },
	natural: { label: "Natural language", kind: "gray" },
	citation: { label: "Citation", kind: "green" },
};

function ModeChip({
	data,
	override,
	onMode,
}: {
	data: ResearchSearchResponse;
	override: string | null;
	onMode: (mode: string | null) => void;
}) {
	const spec = MODE_LABEL[data.mode];
	if (!spec) return null;
	// The sensible alternate route for one click. Citation mode offers none —
	// overriding a pinned exact lookup is never what the user wants.
	const alternate =
		data.mode === "boolean"
			? { mode: "natural", label: "Search as natural language" }
			: data.mode === "natural"
				? { mode: "tc", label: "Search as terms & connectors" }
				: null;
	return (
		<span className="flex items-baseline gap-2">
			<Tag kind={spec.kind}>{spec.label}</Tag>
			{alternate && (
				<button
					type="button"
					onClick={() => onMode(alternate.mode)}
					className="text-[var(--cds-link)] text-xs transition-colors hover:underline"
				>
					{alternate.label}
				</button>
			)}
			{override && (
				<button
					type="button"
					onClick={() => onMode(null)}
					className="text-[var(--cds-helper)] text-xs transition-colors hover:underline"
					title="Let the query decide the mode"
				>
					Auto
				</button>
			)}
		</span>
	);
}

// ---------------------------------------------------------------------------
// Active-filter chips — built from AdvancedFilters so they mirror the rail.
// ---------------------------------------------------------------------------

function FilterChips({
	filters,
	onChange,
}: {
	filters: AdvancedFilters;
	onChange: (f: AdvancedFilters) => void;
}) {
	const chips: { key: string; label: string; clear: () => void }[] = [];
	if (filters.docType !== "all")
		chips.push({
			key: "doc_type",
			label: DOC_TYPE_LABEL[filters.docType] ?? filters.docType,
			clear: () => onChange({ ...filters, docType: "all" }),
		});
	if (caselawScoped(filters.docType)) {
		if (filters.court)
			chips.push({
				key: "court",
				label: COURT_LABEL[filters.court] ?? filters.court,
				clear: () => onChange({ ...filters, court: "" }),
			});
		if (filters.status)
			chips.push({
				key: "status",
				label: filters.status,
				clear: () => onChange({ ...filters, status: "" }),
			});
		if (filters.yearFrom || filters.yearTo)
			chips.push({
				key: "year",
				label: `${filters.yearFrom || "earliest"}–${filters.yearTo || "latest"}`,
				clear: () => onChange({ ...filters, yearFrom: "", yearTo: "" }),
			});
	}
	if (chips.length === 0) return null;

	return (
		<div className="mt-3 flex flex-wrap items-center gap-2">
			<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]">
				Filters
			</span>
			{chips.map((c) => (
				<span
					key={c.key}
					className="inline-flex h-6 items-center gap-1.5 bg-[var(--cds-layer-selected)] px-2 text-xs"
				>
					{c.label}
					<button
						type="button"
						aria-label={`Remove ${c.label} filter`}
						onClick={c.clear}
						className="hover:opacity-70"
					>
						<XIcon className="size-3" />
					</button>
				</span>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Refine rail — every control maps onto a real browseSearch param.
// ---------------------------------------------------------------------------

const DOC_TYPES: { id: AdvancedFilters["docType"]; label: string }[] = [
	{ id: "all", label: "All content" },
	{ id: "cases", label: "Cases" },
	{ id: "code", label: "Iowa Code" },
	{ id: "admin", label: "Iowa Admin. Code" },
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

// Court/status/year only mean anything for caselaw (the backend treats any
// caselaw filter as a scope override), so they're disabled outside cases/all.
function caselawScoped(docType: AdvancedFilters["docType"]): boolean {
	return docType === "all" || docType === "cases";
}

// doc_type facet slugs (backend counts by source slug) → rail option ids.
const SLUG_TO_DOC_TYPE: Record<string, AdvancedFilters["docType"]> = {
	"iowa-caselaw": "cases",
	"iowa-code": "code",
	"iowa-admin-code": "admin",
	"iowa-court-rules": "rules",
};

function RefineRail({
	filters,
	onChange,
	loading,
	facets,
}: {
	filters: AdvancedFilters;
	onChange: (f: AdvancedFilters) => void;
	loading: boolean;
	facets: SearchFacets | null;
}) {
	const casesScoped = caselawScoped(filters.docType);
	const docTypeCounts: Partial<Record<string, number>> = {};
	if (facets) {
		let all = 0;
		for (const d of facets.doc_types) {
			const id = SLUG_TO_DOC_TYPE[d.slug];
			if (id) docTypeCounts[id] = d.count;
			all += d.count;
		}
		docTypeCounts.all = all;
	}
	const courtCounts = Object.fromEntries(
		(facets?.courts ?? []).map((c) => [c.court_id, c.count]),
	);
	const statusCounts = Object.fromEntries(
		(facets?.statuses ?? []).map((s) => [s.status, s.count]),
	);
	// Switching to code/rules clears the caselaw-only fields so a stale court
	// or year can't linger behind a disabled control and re-scope the search.
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
		<aside className={cn(loading && "pointer-events-none opacity-60")}>
			<div className="flex items-center gap-2 border-[var(--cds-border)] border-b pb-3">
				<ListFilterIcon className="size-4 text-[var(--cds-text-2)]" />
				<h2 className="font-semibold text-sm">Refine results</h2>
			</div>
			{facets?.basis === "top_results" && (
				<p className="pt-2 text-[11px] text-[var(--cds-helper)] leading-snug">
					Counts reflect the top results.
				</p>
			)}

			<RailSection title="Content type">
				{DOC_TYPES.map((d) => (
					<FacetRow
						key={d.id}
						label={d.label}
						count={docTypeCounts[d.id]}
						active={filters.docType === d.id}
						onClick={() => setDocType(d.id)}
					/>
				))}
			</RailSection>

			<RailSection title="Court">
				{COURTS.map((c) => (
					<FacetRow
						key={c.value || "any-court"}
						label={c.label}
						count={c.value ? courtCounts[c.value] : undefined}
						active={(filters.court || "") === c.value}
						disabled={!casesScoped}
						onClick={() => onChange({ ...filters, court: c.value })}
					/>
				))}
			</RailSection>

			<RailSection title="Status">
				{STATUSES.map((s) => (
					<FacetRow
						key={s.value || "any-status"}
						label={s.label}
						count={s.value ? statusCounts[s.value] : undefined}
						active={(filters.status || "") === s.value}
						disabled={!casesScoped}
						onClick={() => onChange({ ...filters, status: s.value })}
					/>
				))}
			</RailSection>

			<RailSection title="Decided year">
				<YearRange
					filters={filters}
					onChange={onChange}
					disabled={!casesScoped}
				/>
				{casesScoped && (facets?.decades?.length ?? 0) > 0 && (
					<DecadeHistogram
						decades={facets?.decades ?? []}
						onPick={(decade) =>
							onChange({
								...filters,
								yearFrom: decade,
								yearTo: String(Number(decade) + 9),
							})
						}
					/>
				)}
				<p className="mt-2 pl-3 text-[11px] text-[var(--cds-helper)] leading-snug">
					Court, status, and year apply to cases.
				</p>
			</RailSection>
		</aside>
	);
}

// Decade bars under the year inputs — the results-v2 mockup's date histogram,
// fed by real facet counts. Clicking a bar sets the year range to that decade.
function DecadeHistogram({
	decades,
	onPick,
}: {
	decades: { decade: string; count: number }[];
	onPick: (decade: string) => void;
}) {
	const max = Math.max(...decades.map((d) => d.count), 1);
	// Most recent first — that's where the action is.
	const rows = [...decades].sort((a, b) => b.decade.localeCompare(a.decade));
	return (
		<div className="mt-3 space-y-1">
			{rows.map((d) => (
				<button
					key={d.decade}
					type="button"
					onClick={() => onPick(d.decade)}
					title={`${d.count.toLocaleString()} in the ${d.decade}s`}
					className="group flex w-full items-center gap-2 text-left"
				>
					<span className="w-10 shrink-0 font-mono text-[11px] text-[var(--cds-text-2)] tabular-nums group-hover:text-[var(--cds-text)]">
						{d.decade}s
					</span>
					<span className="h-3 flex-1 overflow-hidden">
						<span
							className="block h-full bg-[#0f62fe]/30 transition-colors group-hover:bg-[#0f62fe]/60"
							style={{ width: `${Math.max(2, (d.count / max) * 100)}%` }}
						/>
					</span>
					<span className="w-9 shrink-0 text-right font-mono text-[10px] text-[var(--cds-helper)] tabular-nums">
						{d.count.toLocaleString()}
					</span>
				</button>
			))}
		</div>
	);
}

function RailSection({
	title,
	children,
}: {
	title: string;
	children: ReactNode;
}) {
	return (
		<section className="border-[var(--cds-border)] border-b pb-5">
			<h3 className="pt-5 pb-3 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				{title}
			</h3>
			{children}
		</section>
	);
}

function FacetRow({
	label,
	count,
	active,
	disabled,
	onClick,
}: {
	label: string;
	count?: number;
	active?: boolean;
	disabled?: boolean;
	onClick?: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			disabled={disabled}
			className={cn(
				"flex w-full items-center gap-2.5 border-l-[3px] py-1.5 pl-3 text-left text-sm transition-colors",
				disabled && "cursor-not-allowed opacity-40",
				active
					? "border-[#0f62fe] font-semibold"
					: "border-transparent text-[var(--cds-text-2)]",
				!disabled && !active && "hover:text-[var(--cds-text)]",
			)}
		>
			<span className="min-w-0 flex-1 truncate">{label}</span>
			{count !== undefined && (
				<span className="shrink-0 font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
					{count.toLocaleString()}
				</span>
			)}
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
		"h-9 w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-3 font-mono text-[13px] tabular-nums outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe] disabled:cursor-not-allowed disabled:opacity-40";

	return (
		<div className="grid grid-cols-2 gap-3">
			<label className="block">
				<span className="mb-1 block text-[11px] text-[var(--cds-helper)]">
					From
				</span>
				<input
					inputMode="numeric"
					placeholder="1839"
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
			</label>
			<label className="block">
				<span className="mb-1 block text-[11px] text-[var(--cds-helper)]">
					To
				</span>
				<input
					inputMode="numeric"
					placeholder="2026"
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
			</label>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Result rows
// ---------------------------------------------------------------------------

// Split the snippet/title on the query terms and wrap matches in <mark>. The
// text renders as plain JSX children, so React auto-escapes every fragment —
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
			// biome-ignore lint/suspicious/noArrayIndexKey: static split output
			<mark key={i} className="bg-[#0f62fe]/20 text-inherit">
				{part}
			</mark>
		) : (
			part
		),
	);
}

const KIND_TAG: Record<BrowseSearchResult["kind"], TagKind> = {
	case: "blue",
	code: "gray",
	rule: "gray",
	admin: "gray",
};

const KIND_LABEL: Record<BrowseSearchResult["kind"], string> = {
	case: "Case",
	code: "Iowa Code",
	rule: "Court Rules",
	admin: "Iowa Admin. Code",
};

// Treatment badge styling by citator status. Labels arrive kebab-case
// ("superseded-by-statute") — prettify for display.
function treatmentTag(t: NonNullable<ResearchSearchResult["treatment"]>) {
	const kind: TagKind = t.status === "negative" ? "red" : "yellow";
	const label = (t.label || t.status).replace(/-/g, " ");
	return (
		<Tag kind={kind}>
			<span className="capitalize">{label}</span>
		</Tag>
	);
}

// Server-provided highlight segments (the terms the engine actually matched)
// rendered as plain text nodes — no HTML ever crosses this boundary.
function renderSegments(segments: { text: string; hit: boolean }[]): ReactNode {
	return segments.map((s, i) =>
		s.hit ? (
			// biome-ignore lint/suspicious/noArrayIndexKey: static server output
			<mark key={i} className="bg-[#0f62fe]/20 text-inherit">
				{s.text}
			</mark>
		) : (
			s.text
		),
	);
}

function ResultRow({ r, query }: { r: ResearchSearchResult; query: string }) {
	const isCase = r.kind === "case";
	const year = isCase ? (r.date_filed || "").slice(0, 4) : "";
	const context = isCase
		? [
				r.court_name,
				year,
				r.cited_by ? `Cited by ${r.cited_by.toLocaleString()}` : "",
			]
				.filter(Boolean)
				.join(" · ")
		: r.chapter
			? `Chapter ${r.chapter.ordinal}${r.chapter.heading ? ` — ${r.chapter.heading}` : ""}`
			: r.source;
	const cite = isCase ? r.citations.join(" · ") : r.citation;
	// Both hit kinds open in-app readers: decisions in /case, sections in
	// /section. The query rides along so the reader can highlight the terms
	// that produced this hit and jump to the first match.
	const hl = query ? `?q=${encodeURIComponent(query)}` : "";
	const href =
		isCase && r.case_id != null
			? `/case/${r.case_id}${hl}`
			: `/section/${r.node_id}${hl}`;
	const title = isCase
		? r.case_name || r.heading || "(unnamed case)"
		: r.heading || "(no heading)";

	return (
		<article className="group bg-[var(--cds-layer)] p-4 transition-colors hover:bg-[var(--cds-layer-hover)] sm:p-5">
			<div className="flex flex-wrap items-center gap-2">
				<Tag kind={KIND_TAG[r.kind] ?? "gray"}>
					{KIND_LABEL[r.kind] ?? r.kind}
				</Tag>
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					{r.type}
				</span>
				{r.exact && <Tag kind="blue">Exact match</Tag>}
				{r.treatment && treatmentTag(r.treatment)}
			</div>

			<h3 className="mt-2.5">
				<Link
					href={href}
					className="font-semibold text-[15px] hover:text-[var(--cds-link)] hover:underline"
				>
					{!isCase && (
						<span className="mr-2 font-mono text-sm tabular-nums">
							{r.citation.trim().split(/\s+/).pop()}
						</span>
					)}
					{highlight(title, query)}
				</Link>
			</h3>
			<p className="mt-0.5 text-[13px] text-[var(--cds-text-2)]">
				{cite && <span className="font-mono">{cite}</span>}
				{cite && context && (
					<span className="mx-2 text-[var(--cds-helper)]">·</span>
				)}
				{context}
			</p>

			{(r.snippet_segments?.length || r.snippet) && (
				<p className="mt-2 line-clamp-3 max-w-3xl text-[var(--cds-text-2)] text-sm leading-relaxed">
					{r.snippet_segments?.length
						? renderSegments(r.snippet_segments)
						: highlight(r.snippet, query)}
				</p>
			)}
		</article>
	);
}
