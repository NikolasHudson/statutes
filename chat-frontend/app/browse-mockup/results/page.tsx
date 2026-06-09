"use client";

// Design mockup for a redesigned search-results page (/browse-mockup/results).
// Full-window layout: a slim icon-only app rail, then the result "refine"
// sidebar (facets) where the app sidebar normally sits, then the results filling
// the entire remaining width — no centered max-width column. Same research-tool
// language as the other mockups (dense, high-contrast, royal accent — the
// app-wide light theme). Rows use the REAL fields the search endpoint returns today
// (apps/api/browse.py _search_row): kind, case_name, court_name, date_filed,
// citations[], type, citation, source, chapter, heading, snippet, exact. The
// search response has no grand total and no facets (only count=page-size +
// has_more), so the counts/total here are derived/illustrative; and the row has
// no precedential_status today (only the case-list endpoint does), so `status`
// is mock and flagged for a possible backend add.

import {
	ArrowUpDownIcon,
	BookmarkPlusIcon,
	BookOpenIcon,
	CheckIcon,
	ChevronLeftIcon,
	ChevronRightIcon,
	CircleUserIcon,
	GavelIcon,
	LandmarkIcon,
	LibraryBigIcon,
	ListFilterIcon,
	type LucideIcon,
	MessagesSquareIcon,
	ScaleIcon,
	SearchIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Result model — mirrors apps/api/browse.py _search_row (+ a flagged `status`)
// ---------------------------------------------------------------------------

type Kind = "case" | "code" | "rule";

type Result = {
	node_id: number;
	kind: Kind;
	case_id: number | null;
	case_name: string | null;
	court_name: string;
	date_filed: string; // ISO; "" for statutes/rules
	citations: string[];
	type: string; // node-type label, e.g. "Section" | "Opinion" | "Rule"
	citation: string; // full citation, e.g. "Iowa Code § 714.16"
	source: string;
	source_slug: string;
	chapter: { ordinal: string; heading: string } | null;
	heading: string;
	snippet: string;
	exact: boolean;
	// DEMO ONLY — not in the real search row (see file header).
	status?: "Published" | "Unpublished";
};

// Representative results for q="consumer fraud" — real field shapes, plausible
// Iowa content. Snippets are plain text (the server HTML-escapes them).
const RESULTS: Result[] = [
	{
		node_id: 10714,
		kind: "code",
		case_id: null,
		case_name: null,
		court_name: "",
		date_filed: "",
		citations: ["Iowa Code § 714.16"],
		type: "Section",
		citation: "Iowa Code § 714.16",
		source: "Iowa Code",
		source_slug: "iowa-code",
		chapter: { ordinal: "714", heading: "Theft, Fraud, and Related Offenses" },
		heading: "Consumer frauds",
		snippet:
			"The act, use or employment by a person of an unfair practice, deception, fraud, false pretense, or misrepresentation in connection with the lending of money or the sale or advertisement of merchandise is an unlawful consumer fraud practice.",
		exact: true,
	},
	{
		node_id: 50231,
		kind: "case",
		case_id: 50231,
		case_name: "State ex rel. Miller v. Vertrue, Inc.",
		court_name: "Supreme Court of Iowa",
		date_filed: "2013-06-21",
		citations: ["834 N.W.2d 12"],
		type: "Opinion",
		citation: "State ex rel. Miller v. Vertrue, Inc.",
		source: "Iowa Caselaw",
		source_slug: "iowa-caselaw",
		chapter: null,
		heading: "State ex rel. Miller v. Vertrue, Inc.",
		snippet:
			"The Consumer Fraud Act authorizes the attorney general to seek civil penalties and reimbursement for deceptive membership-program practices directed at Iowa consumers.",
		exact: false,
		status: "Published",
	},
	{
		node_id: 10715,
		kind: "code",
		case_id: null,
		case_name: null,
		court_name: "",
		date_filed: "",
		citations: ["Iowa Code § 714.16A"],
		type: "Section",
		citation: "Iowa Code § 714.16A",
		source: "Iowa Code",
		source_slug: "iowa-code",
		chapter: { ordinal: "714", heading: "Theft, Fraud, and Related Offenses" },
		heading:
			"Additional civil penalty for consumer frauds against older persons",
		snippet:
			"If a person violates section 714.16 and the violation is committed against an older person, the attorney general may seek an additional civil penalty not to exceed five thousand dollars per violation.",
		exact: false,
	},
	{
		node_id: 50544,
		kind: "case",
		case_id: 50544,
		case_name: "State v. Hagen",
		court_name: "Supreme Court of Iowa",
		date_filed: "2019-04-12",
		citations: ["925 N.W.2d 598"],
		type: "Opinion",
		citation: "State v. Hagen",
		source: "Iowa Caselaw",
		source_slug: "iowa-caselaw",
		chapter: null,
		heading: "State v. Hagen",
		snippet:
			"We conclude the defendant's conduct in soliciting prepayment for home-repair work he never performed constituted a consumer fraud practice under chapter 714.",
		exact: false,
		status: "Published",
	},
	{
		node_id: 50890,
		kind: "case",
		case_id: 50890,
		case_name: "Molo Oil Co. v. River City Ford Truck Sales",
		court_name: "Court of Appeals of Iowa",
		date_filed: "2021-09-01",
		citations: ["965 N.W.2d 200"],
		type: "Opinion",
		citation: "Molo Oil Co. v. River City Ford Truck Sales",
		source: "Iowa Caselaw",
		source_slug: "iowa-caselaw",
		chapter: null,
		heading: "Molo Oil Co. v. River City Ford Truck Sales",
		snippet:
			"Plaintiff argues a private right of action for consumer fraud exists where a buyer suffers an ascertainable loss caused by the seller's misrepresentation.",
		exact: false,
		status: "Unpublished",
	},
	{
		node_id: 10980,
		kind: "code",
		case_id: null,
		case_name: null,
		court_name: "",
		date_filed: "",
		citations: ["Iowa Code § 714H.3"],
		type: "Section",
		citation: "Iowa Code § 714H.3",
		source: "Iowa Code",
		source_slug: "iowa-code",
		chapter: {
			ordinal: "714H",
			heading: "Private Right of Action for Consumer Frauds",
		},
		heading: "Private cause of action",
		snippet:
			"A consumer who suffers an ascertainable loss of money or property as the result of a prohibited practice may bring an action to recover actual damages.",
		exact: false,
	},
	{
		node_id: 50912,
		kind: "case",
		case_id: 50912,
		case_name: "State v. Brown",
		court_name: "Court of Appeals of Iowa",
		date_filed: "2020-02-19",
		citations: ["939 N.W.2d 661"],
		type: "Opinion",
		citation: "State v. Brown",
		source: "Iowa Caselaw",
		source_slug: "iowa-caselaw",
		chapter: null,
		heading: "State v. Brown",
		snippet:
			"The consumer fraud statute requires proof of an ascertainable loss; speculative or unrealized harm will not support recovery under the chapter.",
		exact: false,
		status: "Unpublished",
	},
	{
		node_id: 30122,
		kind: "rule",
		case_id: null,
		case_name: null,
		court_name: "",
		date_filed: "",
		citations: ["Iowa R. Civ. P. 1.261"],
		type: "Rule",
		citation: "Iowa R. Civ. P. 1.261",
		source: "Iowa Court Rules",
		source_slug: "iowa-court-rules",
		chapter: { ordinal: "1", heading: "Rules of Civil Procedure" },
		heading: "Class actions — prerequisites",
		snippet:
			"One or more members of a class may sue as representative parties where common questions — such as a uniform consumer fraud practice — predominate over individual issues.",
		exact: false,
	},
];

// Illustrative total — the API returns has_more, not a grand count.
const MOCK_TOTAL = 1284;

const CONTENT_TYPES: { id: "all" | Kind; label: string }[] = [
	{ id: "all", label: "All content" },
	{ id: "case", label: "Cases" },
	{ id: "code", label: "Statutes & Codes" },
	{ id: "rule", label: "Court Rules" },
];

const SORTS = [
	{ id: "relevance", label: "Relevance" },
	{ id: "newest", label: "Most recent" },
	{ id: "oldest", label: "Oldest first" },
] as const;
type SortId = (typeof SORTS)[number]["id"];

const KIND: Record<Kind, { label: string; icon: LucideIcon; tint: string }> = {
	case: { label: "Case", icon: ScaleIcon, tint: "bg-primary/10 text-primary" },
	code: {
		label: "Statute",
		icon: LandmarkIcon,
		tint: "bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
	},
	rule: {
		label: "Court Rule",
		icon: GavelIcon,
		tint: "bg-amber-600/10 text-amber-700 dark:text-amber-400",
	},
};

const MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
const yearOf = (iso: string) => (iso ? iso.slice(0, 4) : "");
function fmtDate(iso: string): string {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
	return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : "";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsMockupPage() {
	return (
		<Suspense fallback={null}>
			<ResultsInner />
		</Suspense>
	);
}

function ResultsInner() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const [query, setQuery] = useState(
		() => searchParams.get("q") ?? "consumer fraud",
	);
	const [draft, setDraft] = useState(query);

	const [type, setType] = useState<"all" | Kind>("all");
	const [court, setCourt] = useState("");
	const [status, setStatus] = useState("");
	const [yearFrom, setYearFrom] = useState(0);
	const [sort, setSort] = useState<SortId>("relevance");

	const hasFilters = type !== "all" || court || status || yearFrom > 0;
	const clearFilters = () => {
		setType("all");
		setCourt("");
		setStatus("");
		setYearFrom(0);
	};

	// Counts for the refine rail, derived from the data (the API has no facets).
	const counts = useMemo(() => {
		const by = (pred: (r: Result) => boolean) => RESULTS.filter(pred).length;
		return {
			all: RESULTS.length,
			case: by((r) => r.kind === "case"),
			code: by((r) => r.kind === "code"),
			rule: by((r) => r.kind === "rule"),
			iowa: by((r) => r.court_name === "Supreme Court of Iowa"),
			iowactapp: by((r) => r.court_name === "Court of Appeals of Iowa"),
			published: by((r) => r.status === "Published"),
			unpublished: by((r) => r.status === "Unpublished"),
		};
	}, []);

	const filtered = useMemo(() => {
		let rows = RESULTS.filter((r) => {
			if (type !== "all" && r.kind !== type) return false;
			if (court && r.court_name !== court) return false;
			if (status && r.status !== status) return false;
			if (
				yearFrom > 0 &&
				(!r.date_filed || Number(yearOf(r.date_filed)) < yearFrom)
			)
				return false;
			return true;
		});
		if (sort !== "relevance") {
			rows = [...rows].sort((a, b) => {
				const da = a.date_filed || "";
				const db = b.date_filed || "";
				if (!da && !db) return 0;
				if (!da) return 1;
				if (!db) return -1;
				return sort === "newest" ? db.localeCompare(da) : da.localeCompare(db);
			});
		}
		return rows;
	}, [type, court, status, yearFrom, sort]);

	const submit = () => setQuery(draft.trim() || query);
	const open = (r: Result) => {
		if (r.kind === "case" && r.case_id != null)
			router.push(`/cases/${r.case_id}`);
		else router.push(`/browse#/${r.source_slug}/${citeTail(r.citation)}`);
	};

	return (
		<div className="flex h-dvh w-full overflow-hidden">
			<IconRail />

			{/* Refine sidebar — sits where the app sidebar normally would. */}
			<aside className="hidden w-60 shrink-0 flex-col border-r bg-card lg:flex">
				<div className="flex h-14 shrink-0 items-center justify-between border-b px-3">
					<span className="flex items-center gap-1.5 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
						<ListFilterIcon className="size-3.5" />
						Refine
					</span>
					{hasFilters && (
						<button
							type="button"
							onClick={clearFilters}
							className="text-[11px] text-primary hover:underline"
						>
							Clear all
						</button>
					)}
				</div>
				<div className="min-w-0 flex-1 divide-y overflow-y-auto">
					<FacetGroup title="Content type">
						{CONTENT_TYPES.map((t) => (
							<Facet
								key={t.id}
								label={t.label}
								count={counts[t.id]}
								selected={type === t.id}
								onClick={() => setType(t.id)}
							/>
						))}
					</FacetGroup>

					<FacetGroup title="Court">
						<Facet
							label="Any court"
							selected={court === ""}
							onClick={() => setCourt("")}
						/>
						<Facet
							label="Supreme Court of Iowa"
							count={counts.iowa}
							selected={court === "Supreme Court of Iowa"}
							onClick={() => setCourt("Supreme Court of Iowa")}
						/>
						<Facet
							label="Court of Appeals of Iowa"
							count={counts.iowactapp}
							selected={court === "Court of Appeals of Iowa"}
							onClick={() => setCourt("Court of Appeals of Iowa")}
						/>
					</FacetGroup>

					<FacetGroup title="Status">
						<Facet
							label="Any status"
							selected={status === ""}
							onClick={() => setStatus("")}
						/>
						<Facet
							label="Published"
							count={counts.published}
							selected={status === "Published"}
							onClick={() => setStatus("Published")}
						/>
						<Facet
							label="Unpublished"
							count={counts.unpublished}
							selected={status === "Unpublished"}
							onClick={() => setStatus("Unpublished")}
						/>
					</FacetGroup>

					<FacetGroup title="Date decided">
						{[
							{ label: "Any time", from: 0 },
							{ label: "Since 2020", from: 2020 },
							{ label: "Since 2015", from: 2015 },
							{ label: "Since 2010", from: 2010 },
						].map((d) => (
							<Facet
								key={d.label}
								label={d.label}
								selected={yearFrom === d.from}
								onClick={() => setYearFrom(d.from)}
							/>
						))}
					</FacetGroup>
				</div>
			</aside>

			{/* Results — fills the entire remaining width. */}
			<main className="flex min-w-0 flex-1 flex-col">
				{/* Top bar: breadcrumb + search */}
				<div className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
					<div className="hidden items-center gap-2 text-sm md:flex">
						<Link
							href="/browse-mockup"
							className="text-muted-foreground hover:text-foreground"
						>
							Library
						</Link>
						<ChevronRightIcon className="size-3.5 text-muted-foreground/50" />
						<span className="font-medium">Search results</span>
					</div>
					<form
						className="ml-auto flex w-full max-w-2xl items-stretch rounded-lg border bg-card shadow-xs transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50"
						onSubmit={(e) => {
							e.preventDefault();
							submit();
						}}
					>
						<div className="relative flex flex-1 items-center">
							<SearchIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
							<input
								value={draft}
								onChange={(e) => setDraft(e.target.value)}
								aria-label="Search the library"
								className="h-9 w-full bg-transparent pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground"
							/>
						</div>
						<div className="flex items-center p-1">
							<Button type="submit" size="sm" className="h-7 gap-1.5 px-3">
								<SearchIcon className="size-3.5" />
								<span className="hidden sm:inline">Search</span>
							</Button>
						</div>
					</form>
				</div>

				{/* Scrollable results */}
				<div className="min-w-0 flex-1 overflow-y-auto">
					{/* Sticky results toolbar */}
					<div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b bg-background/95 px-5 py-3 backdrop-blur">
						<div className="min-w-0">
							<h1 className="truncate font-semibold text-lg tracking-tight">
								Results for{" "}
								<span className="text-primary">&ldquo;{query}&rdquo;</span>
							</h1>
							<p className="text-muted-foreground text-xs">
								Showing 1–{filtered.length} of {MOCK_TOTAL.toLocaleString()}
							</p>
						</div>
						<div className="flex items-center gap-2">
							<Button variant="outline" size="sm">
								<BookmarkPlusIcon className="size-3.5" />
								<span className="hidden sm:inline">Save search</span>
							</Button>
							<label className="flex items-center gap-1.5 rounded-md border bg-card px-2 text-muted-foreground text-xs">
								<ArrowUpDownIcon className="size-3.5" />
								<select
									value={sort}
									onChange={(e) => setSort(e.target.value as SortId)}
									aria-label="Sort results"
									className="h-8 cursor-pointer bg-transparent pr-1 font-medium text-foreground outline-none"
								>
									{SORTS.map((s) => (
										<option key={s.id} value={s.id}>
											{s.label}
										</option>
									))}
								</select>
							</label>
						</div>
					</div>

					<div className="px-5 py-4">
						{/* Active filter chips */}
						{hasFilters && (
							<div className="mb-2 flex flex-wrap items-center gap-1.5">
								{type !== "all" && (
									<FilterChip onClear={() => setType("all")}>
										{CONTENT_TYPES.find((t) => t.id === type)?.label}
									</FilterChip>
								)}
								{court && (
									<FilterChip onClear={() => setCourt("")}>{court}</FilterChip>
								)}
								{status && (
									<FilterChip onClear={() => setStatus("")}>
										{status}
									</FilterChip>
								)}
								{yearFrom > 0 && (
									<FilterChip onClear={() => setYearFrom(0)}>
										Since {yearFrom}
									</FilterChip>
								)}
							</div>
						)}

						{filtered.length === 0 ? (
							<div className="mt-6 rounded-lg border border-dashed bg-card px-4 py-12 text-center text-muted-foreground text-sm">
								No results match these filters.
							</div>
						) : (
							<>
								<ul className="divide-y">
									{filtered.map((r) => (
										<li key={r.node_id}>
											<ResultRow result={r} query={query} onOpen={open} />
										</li>
									))}
								</ul>

								{/* Pager (illustrative — API paginates via has_more) */}
								<div className="mt-4 flex items-center justify-between border-t pt-4">
									<Button variant="outline" size="sm" disabled>
										<ChevronLeftIcon className="size-4" /> Previous
									</Button>
									<div className="flex items-center gap-1">
										{[1, 2, 3, 4, 5].map((n) => (
											<button
												key={n}
												type="button"
												className={cn(
													"size-8 rounded-md text-[13px] tabular-nums transition-colors",
													n === 1
														? "bg-primary font-medium text-primary-foreground"
														: "text-muted-foreground hover:bg-accent hover:text-foreground",
												)}
											>
												{n}
											</button>
										))}
										<span className="px-1 text-muted-foreground text-xs">
											… 129
										</span>
									</div>
									<Button variant="outline" size="sm">
										Next <ChevronRightIcon className="size-4" />
									</Button>
								</div>
							</>
						)}
					</div>
				</div>
			</main>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Slim icon-only app rail
// ---------------------------------------------------------------------------

function IconRail() {
	return (
		<nav className="flex w-14 shrink-0 flex-col items-center gap-1 border-r bg-sidebar py-3">
			<Link
				href="/browse-mockup"
				aria-label="Library home"
				className="mb-1 flex size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground"
			>
				<BookOpenIcon className="size-4.5" />
			</Link>
			<div className="my-1 h-px w-7 bg-sidebar-border" />
			<RailIcon href="/" icon={MessagesSquareIcon} label="Chat" />
			<RailIcon
				href="/browse-mockup"
				icon={LibraryBigIcon}
				label="Library"
				active
			/>
			<RailIcon
				href="/browse-mockup/advanced"
				icon={SlidersHorizontalIcon}
				label="Advanced search"
			/>
			<div className="flex-1" />
			<RailIcon href="/account" icon={CircleUserIcon} label="Account" />
		</nav>
	);
}

function RailIcon({
	href,
	icon: Icon,
	label,
	active,
}: {
	href: string;
	icon: LucideIcon;
	label: string;
	active?: boolean;
}) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Link
					href={href}
					aria-label={label}
					className={cn(
						"flex size-9 items-center justify-center rounded-lg transition-colors",
						active
							? "bg-primary/10 text-primary"
							: "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
					)}
				>
					<Icon className="size-[18px]" />
				</Link>
			</TooltipTrigger>
			<TooltipContent side="right">{label}</TooltipContent>
		</Tooltip>
	);
}

// ---------------------------------------------------------------------------
// Result row
// ---------------------------------------------------------------------------

function ResultRow({
	result: r,
	query,
	onOpen,
}: {
	result: Result;
	query: string;
	onOpen: (r: Result) => void;
}) {
	const k = KIND[r.kind];
	const Icon = k.icon;
	const title = r.kind === "case" ? (r.case_name ?? r.heading) : r.heading;
	// Citation rides with the title: the reporter cite for cases, the code/rule
	// cite otherwise. The trailing context is the court (cases) or chapter.
	const cite = r.kind === "case" ? r.citations.join("  ·  ") : r.citation;
	const context =
		r.kind === "case"
			? r.court_name
			: r.chapter
				? `Chapter ${r.chapter.ordinal} — ${r.chapter.heading}`
				: r.source;

	return (
		<button
			type="button"
			onClick={() => onOpen(r)}
			className="group flex w-full items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors hover:bg-accent/40"
		>
			<span
				className={cn(
					"flex size-9 shrink-0 items-center justify-center rounded-md",
					k.tint,
				)}
			>
				<Icon className="size-4.5" />
			</span>
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
					{r.status && (
						<span className="rounded border px-1.5 py-px text-[10px] text-muted-foreground">
							{r.status}
						</span>
					)}
				</div>

				<h3 className="mt-1 font-semibold text-[15px] text-foreground leading-snug group-hover:text-primary group-hover:underline">
					{title}
				</h3>
				<p className="mt-0.5 truncate text-muted-foreground text-xs">
					{cite && <span className="font-mono text-foreground/80">{cite}</span>}
					{cite && context ? "  ·  " : ""}
					{context}
				</p>
				<p className="mt-1.5 line-clamp-2 text-[13px] text-foreground/75 leading-relaxed">
					{highlight(r.snippet, query)}
				</p>
			</div>
			<div className="flex shrink-0 flex-col items-end gap-2 pl-2">
				{r.kind === "case" && r.date_filed && (
					<span className="whitespace-nowrap text-[11px] text-muted-foreground tabular-nums">
						{fmtDate(r.date_filed)}
					</span>
				)}
				<ChevronRightIcon className="size-4 text-muted-foreground/40 transition-all group-hover:translate-x-0.5 group-hover:text-foreground" />
			</div>
		</button>
	);
}

// ---------------------------------------------------------------------------
// Bits
// ---------------------------------------------------------------------------

function FacetGroup({
	title,
	children,
}: {
	title: string;
	children: ReactNode;
}) {
	return (
		<div className="p-2">
			<h3 className="px-2 pb-1 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				{title}
			</h3>
			<div className="space-y-0.5">{children}</div>
		</div>
	);
}

function Facet({
	label,
	count,
	selected,
	onClick,
}: {
	label: string;
	count?: number;
	selected: boolean;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="group flex w-full items-center gap-2 rounded px-2 py-1 text-left transition-colors hover:bg-accent/40"
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
			{count != null && (
				<span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
					{count}
				</span>
			)}
		</button>
	);
}

function FilterChip({
	children,
	onClear,
}: {
	children: ReactNode;
	onClear: () => void;
}) {
	return (
		<span className="inline-flex items-center gap-1 rounded-full border bg-card py-0.5 pr-1 pl-2.5 font-medium text-foreground text-xs">
			{children}
			<button
				type="button"
				onClick={onClear}
				aria-label="Remove filter"
				className="flex size-4 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
			>
				×
			</button>
		</span>
	);
}

// Wrap query terms in <mark>. JSX children auto-escape, so no raw HTML reaches
// the DOM. Cosmetic only — mirrors the live results pane's highlighter.
function highlight(snippet: string, query: string): ReactNode {
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
	return snippet.split(re).map((part, i) =>
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

// Last token of a citation, e.g. "Iowa Code § 714.16" → "714.16", for the
// /browse deep-link hash.
function citeTail(citation: string): string {
	return encodeURIComponent(citation.trim().split(/\s+/).pop() ?? "");
}
