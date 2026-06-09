"use client";

// Search-results v2 mockup (/browse-mockup/results-v2). A faithful port of the
// vLex/Fastcase research-results layout onto OUR design language (dense,
// high-contrast, royal accent — the app-wide light theme; shadcn Button / Sheet /
// DropdownMenu / Tooltip; lucide icons). Zones, top → bottom, left → right:
//
//   • Left icon rail              — app-wide section nav (icon only)
//   • Global header (banner)      — brand, search + jurisdiction, history,
//                                   upgrade, notifications/folders, account menu
//   • Query-context header        — breadcrumb, search-within, h1 + result count,
//                                   action toolbar (save/alert/download, scope
//                                   radios, view-mode links) and a Results/Charts
//                                   tab bar
//   • Left filter panel           — search-in-results, content-type tree,
//                                   jurisdiction checkboxes, cited-authorities
//                                   combobox, date histogram + range sliders,
//                                   "not in your plan" toggle, advanced + sort
//   • Results list                — selectable cards (treatment badge, court,
//                                   date, citations, snippet, matching-paragraphs,
//                                   citation-count) + "More results" pager
//   • Chat widget                 — floating, opens the REAL corpus assistant
//
// WIRED TO REAL DATA: the chat widget (bottom-right) talks to the same
// /api/chat pipeline as the full-page assistant (runChatTurnParts, corpus-wide
// scope) — like the library mockup wired its grid to /api/browse/sources.
//
// ILLUSTRATIVE: the live /browse search endpoint (apps/api/browse.py) returns
// no grand total, no facets, no precedential treatment, no citation counts, and
// no charts — so result rows, every facet count, treatment badges, cited-by
// numbers, the date histogram and the Charts tab are representative demo data
// (themed to the writeup's query, Katko v. Briney). Row field names still mirror
// the real _search_row so the design maps cleanly onto a future faceted API.

import {
	ArrowUpDownIcon,
	BarChart3Icon,
	BellIcon,
	BellPlusIcon,
	BookOpenIcon,
	BookTextIcon,
	CalendarIcon,
	CheckIcon,
	ChevronDownIcon,
	ChevronRightIcon,
	CircleCheckIcon,
	CircleUserIcon,
	CircleXIcon,
	DownloadIcon,
	FileTextIcon,
	FolderIcon,
	GavelIcon,
	HistoryIcon,
	HomeIcon,
	LandmarkIcon,
	LanguagesIcon,
	LayoutGridIcon,
	LayoutListIcon,
	LibraryBigIcon,
	LifeBuoyIcon,
	ListFilterIcon,
	LogOutIcon,
	type LucideIcon,
	MapPinIcon,
	MessagesSquareIcon,
	QuoteIcon,
	ScaleIcon,
	SearchIcon,
	SettingsIcon,
	ShieldIcon,
	SlidersHorizontalIcon,
	SparklesIcon,
	TriangleAlertIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { SearchChatWidget } from "./search-chat";

// ---------------------------------------------------------------------------
// Result model — mirrors apps/api/browse.py _search_row, plus flagged demo-only
// fields (treatment, citedBy, cites, inPlan, category) the live API doesn't
// return yet. See the file header.
// ---------------------------------------------------------------------------

type Kind = "case" | "statute" | "rule" | "commentary" | "journal" | "brief";
type Treatment = "negative" | "caution" | "positive" | null;
type Jurisdiction = "iowa" | "federal";

type Result = {
	id: number;
	kind: Kind;
	category: LeafKey; // content-type tree leaf this row counts under
	jurisdiction: Jurisdiction;
	caseId: number | null;
	title: string;
	court: string; // "" for statutes/rules/secondary
	date: string; // ISO; "" when undated
	citations: string[];
	snippet: string;
	matchingParagraphs: number;
	citedBy: number; // citation-count badge (demo)
	treatment: Treatment; // citator health (demo)
	cites: number[]; // cited-authority ids (drives the Cited Authorities facet)
	inPlan: boolean; // false ⇒ hidden unless "show results not in your plan"
};

// Representative results for q="Katko v. Briney" — real field shapes, plausible
// Iowa content across content types. Snippets are plain text.
const RESULTS: Result[] = [
	{
		id: 50101,
		kind: "case",
		category: "cases",
		jurisdiction: "iowa",
		caseId: 50101,
		title: "Katko v. Briney",
		court: "Supreme Court of Iowa",
		date: "1971-02-09",
		citations: ["183 N.W.2d 657", "1971 Iowa Sup. LEXIS 743"],
		snippet:
			"The law has always placed a higher value upon human safety than upon mere rights in property; an owner may not set a spring gun to repel a trespasser where the result is death or serious injury. Briney's mechanical device exceeded the privilege to defend an unoccupied dwelling.",
		matchingParagraphs: 14,
		citedBy: 412,
		treatment: "positive",
		cites: [1, 2, 3, 4],
		inPlan: true,
	},
	{
		id: 50231,
		kind: "case",
		category: "cases",
		jurisdiction: "iowa",
		caseId: 50231,
		title: "State v. Mayhew",
		court: "Supreme Court of Iowa",
		date: "2009-06-19",
		citations: ["770 N.W.2d 850"],
		snippet:
			"Reasonable force in defense of property is measured by what an ordinarily prudent person would believe necessary; following Katko, the use of force calculated to cause death is not justified to protect possessory interests alone.",
		matchingParagraphs: 6,
		citedBy: 38,
		treatment: "caution",
		cites: [3, 6],
		inPlan: true,
	},
	{
		id: 10704,
		kind: "statute",
		category: "statutes",
		jurisdiction: "iowa",
		caseId: null,
		title: "Defense of property",
		court: "",
		date: "",
		citations: ["Iowa Code § 704.4"],
		snippet:
			"A person is justified in the use of reasonable force to prevent or terminate criminal interference with the person's possession of property. Deadly force is not justified to protect property interests, consistent with Katko v. Briney.",
		matchingParagraphs: 3,
		citedBy: 96,
		treatment: null,
		cites: [],
		inPlan: true,
	},
	{
		id: 10702,
		kind: "statute",
		category: "statutes",
		jurisdiction: "iowa",
		caseId: null,
		title: "Reasonable force — defined",
		court: "",
		date: "",
		citations: ["Iowa Code § 704.2"],
		snippet:
			"&ldquo;Reasonable force&rdquo; is that force and no more which a reasonable person, in like circumstances, would judge necessary; force which creates a substantial risk of death is reasonable only in defense of life, not property.",
		matchingParagraphs: 2,
		citedBy: 54,
		treatment: null,
		cites: [],
		inPlan: true,
	},
	{
		id: 50544,
		kind: "case",
		category: "cases",
		jurisdiction: "iowa",
		caseId: 50544,
		title: "McKinney v. Cochran",
		court: "Court of Appeals of Iowa",
		date: "2018-03-21",
		citations: ["912 N.W.2d 120"],
		snippet:
			"The landowner's concealed trap injured an entrant; the Briney rule controls, and the privilege to exclude does not extend to mechanical devices that the owner could not lawfully deploy in person.",
		matchingParagraphs: 5,
		citedBy: 12,
		treatment: "negative",
		cites: [1, 3],
		inPlan: true,
	},
	{
		id: 80021,
		kind: "commentary",
		category: "commentary",
		jurisdiction: "iowa",
		caseId: null,
		title: "Use of Mechanical Device Threatening Death or Serious Bodily Harm",
		court: "",
		date: "1965-01-01",
		citations: ["Restatement (2d) of Torts § 85"],
		snippet:
			"The actor is so far privileged to use a device intended to protect his land only as he would be privileged to inflict the same harm by direct means — the principle the Iowa court applied in Katko.",
		matchingParagraphs: 4,
		citedBy: 211,
		treatment: null,
		cites: [3],
		inPlan: true,
	},
	{
		id: 90013,
		kind: "journal",
		category: "journals",
		jurisdiction: "iowa",
		caseId: null,
		title: "Spring Guns and the Limits of Defending Property After Katko",
		court: "",
		date: "1981-11-01",
		citations: ["66 Iowa L. Rev. 1201"],
		snippet:
			"This Note traces the spring-gun doctrine from Bird v. Holbrook through Katko v. Briney, arguing that the Iowa rule strikes the correct balance between possessory rights and human safety.",
		matchingParagraphs: 9,
		citedBy: 47,
		treatment: null,
		cites: [1, 3],
		inPlan: true,
	},
	{
		id: 30198,
		kind: "rule",
		category: "court-rules",
		jurisdiction: "iowa",
		caseId: null,
		title: "Summary judgment",
		court: "",
		date: "",
		citations: ["Iowa R. Civ. P. 1.981"],
		snippet:
			"Judgment shall be rendered where there is no genuine issue of material fact — the posture in which the Katko trial court resolved liability for the spring-gun injury before the jury fixed damages.",
		matchingParagraphs: 1,
		citedBy: 80,
		treatment: null,
		cites: [],
		inPlan: true,
	},
	{
		id: 70044,
		kind: "brief",
		category: "briefs",
		jurisdiction: "iowa",
		caseId: null,
		title: "Brief for Appellants, Katko v. Briney",
		court: "Supreme Court of Iowa",
		date: "1970-09-14",
		citations: ["No. 54169"],
		snippet:
			"Appellants contend the trial court erred in instructing the jury that an owner may not employ a spring gun to protect an unoccupied farmhouse against trespassers.",
		matchingParagraphs: 7,
		citedBy: 0,
		treatment: null,
		cites: [1, 2],
		inPlan: false,
	},
];

// The writeup's header reads "45 results"; rendered rows are a representative
// slice (the rest live behind "More results").
const MOCK_TOTAL = 45;

// ---------------------------------------------------------------------------
// Content-type tree — the vLex hierarchy with (illustrative) count badges.
// ---------------------------------------------------------------------------

type LeafKey =
	| "cases"
	| "statutes"
	| "constitutions"
	| "acts"
	| "congressional"
	| "regulations"
	| "admin-decisions"
	| "exec-orders"
	| "admin-registers"
	| "ag-opinions"
	| "corp-filings"
	| "books"
	| "journals"
	| "commentary"
	| "forms"
	| "court-rules"
	| "jury-instructions"
	| "title-standards"
	| "ethics"
	| "news"
	| "briefs"
	| "orders-opinions";

type TreeNode = {
	key: string; // "all" | parent group key | LeafKey
	label: string;
	count: number;
	children?: { key: LeafKey; label: string; count: number }[];
};

const CONTENT_TREE: TreeNode[] = [
	{ key: "all", label: "All Content", count: MOCK_TOTAL },
	{ key: "cases", label: "Cases", count: 18 },
	{
		key: "statutes-and-laws",
		label: "Statutes and Laws",
		count: 7,
		children: [
			{ key: "statutes", label: "Statutes", count: 5 },
			{ key: "constitutions", label: "Constitutions", count: 1 },
			{ key: "acts", label: "Acts and Session Laws", count: 1 },
		],
	},
	{ key: "congressional", label: "Congressional Materials", count: 0 },
	{
		key: "administrative",
		label: "Administrative Materials",
		count: 2,
		children: [
			{ key: "regulations", label: "Regulations", count: 1 },
			{ key: "admin-decisions", label: "Administrative Decisions", count: 1 },
			{ key: "exec-orders", label: "Executive Orders", count: 0 },
			{ key: "admin-registers", label: "Administrative Registers", count: 0 },
			{ key: "ag-opinions", label: "Attorney General Opinions", count: 0 },
			{ key: "corp-filings", label: "Corporate Filings", count: 0 },
		],
	},
	{
		key: "books-journals",
		label: "Books and Journals",
		count: 9,
		children: [
			{ key: "books", label: "Books", count: 4 },
			{ key: "journals", label: "Journals", count: 5 },
		],
	},
	{ key: "commentary", label: "Lawyer Commentary", count: 4 },
	{ key: "forms", label: "Forms and Contracts", count: 1 },
	{
		key: "rules-guidelines",
		label: "Rules and Guidelines",
		count: 3,
		children: [
			{ key: "court-rules", label: "Court Rules", count: 2 },
			{ key: "jury-instructions", label: "Jury Instructions", count: 1 },
			{ key: "title-standards", label: "Title Standards", count: 0 },
			{ key: "ethics", label: "Ethics Matters", count: 0 },
		],
	},
	{ key: "news", label: "News", count: 1 },
	{
		key: "court-materials",
		label: "Court Materials",
		count: 1,
		children: [
			{ key: "briefs", label: "Briefs/Pleadings/Motions", count: 1 },
			{ key: "orders-opinions", label: "Orders and Opinions", count: 0 },
		],
	},
];

// Map any tree key (root/parent/leaf) → the set of leaf categories it selects,
// so picking a parent includes its children and picking "all" matches every row.
function leavesFor(key: string): Set<LeafKey> | null {
	if (key === "all") return null; // null ⇒ no content-type restriction
	const node = CONTENT_TREE.find((n) => n.key === key);
	if (node?.children) return new Set(node.children.map((c) => c.key));
	return new Set([key as LeafKey]);
}

// ---------------------------------------------------------------------------
// Cited authorities — the searchable relational facet.
// ---------------------------------------------------------------------------

const CITED_AUTHORITIES: { id: number; label: string; count: number }[] = [
	{ id: 1, label: "Bird v. Holbrook (1828)", count: 9 },
	{ id: 3, label: "Restatement (2d) of Torts § 85", count: 12 },
	{ id: 6, label: "Iowa Code § 704.4", count: 15 },
	{ id: 4, label: "Hooker v. Miller, 37 Iowa 613 (1873)", count: 6 },
	{ id: 2, label: "State v. Vance, 17 Iowa 138 (1864)", count: 4 },
	{ id: 5, label: "Palsgraf v. Long Island R.R. (1928)", count: 3 },
];

// ---------------------------------------------------------------------------
// Date histogram — results-by-decade (illustrative).
// ---------------------------------------------------------------------------

const YEAR_MIN = 1900;
const YEAR_MAX = 2025;
const DECADE_BUCKETS: { decade: number; count: number }[] = [
	{ decade: 1900, count: 1 },
	{ decade: 1910, count: 0 },
	{ decade: 1920, count: 1 },
	{ decade: 1930, count: 2 },
	{ decade: 1940, count: 1 },
	{ decade: 1950, count: 3 },
	{ decade: 1960, count: 4 },
	{ decade: 1970, count: 9 },
	{ decade: 1980, count: 7 },
	{ decade: 1990, count: 5 },
	{ decade: 2000, count: 6 },
	{ decade: 2010, count: 4 },
	{ decade: 2020, count: 2 },
];
const HISTO_MAX = Math.max(...DECADE_BUCKETS.map((b) => b.count));

// ---------------------------------------------------------------------------
// Misc presentation
// ---------------------------------------------------------------------------

const KIND: Record<Kind, { label: string; icon: LucideIcon; tint: string }> = {
	case: { label: "Case", icon: ScaleIcon, tint: "bg-primary/10 text-primary" },
	statute: {
		label: "Statute",
		icon: LandmarkIcon,
		tint: "bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
	},
	rule: {
		label: "Court Rule",
		icon: GavelIcon,
		tint: "bg-amber-600/10 text-amber-700 dark:text-amber-400",
	},
	commentary: {
		label: "Commentary",
		icon: BookTextIcon,
		tint: "bg-violet-600/10 text-violet-700 dark:text-violet-400",
	},
	journal: {
		label: "Journal",
		icon: BookOpenIcon,
		tint: "bg-sky-600/10 text-sky-700 dark:text-sky-400",
	},
	brief: {
		label: "Brief",
		icon: FileTextIcon,
		tint: "bg-rose-600/10 text-rose-700 dark:text-rose-400",
	},
};

const TREATMENT: Record<
	Exclude<Treatment, null>,
	{ label: string; short: string; icon: LucideIcon; cls: string }
> = {
	negative: {
		label: "Negative treatment — overruled in part",
		short: "Overruled in part",
		icon: CircleXIcon,
		cls: "bg-red-600/10 text-red-700 dark:text-red-400",
	},
	caution: {
		label: "Caution — distinguished by later authority",
		short: "Distinguished",
		icon: TriangleAlertIcon,
		cls: "bg-amber-600/10 text-amber-700 dark:text-amber-400",
	},
	positive: {
		label: "Positive treatment — followed",
		short: "Followed",
		icon: CircleCheckIcon,
		cls: "bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
	},
};

const SORTS = [
	{ id: "relevance", label: "Relevance" },
	{ id: "newest", label: "Date: Most Recent" },
	{ id: "oldest", label: "Date: Oldest" },
	{ id: "cited", label: "Most Cited" },
] as const;
type SortId = (typeof SORTS)[number]["id"];

const MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
const yearOf = (iso: string) => (iso ? Number(iso.slice(0, 4)) : 0);
function fmtDate(iso: string): string {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
	return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : "";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsV2Page() {
	return (
		<Suspense fallback={null}>
			<ResultsV2Inner />
		</Suspense>
	);
}

function ResultsV2Inner() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const [query, setQuery] = useState(
		() => searchParams.get("q") ?? "Katko v. Briney",
	);
	const [draft, setDraft] = useState(query);
	const [jurisdictionSel, setJurisdictionSel] = useState("United States");

	// Filter-panel state
	const [within, setWithin] = useState(""); // search-in-results
	const [contentKey, setContentKey] = useState("all");
	const [expanded, setExpanded] = useState<Set<string>>(
		() => new Set(["statutes-and-laws", "books-journals"]),
	);
	const [juris, setJuris] = useState<Record<string, boolean>>({
		intl: false,
		us: true,
		federal: false,
		states: false,
	});
	const [authorityQuery, setAuthorityQuery] = useState("");
	const [authority, setAuthority] = useState<number | null>(null);
	const [exactDate, setExactDate] = useState("");
	const [startYear, setStartYear] = useState(YEAR_MIN);
	const [endYear, setEndYear] = useState(YEAR_MAX);
	const [showNotInPlan, setShowNotInPlan] = useState(false);
	const [sort, setSort] = useState<SortId>("relevance");

	// Toolbar / view state
	const [view, setView] = useState<"list" | "grid">("list");
	const [viewMode, setViewMode] = useState<"full" | "listings">("full");
	const [tab, setTab] = useState<"results" | "charts">("results");
	const [selected, setSelected] = useState<Set<number>>(new Set());
	const [actionScope, setActionScope] = useState<"selected" | "top">("top");

	const toggleExpanded = (key: string) =>
		setExpanded((prev) => {
			const next = new Set(prev);
			if (next.has(key)) next.delete(key);
			else next.add(key);
			return next;
		});
	const toggleSelected = (id: number) =>
		setSelected((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});

	// ---- derived results ---------------------------------------------------
	const allowedLeaves = useMemo(() => leavesFor(contentKey), [contentKey]);
	const filtered = useMemo(() => {
		const w = within.trim().toLowerCase();
		let rows = RESULTS.filter((r) => {
			if (!showNotInPlan && !r.inPlan) return false;
			if (allowedLeaves && !allowedLeaves.has(r.category)) return false;
			if (authority != null && !r.cites.includes(authority)) return false;
			// Jurisdiction: a US state row matches "United States" or "All States";
			// federal rows match "All Federal". No box checked ⇒ no restriction.
			const anyJuris = juris.us || juris.federal || juris.states || juris.intl;
			if (anyJuris) {
				const matches =
					(r.jurisdiction === "iowa" && (juris.us || juris.states)) ||
					(r.jurisdiction === "federal" && (juris.us || juris.federal)) ||
					juris.intl;
				if (!matches) return false;
			}
			// Date range applies to dated rows; undated (statutes/rules) always pass.
			if (r.date) {
				const y = yearOf(r.date);
				if (y < startYear || y > endYear) return false;
			}
			if (w && !`${r.title} ${r.snippet}`.toLowerCase().includes(w))
				return false;
			return true;
		});
		if (sort === "cited") {
			rows = [...rows].sort((a, b) => b.citedBy - a.citedBy);
		} else if (sort !== "relevance") {
			rows = [...rows].sort((a, b) => {
				const da = a.date || "";
				const db = b.date || "";
				if (!da && !db) return 0;
				if (!da) return 1;
				if (!db) return -1;
				return sort === "newest" ? db.localeCompare(da) : da.localeCompare(db);
			});
		}
		return rows;
	}, [
		within,
		allowedLeaves,
		authority,
		juris,
		startYear,
		endYear,
		showNotInPlan,
		sort,
	]);

	const submit = () => setQuery(draft.trim() || query);
	const open = (r: Result) => {
		if (r.kind === "case" && r.caseId != null)
			router.push(`/cases/${r.caseId}`);
		else
			router.push(`/browse?q=${encodeURIComponent(r.citations[0] ?? query)}`);
	};

	return (
		<div className="flex h-dvh w-full overflow-hidden">
			<a
				href="#results"
				className="sr-only rounded-md bg-primary px-3 py-1.5 text-primary-foreground text-sm focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
			>
				Skip to results
			</a>

			<IconRail />

			{/* Everything right of the rail: banner on top, then the two columns. */}
			<div className="flex min-w-0 flex-1 flex-col">
				<GlobalHeader
					draft={draft}
					onDraft={setDraft}
					onSubmit={submit}
					jurisdiction={jurisdictionSel}
					onJurisdiction={setJurisdictionSel}
				/>

				<div className="flex min-h-0 flex-1">
					<FilterPanel
						within={within}
						onWithin={setWithin}
						contentKey={contentKey}
						onContentKey={setContentKey}
						expanded={expanded}
						onToggleExpanded={toggleExpanded}
						juris={juris}
						onJuris={setJuris}
						authorityQuery={authorityQuery}
						onAuthorityQuery={setAuthorityQuery}
						authority={authority}
						onAuthority={setAuthority}
						exactDate={exactDate}
						onExactDate={setExactDate}
						startYear={startYear}
						endYear={endYear}
						onStartYear={setStartYear}
						onEndYear={setEndYear}
						showNotInPlan={showNotInPlan}
						onShowNotInPlan={setShowNotInPlan}
						sort={sort}
						onSort={setSort}
					/>

					{/* Results column */}
					<main
						id="results"
						className="flex min-w-0 flex-1 flex-col overflow-hidden"
					>
						<QueryHeader
							query={query}
							shown={filtered.length}
							selectedCount={selected.size}
							actionScope={actionScope}
							onActionScope={setActionScope}
							view={view}
							onView={setView}
							viewMode={viewMode}
							onViewMode={setViewMode}
							tab={tab}
							onTab={setTab}
						/>

						<div className="min-w-0 flex-1 overflow-y-auto px-5 py-4">
							{/* Active filter chips */}
							<ActiveChips
								contentKey={contentKey}
								onClearContent={() => setContentKey("all")}
								authority={authority}
								onClearAuthority={() => setAuthority(null)}
								startYear={startYear}
								endYear={endYear}
								onClearDate={() => {
									setStartYear(YEAR_MIN);
									setEndYear(YEAR_MAX);
								}}
								within={within}
								onClearWithin={() => setWithin("")}
							/>

							{tab === "charts" ? (
								<ChartsPanel rows={filtered} />
							) : filtered.length === 0 ? (
								<div className="mt-6 rounded-lg border border-dashed bg-card px-4 py-12 text-center text-muted-foreground text-sm">
									No results match these filters.
								</div>
							) : (
								<>
									<ul
										className={cn(
											view === "grid"
												? "grid gap-3 sm:grid-cols-2"
												: "divide-y",
										)}
									>
										{filtered.map((r) => (
											<ResultCard
												key={r.id}
												result={r}
												query={query}
												view={view}
												viewMode={viewMode}
												selected={selected.has(r.id)}
												onToggle={() => toggleSelected(r.id)}
												onOpen={() => open(r)}
											/>
										))}
									</ul>

									{/* "More results" pagination trigger */}
									<div className="mt-5 flex flex-col items-center gap-1.5 border-t pt-5">
										<Button variant="outline" size="sm" className="gap-1.5">
											<ChevronDownIcon className="size-4" />
											More results
										</Button>
										<span className="text-[11px] text-muted-foreground tabular-nums">
											Showing {filtered.length} of {MOCK_TOTAL.toLocaleString()}
										</span>
									</div>
								</>
							)}
						</div>
					</main>
				</div>
			</div>

			<SearchChatWidget query={query} />
		</div>
	);
}

// ---------------------------------------------------------------------------
// 1. Global header (banner)
// ---------------------------------------------------------------------------

function GlobalHeader({
	draft,
	onDraft,
	onSubmit,
	jurisdiction,
	onJurisdiction,
}: {
	draft: string;
	onDraft: (v: string) => void;
	onSubmit: () => void;
	jurisdiction: string;
	onJurisdiction: (v: string) => void;
}) {
	return (
		<header className="flex h-16 shrink-0 items-center gap-3 border-b bg-card px-4">
			{/* Brand */}
			<Link
				href="/browse-mockup"
				className="flex shrink-0 items-center gap-2"
				aria-label="Hudson Legal Tech home"
			>
				<span className="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
					<BookOpenIcon className="size-4" />
				</span>
				<span className="hidden flex-col leading-none lg:flex">
					<span className="font-semibold text-sm">Hudson Legal Tech</span>
					<span className="text-[11px] text-muted-foreground">Research</span>
				</span>
			</Link>

			{/* Search form — input + jurisdiction + submit */}
			<form
				className="mx-auto flex w-full max-w-2xl items-stretch rounded-lg border bg-background shadow-xs transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50"
				onSubmit={(e) => {
					e.preventDefault();
					onSubmit();
				}}
			>
				<div className="relative flex flex-1 items-center">
					<SearchIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
					<input
						value={draft}
						onChange={(e) => onDraft(e.target.value)}
						aria-label="Search the corpus"
						placeholder="Search by keyword, citation, or party name…"
						className="h-10 w-full bg-transparent pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground"
					/>
				</div>
				<div className="my-2 w-px bg-border" />
				<div className="relative hidden items-center sm:flex">
					<MapPinIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-3.5 text-muted-foreground" />
					<select
						value={jurisdiction}
						onChange={(e) => onJurisdiction(e.target.value)}
						aria-label="Jurisdiction"
						className="h-full cursor-pointer appearance-none bg-transparent pr-8 pl-8 font-medium text-foreground text-sm outline-none"
					>
						{["United States", "Iowa", "All States", "Federal"].map((j) => (
							<option key={j} value={j}>
								{j}
							</option>
						))}
					</select>
					<ChevronDownIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 right-2.5 size-3.5 text-muted-foreground" />
				</div>
				<div className="flex items-center p-1.5">
					<Button
						type="submit"
						size="sm"
						className="size-8 p-0"
						aria-label="Search"
					>
						<SearchIcon className="size-4" />
					</Button>
				</div>
			</form>

			{/* Right-hand utilities */}
			<div className="flex shrink-0 items-center gap-1">
				<HistoryMenu />
				<HeaderIcon icon={FolderIcon} label="Folders" />
				<HeaderIcon icon={BellIcon} label="Notifications" badge />
				<Button size="sm" className="ml-1 hidden gap-1.5 md:inline-flex">
					<SparklesIcon className="size-3.5" />
					Upgrade
				</Button>
				<AccountMenu />
			</div>
		</header>
	);
}

function HeaderIcon({
	icon: Icon,
	label,
	badge,
}: {
	icon: LucideIcon;
	label: string;
	badge?: boolean;
}) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<button
					type="button"
					aria-label={label}
					className="relative flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					<Icon className="size-[18px]" />
					{badge && (
						<span className="absolute top-2 right-2 size-1.5 rounded-full bg-primary" />
					)}
				</button>
			</TooltipTrigger>
			<TooltipContent side="bottom">{label}</TooltipContent>
		</Tooltip>
	);
}

// Recently-visited documents — the writeup's History dropdown / recent list.
const RECENT_DOCS: { title: string; meta: string }[] = [
	{ title: "Katko v. Briney", meta: "183 N.W.2d 657 · viewed 1h ago" },
	{ title: "State v. Mayhew", meta: "770 N.W.2d 850 · viewed yesterday" },
	{ title: "Iowa Code § 704.4", meta: "Defense of property · 2 days ago" },
	{ title: "Bird v. Holbrook", meta: "130 Eng. Rep. 911 · 3 days ago" },
];

function HistoryMenu() {
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<button
					type="button"
					aria-label="History"
					className="flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					<HistoryIcon className="size-[18px]" />
				</button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-72">
				<DropdownMenuLabel className="flex items-center justify-between">
					Recent documents
					<button
						type="button"
						className="font-normal text-[11px] text-muted-foreground hover:text-foreground"
					>
						Clear
					</button>
				</DropdownMenuLabel>
				<DropdownMenuSeparator />
				{RECENT_DOCS.map((d) => (
					<DropdownMenuItem
						key={d.title}
						className="flex-col items-start gap-0.5"
					>
						<span className="font-medium text-[13px]">{d.title}</span>
						<span className="text-[11px] text-muted-foreground">{d.meta}</span>
					</DropdownMenuItem>
				))}
			</DropdownMenuContent>
		</DropdownMenu>
	);
}

function AccountMenu() {
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<button
					type="button"
					aria-label="Account"
					className="ml-0.5 flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					<CircleUserIcon className="size-6" />
				</button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-64">
				<div className="px-2 py-1.5">
					<p className="font-medium text-sm">Nick Hudson</p>
					<p className="truncate text-muted-foreground text-xs">
						nick@nickhudson.me
					</p>
				</div>
				<DropdownMenuSeparator />
				<DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase tracking-wider">
					Settings
				</DropdownMenuLabel>
				<DropdownMenuItem>
					<LanguagesIcon className="size-4" /> Language settings
				</DropdownMenuItem>
				<DropdownMenuItem>
					<SettingsIcon className="size-4" /> Manage your account
				</DropdownMenuItem>
				<DropdownMenuSeparator />
				<DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase tracking-wider">
					Alerts
				</DropdownMenuLabel>
				<DropdownMenuItem>
					<BellPlusIcon className="size-4" /> Manage your alerts
				</DropdownMenuItem>
				<DropdownMenuItem>
					<BellIcon className="size-4" /> Notifications center
				</DropdownMenuItem>
				<DropdownMenuSeparator />
				<DropdownMenuLabel className="text-[11px] text-muted-foreground uppercase tracking-wider">
					Privacy &amp; Legal
				</DropdownMenuLabel>
				<DropdownMenuItem>
					<HistoryIcon className="size-4" /> History tracking: On
				</DropdownMenuItem>
				<DropdownMenuItem>
					<ShieldIcon className="size-4" /> Terms &amp; Privacy
				</DropdownMenuItem>
				<DropdownMenuSeparator />
				<DropdownMenuItem>
					<FileTextIcon className="size-4" /> Return to classic
				</DropdownMenuItem>
				<DropdownMenuItem className="text-destructive focus:text-destructive">
					<LogOutIcon className="size-4" /> Log out
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}

// ---------------------------------------------------------------------------
// 2. Left icon rail
// ---------------------------------------------------------------------------

function IconRail() {
	return (
		<nav className="flex w-14 shrink-0 flex-col items-center gap-1 border-r bg-sidebar py-3">
			<Link
				href="/browse-mockup"
				aria-label="Home"
				className="mb-1 flex size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground"
			>
				<BookOpenIcon className="size-[18px]" />
			</Link>
			<div className="my-1 h-px w-7 bg-sidebar-border" />
			<RailIcon href="/browse-mockup" icon={HomeIcon} label="Home" />
			<RailIcon
				href="/browse-mockup/results-v2"
				icon={SearchIcon}
				label="Search"
				active
			/>
			<RailIcon href="/browse-mockup" icon={ScaleIcon} label="Practice areas" />
			<RailIcon href="/browse-mockup" icon={LibraryBigIcon} label="Library" />
			<RailIcon href="/" icon={MessagesSquareIcon} label="Assistant" />
			<RailIcon href="/browse-mockup" icon={FolderIcon} label="Folders" />
			<div className="flex-1" />
			<RailIcon href="/browse-mockup" icon={LifeBuoyIcon} label="Help" />
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
// 3a. Query-context header (breadcrumb, h1 + count, toolbar, tabs)
// ---------------------------------------------------------------------------

function QueryHeader({
	query,
	shown,
	selectedCount,
	actionScope,
	onActionScope,
	view,
	onView,
	viewMode,
	onViewMode,
	tab,
	onTab,
}: {
	query: string;
	shown: number;
	selectedCount: number;
	actionScope: "selected" | "top";
	onActionScope: (v: "selected" | "top") => void;
	view: "list" | "grid";
	onView: (v: "list" | "grid") => void;
	viewMode: "full" | "listings";
	onViewMode: (v: "full" | "listings") => void;
	tab: "results" | "charts";
	onTab: (v: "results" | "charts") => void;
}) {
	return (
		<div className="shrink-0 border-b bg-card">
			<div className="px-5 pt-3">
				{/* Breadcrumb */}
				<nav aria-label="Breadcrumb">
					<ol className="flex items-center gap-2 text-xs">
						<li>
							<Link
								href="/browse-mockup"
								className="text-muted-foreground hover:text-foreground"
							>
								Home
							</Link>
						</li>
						<ChevronRightIcon className="size-3.5 text-muted-foreground/50" />
						<li className="font-medium text-foreground">Your search</li>
					</ol>
				</nav>

				{/* Heading + count */}
				<div className="mt-2 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
					<div className="min-w-0">
						<h1 className="truncate font-semibold text-xl tracking-tight">
							{query}
						</h1>
						<p
							className="mt-0.5 text-muted-foreground text-xs"
							role="status"
							aria-live="polite"
						>
							{MOCK_TOTAL} results
							{shown !== MOCK_TOTAL ? ` · ${shown} shown` : ""}
						</p>
					</div>

					{/* Toolbar */}
					<div className="flex flex-wrap items-center gap-2">
						{/* View toggle: list / grid */}
						<div className="flex items-center rounded-md border bg-background p-0.5">
							<ToolbarToggle
								active={view === "list"}
								onClick={() => onView("list")}
								icon={LayoutListIcon}
								label="List view"
							/>
							<ToolbarToggle
								active={view === "grid"}
								onClick={() => onView("grid")}
								icon={LayoutGridIcon}
								label="Grid view"
							/>
						</div>

						{/* Save dropdown */}
						<DropdownMenu>
							<DropdownMenuTrigger asChild>
								<Button variant="outline" size="sm" className="gap-1.5">
									<FolderIcon className="size-3.5" />
									<span className="hidden sm:inline">Save</span>
									<ChevronDownIcon className="size-3.5" />
								</Button>
							</DropdownMenuTrigger>
							<DropdownMenuContent align="end">
								<DropdownMenuItem>Save search</DropdownMenuItem>
								<DropdownMenuItem disabled={selectedCount === 0}>
									Save selected documents
									{selectedCount > 0 ? ` (${selectedCount})` : ""}
								</DropdownMenuItem>
							</DropdownMenuContent>
						</DropdownMenu>

						<Button variant="outline" size="sm" className="gap-1.5">
							<BellPlusIcon className="size-3.5" />
							<span className="hidden sm:inline">Create alert</span>
						</Button>
						<Button variant="outline" size="sm" className="gap-1.5">
							<DownloadIcon className="size-3.5" />
							<span className="hidden sm:inline">Download</span>
						</Button>
					</div>
				</div>

				{/* Scope radios + view-mode links */}
				<div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[13px]">
					<fieldset className="flex items-center gap-4">
						<legend className="sr-only">Action scope</legend>
						<ScopeRadio
							name="scope"
							checked={actionScope === "selected"}
							onChange={() => onActionScope("selected")}
							label={`Selected results${selectedCount ? ` (${selectedCount})` : ""}`}
						/>
						<ScopeRadio
							name="scope"
							checked={actionScope === "top"}
							onChange={() => onActionScope("top")}
							label={`Top ${MOCK_TOTAL} results`}
						/>
					</fieldset>

					<div className="flex items-center gap-1">
						<ViewModeLink
							active={viewMode === "full"}
							onClick={() => onViewMode("full")}
						>
							Full documents
						</ViewModeLink>
						<span className="text-muted-foreground/40">·</span>
						<ViewModeLink
							active={viewMode === "listings"}
							onClick={() => onViewMode("listings")}
						>
							Search listings
						</ViewModeLink>
					</div>
				</div>
			</div>

			{/* Results / Charts tab bar */}
			<div className="mt-3 flex gap-6 px-5">
				<TabButton active={tab === "results"} onClick={() => onTab("results")}>
					{MOCK_TOTAL} results
				</TabButton>
				<TabButton active={tab === "charts"} onClick={() => onTab("charts")}>
					<BarChart3Icon className="size-3.5" />
					Charts
				</TabButton>
			</div>
		</div>
	);
}

function ToolbarToggle({
	active,
	onClick,
	icon: Icon,
	label,
}: {
	active: boolean;
	onClick: () => void;
	icon: LucideIcon;
	label: string;
}) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<button
					type="button"
					onClick={onClick}
					aria-label={label}
					aria-pressed={active}
					className={cn(
						"flex size-7 items-center justify-center rounded transition-colors",
						active
							? "bg-primary text-primary-foreground"
							: "text-muted-foreground hover:text-foreground",
					)}
				>
					<Icon className="size-4" />
				</button>
			</TooltipTrigger>
			<TooltipContent side="bottom">{label}</TooltipContent>
		</Tooltip>
	);
}

function ScopeRadio({
	name,
	checked,
	onChange,
	label,
}: {
	name: string;
	checked: boolean;
	onChange: () => void;
	label: string;
}) {
	return (
		<label className="flex cursor-pointer items-center gap-1.5">
			<input
				type="radio"
				name={name}
				checked={checked}
				onChange={onChange}
				className="size-3.5 accent-primary"
			/>
			<span
				className={
					checked ? "font-medium text-foreground" : "text-muted-foreground"
				}
			>
				{label}
			</span>
		</label>
	);
}

function ViewModeLink({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"rounded px-1 transition-colors",
				active
					? "font-medium text-primary"
					: "text-muted-foreground hover:text-foreground",
			)}
		>
			{children}
		</button>
	);
}

function TabButton({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			role="tab"
			aria-selected={active}
			className={cn(
				"-mb-px flex items-center gap-1.5 border-b-2 px-0.5 pb-2 font-medium text-[13px] transition-colors",
				active
					? "border-primary text-foreground"
					: "border-transparent text-muted-foreground hover:text-foreground",
			)}
		>
			{children}
		</button>
	);
}

// ---------------------------------------------------------------------------
// 3b. Left filter panel
// ---------------------------------------------------------------------------

function FilterPanel(props: {
	within: string;
	onWithin: (v: string) => void;
	contentKey: string;
	onContentKey: (v: string) => void;
	expanded: Set<string>;
	onToggleExpanded: (k: string) => void;
	juris: Record<string, boolean>;
	onJuris: (v: Record<string, boolean>) => void;
	authorityQuery: string;
	onAuthorityQuery: (v: string) => void;
	authority: number | null;
	onAuthority: (v: number | null) => void;
	exactDate: string;
	onExactDate: (v: string) => void;
	startYear: number;
	endYear: number;
	onStartYear: (v: number) => void;
	onEndYear: (v: number) => void;
	showNotInPlan: boolean;
	onShowNotInPlan: (v: boolean) => void;
	sort: SortId;
	onSort: (v: SortId) => void;
}) {
	const [draftWithin, setDraftWithin] = useState(props.within);
	return (
		<aside className="hidden w-72 shrink-0 flex-col border-r bg-card lg:flex">
			<div className="flex h-11 shrink-0 items-center gap-1.5 border-b px-3 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				<ListFilterIcon className="size-3.5" />
				Narrow your results
			</div>

			<div className="min-w-0 flex-1 divide-y overflow-y-auto">
				{/* Search in results */}
				<div className="p-3">
					<form
						className="flex items-stretch rounded-md border bg-background transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50"
						onSubmit={(e) => {
							e.preventDefault();
							props.onWithin(draftWithin.trim());
						}}
					>
						<input
							value={draftWithin}
							onChange={(e) => setDraftWithin(e.target.value)}
							placeholder="Search within results…"
							aria-label="Search within results"
							className="h-8 w-full bg-transparent px-2.5 text-[13px] outline-none placeholder:text-muted-foreground"
						/>
						<button
							type="submit"
							aria-label="Search within results"
							className="flex w-8 items-center justify-center text-muted-foreground hover:text-foreground"
						>
							<SearchIcon className="size-3.5" />
						</button>
					</form>
				</div>

				{/* Content type */}
				<FilterSection title="Content type">
					<ContentTypeTree
						selected={props.contentKey}
						onSelect={props.onContentKey}
						expanded={props.expanded}
						onToggleExpanded={props.onToggleExpanded}
					/>
				</FilterSection>

				{/* Jurisdiction */}
				<FilterSection title="Jurisdiction">
					<JurisdictionFilter juris={props.juris} onJuris={props.onJuris} />
				</FilterSection>

				{/* Cited authorities */}
				<FilterSection title="Cited authorities">
					<CitedAuthorities
						q={props.authorityQuery}
						onQ={props.onAuthorityQuery}
						selected={props.authority}
						onSelect={props.onAuthority}
					/>
				</FilterSection>

				{/* Date */}
				<FilterSection title="Date">
					<DateFilter
						exactDate={props.exactDate}
						onExactDate={props.onExactDate}
						startYear={props.startYear}
						endYear={props.endYear}
						onStartYear={props.onStartYear}
						onEndYear={props.onEndYear}
					/>
				</FilterSection>

				{/* Plan toggle */}
				<div className="p-3">
					<label className="flex cursor-pointer items-center justify-between gap-2">
						<span className="text-[13px] text-foreground">
							Show results not in your plan
						</span>
						<input
							type="checkbox"
							checked={props.showNotInPlan}
							onChange={(e) => props.onShowNotInPlan(e.target.checked)}
							className="size-4 accent-primary"
						/>
					</label>
				</div>

				{/* Advanced + sort */}
				<div className="space-y-2 p-3">
					<Button
						asChild
						variant="outline"
						size="sm"
						className="w-full justify-center gap-1.5"
					>
						<Link href="/browse-mockup/advanced">
							<SlidersHorizontalIcon className="size-3.5" />
							Advanced search
						</Link>
					</Button>
					<SortByMenu sort={props.sort} onSort={props.onSort} />
				</div>
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
		<section className="p-3">
			<h3 className="px-1 pb-1.5 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				{title}
			</h3>
			{children}
		</section>
	);
}

function ContentTypeTree({
	selected,
	onSelect,
	expanded,
	onToggleExpanded,
}: {
	selected: string;
	onSelect: (k: string) => void;
	expanded: Set<string>;
	onToggleExpanded: (k: string) => void;
}) {
	return (
		<div className="space-y-0.5">
			{CONTENT_TREE.map((node) => {
				const hasChildren = !!node.children?.length;
				const isOpen = expanded.has(node.key);
				return (
					<div key={node.key}>
						<div className="flex items-center">
							{hasChildren ? (
								<button
									type="button"
									onClick={() => onToggleExpanded(node.key)}
									aria-label={isOpen ? "Collapse" : "Expand"}
									aria-expanded={isOpen}
									className="flex size-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-foreground"
								>
									<ChevronRightIcon
										className={cn(
											"size-3.5 transition-transform",
											isOpen && "rotate-90",
										)}
									/>
								</button>
							) : (
								<span className="w-5 shrink-0" />
							)}
							<TreeRow
								label={node.label}
								count={node.count}
								selected={selected === node.key}
								bold={node.key === "all"}
								onClick={() => onSelect(node.key)}
							/>
						</div>
						{hasChildren && isOpen && (
							<div className="ml-5 border-l pl-1">
								{node.children?.map((c) => (
									<TreeRow
										key={c.key}
										label={c.label}
										count={c.count}
										selected={selected === c.key}
										onClick={() => onSelect(c.key)}
									/>
								))}
							</div>
						)}
					</div>
				);
			})}
		</div>
	);
}

function TreeRow({
	label,
	count,
	selected,
	bold,
	onClick,
}: {
	label: string;
	count: number;
	selected: boolean;
	bold?: boolean;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"group flex min-w-0 flex-1 items-center gap-2 rounded px-1.5 py-1 text-left transition-colors hover:bg-accent/50",
				selected && "bg-primary/10",
			)}
		>
			<span
				className={cn(
					"min-w-0 flex-1 truncate text-[13px]",
					selected
						? "font-medium text-primary"
						: cn(
								"text-muted-foreground group-hover:text-foreground",
								bold && "font-medium text-foreground",
							),
				)}
			>
				{label}
			</span>
			<span
				className={cn(
					"shrink-0 rounded px-1 text-[11px] tabular-nums",
					count === 0
						? "text-muted-foreground/40"
						: "bg-muted text-muted-foreground",
				)}
			>
				{count}
			</span>
		</button>
	);
}

function JurisdictionFilter({
	juris,
	onJuris,
}: {
	juris: Record<string, boolean>;
	onJuris: (v: Record<string, boolean>) => void;
}) {
	const [more, setMore] = useState(false);
	const set = (key: string, val: boolean) => onJuris({ ...juris, [key]: val });
	const rows: { key: string; label: string }[] = [
		{ key: "intl", label: "All Countries & International" },
		{ key: "us", label: "United States" },
		{ key: "federal", label: "All Federal" },
		{ key: "states", label: "All States" },
	];
	return (
		<div className="space-y-0.5">
			{rows.map((r) => (
				<label
					key={r.key}
					className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-accent/50"
				>
					<input
						type="checkbox"
						checked={!!juris[r.key]}
						onChange={(e) => set(r.key, e.target.checked)}
						className="size-3.5 accent-primary"
					/>
					<span
						className={cn(
							"text-[13px]",
							juris[r.key]
								? "font-medium text-foreground"
								: "text-muted-foreground",
						)}
					>
						{r.label}
					</span>
				</label>
			))}
			<button
				type="button"
				onClick={() => setMore((v) => !v)}
				className="flex items-center gap-1 px-1.5 py-1 text-[12px] text-primary hover:underline"
			>
				<ChevronRightIcon
					className={cn("size-3 transition-transform", more && "rotate-90")}
				/>
				Select more jurisdictions
			</button>
			{more && (
				<div className="ml-1.5 border-l pl-2.5">
					{[
						"Iowa",
						"Eighth Circuit",
						"U.S. Supreme Court",
						"Minnesota",
						"Nebraska",
					].map((j) => (
						<label
							key={j}
							className="flex cursor-pointer items-center gap-2 py-0.5 text-[12px] text-muted-foreground hover:text-foreground"
						>
							<input type="checkbox" className="size-3 accent-primary" />
							{j}
						</label>
					))}
				</div>
			)}
		</div>
	);
}

function CitedAuthorities({
	q,
	onQ,
	selected,
	onSelect,
}: {
	q: string;
	onQ: (v: string) => void;
	selected: number | null;
	onSelect: (v: number | null) => void;
}) {
	const matches = CITED_AUTHORITIES.filter((a) =>
		a.label.toLowerCase().includes(q.trim().toLowerCase()),
	);
	return (
		<div>
			<div className="flex items-stretch rounded-md border bg-background transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
				<input
					value={q}
					onChange={(e) => onQ(e.target.value)}
					placeholder="Filter cases cited across results…"
					aria-label="Filter cited authorities"
					className="h-8 w-full bg-transparent px-2.5 text-[13px] outline-none placeholder:text-muted-foreground"
				/>
				<span className="flex w-8 items-center justify-center text-muted-foreground">
					<SearchIcon className="size-3.5" />
				</span>
			</div>
			<div className="mt-1 max-h-44 space-y-0.5 overflow-y-auto">
				{matches.length === 0 ? (
					<p className="px-1.5 py-2 text-[12px] text-muted-foreground">
						No authorities match.
					</p>
				) : (
					matches.map((a) => {
						const active = selected === a.id;
						return (
							<button
								key={a.id}
								type="button"
								onClick={() => onSelect(active ? null : a.id)}
								className={cn(
									"group flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-colors hover:bg-accent/50",
									active && "bg-primary/10",
								)}
							>
								<span
									className={cn(
										"flex size-3.5 shrink-0 items-center justify-center rounded border",
										active
											? "border-primary bg-primary text-primary-foreground"
											: "border-muted-foreground/40",
									)}
								>
									{active && <CheckIcon className="size-2.5" />}
								</span>
								<span
									className={cn(
										"min-w-0 flex-1 truncate text-[13px]",
										active
											? "font-medium text-foreground"
											: "text-muted-foreground group-hover:text-foreground",
									)}
								>
									{a.label}
								</span>
								<span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
									{a.count}
								</span>
							</button>
						);
					})
				)}
			</div>
		</div>
	);
}

function DateFilter({
	exactDate,
	onExactDate,
	startYear,
	endYear,
	onStartYear,
	onEndYear,
}: {
	exactDate: string;
	onExactDate: (v: string) => void;
	startYear: number;
	endYear: number;
	onStartYear: (v: number) => void;
	onEndYear: (v: number) => void;
}) {
	return (
		<div className="space-y-3">
			{/* Exact date */}
			<div className="relative flex items-center rounded-md border bg-background transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
				<CalendarIcon className="pointer-events-none absolute left-2.5 size-3.5 text-muted-foreground" />
				<input
					value={exactDate}
					onChange={(e) => onExactDate(e.target.value)}
					placeholder="Exact date (e.g. 1971-02-09)"
					aria-label="Exact date"
					className="h-8 w-full bg-transparent pr-2.5 pl-8 text-[13px] outline-none placeholder:text-muted-foreground"
				/>
			</div>

			{/* Range: start slider · histogram · end slider */}
			<div>
				<div className="flex items-center justify-between text-[11px] text-muted-foreground tabular-nums">
					<span>Start: {startYear}</span>
					<span>End: {endYear}</span>
				</div>

				<input
					type="range"
					min={YEAR_MIN}
					max={YEAR_MAX}
					value={startYear}
					onChange={(e) =>
						onStartYear(Math.min(Number(e.target.value), endYear))
					}
					aria-label="Start date"
					className="mt-1.5 h-1 w-full cursor-pointer accent-primary"
				/>

				{/* Histogram */}
				<div className="mt-2 flex h-16 items-end gap-px">
					{DECADE_BUCKETS.map((b) => {
						const inRange = b.decade >= startYear && b.decade <= endYear;
						return (
							<div
								key={b.decade}
								title={`${b.decade}s — ${b.count}`}
								className={cn(
									"flex-1 rounded-t transition-colors",
									inRange ? "bg-primary" : "bg-primary/15",
								)}
								style={{
									height: `${Math.max(6, (b.count / HISTO_MAX) * 100)}%`,
								}}
							/>
						);
					})}
				</div>

				<input
					type="range"
					min={YEAR_MIN}
					max={YEAR_MAX}
					value={endYear}
					onChange={(e) =>
						onEndYear(Math.max(Number(e.target.value), startYear))
					}
					aria-label="End date"
					className="mt-1 h-1 w-full cursor-pointer accent-primary"
				/>
			</div>
		</div>
	);
}

function SortByMenu({
	sort,
	onSort,
}: {
	sort: SortId;
	onSort: (v: SortId) => void;
}) {
	const current = SORTS.find((s) => s.id === sort);
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<Button variant="outline" size="sm" className="w-full justify-between">
					<span className="flex items-center gap-1.5">
						<ArrowUpDownIcon className="size-3.5" />
						Sort: {current?.label}
					</span>
					<ChevronDownIcon className="size-3.5" />
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent
				align="start"
				className="w-[var(--radix-dropdown-menu-trigger-width)]"
			>
				{SORTS.map((s) => (
					<DropdownMenuItem key={s.id} onClick={() => onSort(s.id)}>
						<CheckIcon className={cn("size-4", s.id !== sort && "opacity-0")} />
						{s.label}
					</DropdownMenuItem>
				))}
			</DropdownMenuContent>
		</DropdownMenu>
	);
}

// ---------------------------------------------------------------------------
// Active filter chips (above the list)
// ---------------------------------------------------------------------------

function ActiveChips({
	contentKey,
	onClearContent,
	authority,
	onClearAuthority,
	startYear,
	endYear,
	onClearDate,
	within,
	onClearWithin,
}: {
	contentKey: string;
	onClearContent: () => void;
	authority: number | null;
	onClearAuthority: () => void;
	startYear: number;
	endYear: number;
	onClearDate: () => void;
	within: string;
	onClearWithin: () => void;
}) {
	const contentLabel =
		contentKey !== "all"
			? (CONTENT_TREE.find((n) => n.key === contentKey)?.label ??
				CONTENT_TREE.flatMap((n) => n.children ?? []).find(
					(c) => c.key === contentKey,
				)?.label)
			: null;
	const authLabel =
		authority != null
			? CITED_AUTHORITIES.find((a) => a.id === authority)?.label
			: null;
	const dateActive = startYear !== YEAR_MIN || endYear !== YEAR_MAX;
	const any = contentLabel || authLabel || dateActive || within.trim();
	if (!any) return null;
	return (
		<div className="mb-3 flex flex-wrap items-center gap-1.5">
			<span className="text-[11px] text-muted-foreground uppercase tracking-wider">
				Filters
			</span>
			{contentLabel && <Chip onClear={onClearContent}>{contentLabel}</Chip>}
			{authLabel && <Chip onClear={onClearAuthority}>Cites: {authLabel}</Chip>}
			{dateActive && (
				<Chip onClear={onClearDate}>
					{startYear}–{endYear}
				</Chip>
			)}
			{within.trim() && <Chip onClear={onClearWithin}>“{within.trim()}”</Chip>}
		</div>
	);
}

function Chip({
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
				<XIcon className="size-3" />
			</button>
		</span>
	);
}

// ---------------------------------------------------------------------------
// 3c. Result card
// ---------------------------------------------------------------------------

function ResultCard({
	result: r,
	query,
	view,
	viewMode,
	selected,
	onToggle,
	onOpen,
}: {
	result: Result;
	query: string;
	view: "list" | "grid";
	viewMode: "full" | "listings";
	selected: boolean;
	onToggle: () => void;
	onOpen: () => void;
}) {
	const k = KIND[r.kind];
	const Icon = k.icon;
	const context =
		r.kind === "case" || r.kind === "brief"
			? r.court
			: r.kind === "statute"
				? "Iowa Code"
				: r.kind === "rule"
					? "Iowa Court Rules"
					: r.kind === "journal"
						? "Law review"
						: "Treatise";

	return (
		<div
			className={cn(
				"group flex items-start gap-3 transition-colors",
				view === "grid"
					? "rounded-lg border bg-card p-3 hover:border-primary/40"
					: "px-1 py-3.5 hover:bg-accent/30",
				selected && "bg-primary/[0.04]",
			)}
		>
			{/* Checkbox — accessible label carries the citation-count badge */}
			<label className="mt-0.5 flex cursor-pointer items-center">
				<input
					type="checkbox"
					checked={selected}
					onChange={onToggle}
					aria-label={`Select ${r.title} — cited by ${r.citedBy}`}
					className="size-4 accent-primary"
				/>
			</label>

			<span
				className={cn(
					"mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md",
					k.tint,
				)}
			>
				<Icon className="size-4" />
			</span>

			<div className="min-w-0 flex-1">
				{/* Kind + treatment + cited-by */}
				<div className="flex flex-wrap items-center gap-x-2 gap-y-1">
					<span
						className={cn(
							"inline-flex items-center rounded px-1.5 py-0.5 font-medium text-[10px]",
							k.tint,
						)}
					>
						{k.label}
					</span>
					{r.treatment && <TreatmentBadge treatment={r.treatment} />}
					{r.citedBy > 0 && (
						<span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground tabular-nums">
							<QuoteIcon className="size-3" />
							Cited by {r.citedBy}
						</span>
					)}
					{!r.inPlan && (
						<span className="rounded border px-1.5 py-px text-[10px] text-muted-foreground">
							Not in plan
						</span>
					)}
				</div>

				{/* Title */}
				<h3 className="mt-1">
					<button
						type="button"
						onClick={onOpen}
						className="text-left font-semibold text-[15px] text-foreground leading-snug hover:text-primary hover:underline"
					>
						{highlight(r.title, query)}
					</button>
				</h3>

				{/* Court · date · citations */}
				<p className="mt-0.5 text-muted-foreground text-xs">
					{context && <span>{context}</span>}
					{context && r.date ? "  ·  " : ""}
					{r.date && <span className="tabular-nums">{fmtDate(r.date)}</span>}
				</p>
				{r.citations.length > 0 && (
					<p className="mt-0.5 truncate font-mono text-[11px] text-foreground/70">
						{r.citations.join("  ·  ")}
					</p>
				)}

				{/* Snippet */}
				<p
					className={cn(
						"mt-1.5 text-[13px] text-foreground/75 leading-relaxed",
						viewMode === "listings" ? "line-clamp-1" : "line-clamp-3",
					)}
				>
					{highlight(r.snippet, query)}
				</p>

				{/* Matching paragraphs */}
				{r.matchingParagraphs > 0 && (
					<button
						type="button"
						onClick={onOpen}
						className="mt-1.5 inline-flex items-center gap-1 font-medium text-[12px] text-primary hover:underline"
					>
						Show {r.matchingParagraphs} matching paragraph
						{r.matchingParagraphs === 1 ? "" : "s"}
						<ChevronRightIcon className="size-3" />
					</button>
				)}
			</div>
		</div>
	);
}

function TreatmentBadge({
	treatment,
}: {
	treatment: Exclude<Treatment, null>;
}) {
	const t = TREATMENT[treatment];
	const Icon = t.icon;
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<button
					type="button"
					aria-label={t.label}
					className={cn(
						"inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-[10px]",
						t.cls,
					)}
				>
					<Icon className="size-3" />
					{t.short}
				</button>
			</TooltipTrigger>
			<TooltipContent side="top">{t.label}</TooltipContent>
		</Tooltip>
	);
}

// ---------------------------------------------------------------------------
// Charts tab — lightweight visualizations over the (filtered) result set.
// ---------------------------------------------------------------------------

function ChartsPanel({ rows }: { rows: Result[] }) {
	// By content type (kind)
	const byKind = useMemo(() => {
		const m = new Map<Kind, number>();
		for (const r of rows) m.set(r.kind, (m.get(r.kind) ?? 0) + 1);
		return [...m.entries()].sort((a, b) => b[1] - a[1]);
	}, [rows]);
	const kindMax = Math.max(1, ...byKind.map(([, n]) => n));

	return (
		<div className="grid gap-4 lg:grid-cols-2">
			{/* Results over time (the same histogram, read-only) */}
			<section className="rounded-lg border bg-card p-4">
				<h3 className="font-medium text-[13px]">Results over time</h3>
				<p className="text-[11px] text-muted-foreground">By decade decided</p>
				<div className="mt-3 flex h-32 items-end gap-1">
					{DECADE_BUCKETS.map((b) => (
						<div
							key={b.decade}
							className="flex flex-1 flex-col items-center gap-1"
						>
							<div
								className="w-full rounded-t bg-primary/80"
								style={{
									height: `${Math.max(4, (b.count / HISTO_MAX) * 100)}%`,
								}}
								title={`${b.decade}s — ${b.count}`}
							/>
							<span className="text-[9px] text-muted-foreground tabular-nums">
								&rsquo;{String(b.decade).slice(2)}
							</span>
						</div>
					))}
				</div>
			</section>

			{/* By content type */}
			<section className="rounded-lg border bg-card p-4">
				<h3 className="font-medium text-[13px]">By content type</h3>
				<p className="text-[11px] text-muted-foreground">
					Distribution of shown results
				</p>
				<div className="mt-3 space-y-2">
					{byKind.map(([kind, n]) => (
						<div key={kind} className="flex items-center gap-2">
							<span className="w-20 shrink-0 text-[12px] text-muted-foreground">
								{KIND[kind].label}
							</span>
							<div className="h-4 flex-1 overflow-hidden rounded bg-muted">
								<div
									className={cn("h-full rounded", KIND[kind].tint)}
									style={{ width: `${(n / kindMax) * 100}%` }}
								/>
							</div>
							<span className="w-6 shrink-0 text-right text-[12px] tabular-nums">
								{n}
							</span>
						</div>
					))}
				</div>
			</section>

			<section className="rounded-lg border border-dashed bg-card/50 p-4 lg:col-span-2">
				<p className="flex items-center gap-2 text-[12px] text-muted-foreground">
					<BarChart3Icon className="size-3.5" />
					Charts are illustrative — the live search endpoint doesn&rsquo;t
					return aggregate facets yet.
				</p>
			</section>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Highlight — wrap query terms in <mark>. JSX children auto-escape; cosmetic.
// ---------------------------------------------------------------------------

function highlight(text: string, query: string): ReactNode {
	const terms = [
		...new Set(
			query
				.toLowerCase()
				.split(/\s+/)
				.map((t) => t.trim().replace(/[^\w]/g, ""))
				.filter((t) => t.length >= 2 && t !== "v"),
		),
	].sort((a, b) => b.length - a.length);
	if (terms.length === 0) return text;
	const re = new RegExp(
		`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
		"gi",
	);
	return text.split(re).map((part, i) =>
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
