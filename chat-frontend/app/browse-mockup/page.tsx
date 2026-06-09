"use client";

// Design mockup for a redesigned browse home — a Westlaw/Lexis-grade research
// "Library". Self-contained on its own route (/browse-mockup) so it can be shown
// and iterated on without touching the live /browse flow. Tuned for *density*:
// a compact utility bar, a tight source grid with real counts, and a supporting
// rail (recent work, tools, coverage). The content grid is now wired to the REAL
// corpus: it fetches /api/browse/sources and shows one card per source we
// actually have (Iowa Code, Court Rules, Caselaw) with live counts. Search runs
// the real /browse?q= corpus search; a card opens that source via
// /browse?source=<slug>. (Recents/tools are still illustrative.)

import {
	AlertCircleIcon,
	ArrowUpRightIcon,
	BadgeCheckIcon,
	BookmarkIcon,
	BookOpenIcon,
	ChevronDownIcon,
	ChevronRightIcon,
	GavelIcon,
	GitCompareArrowsIcon,
	HashIcon,
	HistoryIcon,
	LandmarkIcon,
	ListTreeIcon,
	Loader2Icon,
	type LucideIcon,
	MapPinIcon,
	ScaleIcon,
	SearchIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { MockupSidebar } from "@/components/browse/mockup-sidebar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import { type BrowseSource, browseSources } from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

const ADVANCED_HREF = "/browse-mockup/advanced";

// ---------------------------------------------------------------------------
// Source presentation — per-slug icon + blurb, with kind fallbacks
// ---------------------------------------------------------------------------

type Scope = "all" | "state" | "federal";

const TABS: { id: Scope; label: string }[] = [
	{ id: "all", label: "All Content" },
	{ id: "state", label: "State" },
	{ id: "federal", label: "Federal" },
];

const SOURCE_VIEW: Record<string, { icon: LucideIcon; blurb: string }> = {
	"iowa-caselaw": { icon: ScaleIcon, blurb: "Reported & unreported decisions" },
	"iowa-code": { icon: LandmarkIcon, blurb: "Codified Iowa statutes" },
	"iowa-court-rules": {
		icon: GavelIcon,
		blurb: "Rules of procedure & evidence",
	},
};

function viewFor(s: BrowseSource): { icon: LucideIcon; blurb: string } {
	return (
		SOURCE_VIEW[s.slug] ?? {
			icon: s.kind === "caselaw" ? ScaleIcon : BookOpenIcon,
			blurb: s.entry_label,
		}
	);
}

// State vs federal from the source's jurisdiction name (everything is Iowa
// today, so Federal comes back empty — shown honestly).
function scopeOf(s: BrowseSource): "state" | "federal" {
	return /federal|united states|u\.s\./i.test(s.jurisdiction)
		? "federal"
		: "state";
}

// Illustrative recent searches (still mock — clearly a UI element, not content).
type Recent = { query: string; q: string; scope: string; when: string };
const RECENTS: Recent[] = [
	{
		query: "consumer fraud",
		q: "consumer fraud",
		scope: "All content",
		when: "2 hours ago",
	},
	{
		query: "State v. Brown",
		q: "State v. Brown",
		scope: "Case law",
		when: "Yesterday",
	},
	{
		query: "Iowa Code § 714.16",
		q: "714.16",
		scope: "Statutes",
		when: "2 days ago",
	},
	{
		query: "premises liability",
		q: "premises liability",
		scope: "Case law",
		when: "4 days ago",
	},
	{
		query: "private right of action",
		q: '"private right of action"',
		scope: "Case law",
		when: "5 days ago",
	},
	{
		query: "negligence per se",
		q: "negligence per se",
		scope: "All content",
		when: "1 week ago",
	},
];

const TOOLS: { icon: LucideIcon; label: string; href?: string }[] = [
	{ icon: HashIcon, label: "Citation lookup" },
	{
		icon: GitCompareArrowsIcon,
		label: "Compare editions",
		href: "/browse/compare",
	},
	{
		icon: SlidersHorizontalIcon,
		label: "Advanced search",
		href: ADVANCED_HREF,
	},
	{ icon: BadgeCheckIcon, label: "Citator" },
	{ icon: ListTreeIcon, label: "Tables & indexes" },
	{ icon: BookmarkIcon, label: "Saved research" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BrowseMockupPage() {
	const router = useRouter();
	const [query, setQuery] = useState("");
	const [tab, setTab] = useState<Scope>("all");

	// Real corpus sources.
	const [sources, setSources] = useState<BrowseSource[] | null>(null);
	const [sourcesError, setSourcesError] = useState<string | null>(null);
	useEffect(() => {
		let cancelled = false;
		browseSources()
			.then((s) => !cancelled && setSources(s))
			.catch((e) => {
				if (!cancelled)
					setSourcesError(
						e instanceof Error ? e.message : "Failed to load corpus sources.",
					);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const jurisdictions = useMemo(
		() => [...new Set((sources ?? []).map((s) => s.jurisdiction))],
		[sources],
	);
	const [jurisdiction, setJurisdiction] = useState("All jurisdictions");
	const totalDocs = useMemo(
		() => (sources ?? []).reduce((n, s) => n + s.entries, 0),
		[sources],
	);

	const shown = useMemo(() => {
		if (!sources) return [];
		return tab === "all" ? sources : sources.filter((s) => scopeOf(s) === tab);
	}, [sources, tab]);
	const tabCount = (id: Scope) =>
		!sources
			? 0
			: id === "all"
				? sources.length
				: sources.filter((s) => scopeOf(s) === id).length;

	const runSearch = (q: string) => {
		const trimmed = q.trim();
		if (!trimmed) return;
		router.push(`/browse?q=${encodeURIComponent(trimmed)}`);
	};
	const openSource = (slug: string) =>
		router.push(`/browse?source=${encodeURIComponent(slug)}`);

	return (
		<SidebarProvider>
			<div className="flex h-dvh w-full pr-0.5">
				<MockupSidebar />
				<SidebarInset>
					<header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
						<SidebarTrigger />
						<Separator orientation="vertical" className="mr-1 h-4" />
						<span className="font-medium text-sm">Library</span>
						{sources && (
							<span className="ml-auto hidden text-muted-foreground text-xs sm:inline">
								{totalDocs.toLocaleString()} documents ·{" "}
								{jurisdictions.join(", ")}
							</span>
						)}
					</header>

					<main className="min-w-0 flex-1 overflow-y-auto">
						<div className="mx-auto max-w-6xl px-5 py-5">
							{/* ---- Utility bar: title + quick actions ------------------- */}
							<div className="flex items-end justify-between gap-4">
								<div className="min-w-0">
									<h1 className="font-semibold text-xl tracking-tight">
										Library
									</h1>
									<p className="mt-0.5 truncate text-muted-foreground text-xs">
										Search Iowa case law, statutes, and court rules — one box.
									</p>
								</div>
								<div className="hidden shrink-0 items-center gap-1 sm:flex">
									<Button asChild variant="ghost" size="sm">
										<Link href={ADVANCED_HREF}>
											<SlidersHorizontalIcon className="size-3.5" />
											Advanced
										</Link>
									</Button>
									<Button asChild variant="ghost" size="sm">
										<Link href="/browse/compare">
											<GitCompareArrowsIcon className="size-3.5" />
											Compare editions
										</Link>
									</Button>
									<Button variant="ghost" size="sm">
										<HistoryIcon className="size-3.5" />
										History
									</Button>
								</div>
							</div>

							{/* ---- Search ---------------------------------------------- */}
							<form
								className="mt-3"
								onSubmit={(e) => {
									e.preventDefault();
									runSearch(query);
								}}
							>
								<div className="flex items-stretch rounded-lg border bg-card shadow-xs transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
									<div className="relative flex flex-1 items-center">
										<SearchIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
										<input
											value={query}
											onChange={(e) => setQuery(e.target.value)}
											placeholder="Search by keyword, citation, or party name…"
											aria-label="Search the library"
											className="h-11 w-full bg-transparent pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground"
										/>
									</div>

									<div className="my-2 w-px bg-border" />
									<div className="relative flex items-center">
										<MapPinIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-3.5 text-muted-foreground" />
										<select
											value={jurisdiction}
											onChange={(e) => setJurisdiction(e.target.value)}
											aria-label="Jurisdiction"
											className="h-full cursor-pointer appearance-none bg-transparent pr-8 pl-8 font-medium text-foreground text-sm outline-none"
										>
											{["All jurisdictions", ...jurisdictions].map((j) => (
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
											className="h-8 gap-1.5 px-4"
										>
											<SearchIcon className="size-3.5" />
											Search
										</Button>
									</div>
								</div>
								<p className="mt-2 text-muted-foreground text-xs">
									Try{" "}
									<button
										type="button"
										onClick={() => setQuery("consumer fraud")}
										className="font-medium text-foreground/80 hover:text-foreground hover:underline"
									>
										consumer fraud
									</button>
									,{" "}
									<button
										type="button"
										onClick={() => setQuery("714.16")}
										className="font-mono text-foreground/80 hover:text-foreground hover:underline"
									>
										714.16
									</button>
									, or build a precise query in{" "}
									<Link
										href={ADVANCED_HREF}
										className="font-medium text-foreground/80 hover:text-foreground hover:underline"
									>
										advanced search
									</Link>
									.
								</p>
							</form>

							{/* ---- Tabs ------------------------------------------------ */}
							<div className="mt-5 border-b">
								<div className="flex gap-6">
									{TABS.map((t) => {
										const active = t.id === tab;
										return (
											<button
												key={t.id}
												type="button"
												onClick={() => setTab(t.id)}
												className={cn(
													"-mb-px flex items-center gap-1.5 border-b-2 px-0.5 pb-2 font-medium text-[13px] transition-colors",
													active
														? "border-foreground text-foreground"
														: "border-transparent text-muted-foreground hover:text-foreground",
												)}
											>
												{t.label}
												{sources && (
													<span
														className={cn(
															"rounded px-1 py-px text-[10px] tabular-nums",
															active
																? "bg-primary/10 text-foreground"
																: "bg-muted text-muted-foreground",
														)}
													>
														{tabCount(t.id)}
													</span>
												)}
											</button>
										);
									})}
								</div>
							</div>

							{/* ---- Source grid + rail ---------------------------------- */}
							<div className="mt-4 grid gap-5 lg:grid-cols-[1fr_18rem]">
								<div className="min-w-0">
									<div className="overflow-hidden rounded-lg border bg-card">
										{sourcesError ? (
											<div className="flex items-start gap-2 p-4 text-destructive text-sm">
												<AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
												<span>{sourcesError}</span>
											</div>
										) : !sources ? (
											<SkeletonGrid />
										) : shown.length === 0 ? (
											<div className="px-4 py-10 text-center text-muted-foreground text-sm">
												No {tab} sources yet.
											</div>
										) : (
											<div className="grid grid-cols-1 sm:grid-cols-2">
												{shown.map((s) => (
													<SourceCard
														key={s.slug}
														source={s}
														onOpen={() => openSource(s.slug)}
													/>
												))}
											</div>
										)}
									</div>
									{sources && shown.length > 0 && (
										<p className="mt-2 text-muted-foreground text-xs">
											{shown.length} {shown.length === 1 ? "source" : "sources"}
											{tab !== "all" && ` · ${tab} materials`}
										</p>
									)}

									{/* Recent searches — plain text links, below the grid */}
									<section className="mt-4 overflow-hidden rounded-lg border bg-card">
										<header className="flex items-center justify-between border-b px-3 py-2">
											<span className="flex items-center gap-1.5 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
												<HistoryIcon className="size-3.5" />
												Recent searches
											</span>
											<button
												type="button"
												className="text-[11px] text-muted-foreground hover:text-foreground"
											>
												Clear history
											</button>
										</header>
										<ul className="p-1.5">
											{RECENTS.map((r) => (
												<li key={r.query}>
													<button
														type="button"
														onClick={() => runSearch(r.q)}
														className="group flex w-full items-baseline justify-between gap-3 rounded px-2.5 py-1.5 text-left transition-colors hover:bg-accent/40"
													>
														<span className="min-w-0 truncate">
															<span className="text-[13px] text-foreground group-hover:text-primary group-hover:underline">
																{r.query}
															</span>
															<span className="ml-2 text-[11px] text-muted-foreground">
																{r.scope}
															</span>
														</span>
														<span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
															{r.when}
														</span>
													</button>
												</li>
											))}
										</ul>
									</section>
								</div>

								{/* Rail */}
								<aside className="space-y-4">
									<RailPanel
										title="Research tools"
										icon={SlidersHorizontalIcon}
									>
										{TOOLS.map((t) => {
											const Icon = t.icon;
											const inner = (
												<>
													<Icon className="size-3.5 shrink-0 text-muted-foreground" />
													<span className="min-w-0 flex-1 truncate text-[13px]">
														{t.label}
													</span>
													<ArrowUpRightIcon className="size-3 shrink-0 text-muted-foreground/50" />
												</>
											);
											const cls =
												"flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-accent/50";
											return t.href ? (
												<Link key={t.label} href={t.href} className={cls}>
													{inner}
												</Link>
											) : (
												<button key={t.label} type="button" className={cls}>
													{inner}
												</button>
											);
										})}
									</RailPanel>

									<RailPanel title="Coverage" icon={BookOpenIcon}>
										<dl className="space-y-1.5 px-3 py-2 text-xs">
											<CoverageRow
												label="Documents"
												value={sources ? totalDocs.toLocaleString() : "—"}
											/>
											<CoverageRow
												label="Sources"
												value={sources ? String(sources.length) : "—"}
											/>
											<CoverageRow
												label="Jurisdiction"
												value={
													jurisdictions.length ? jurisdictions.join(", ") : "—"
												}
											/>
										</dl>
									</RailPanel>
								</aside>
							</div>
						</div>
					</main>
				</SidebarInset>
			</div>
		</SidebarProvider>
	);
}

// ---------------------------------------------------------------------------
// Source card — compact icon tile + name/blurb + live count + chevron
// ---------------------------------------------------------------------------

function SourceCard({
	source,
	onOpen,
}: {
	source: BrowseSource;
	onOpen: () => void;
}) {
	const { icon: Icon, blurb } = viewFor(source);
	return (
		<button
			type="button"
			onClick={onOpen}
			className={cn(
				"group flex items-center gap-3 border-border p-2.5 text-left transition-colors hover:bg-accent/50",
				// Row separators via top borders; the top row and the center column
				// are tuned so the grid reads as clean hairlines.
				"border-t first:border-t-0 sm:[&:nth-child(2)]:border-t-0 sm:odd:border-r",
			)}
		>
			<span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
				<Icon className="size-4" />
			</span>
			<span className="flex min-w-0 flex-1 flex-col">
				<span className="truncate font-medium text-[13px] leading-tight">
					{source.name}
				</span>
				<span className="truncate text-[11px] text-muted-foreground leading-tight">
					{blurb}
				</span>
			</span>
			<span className="shrink-0 whitespace-nowrap text-[11px] text-muted-foreground tabular-nums">
				{source.entries.toLocaleString()} {source.entry_label.toLowerCase()}
			</span>
			<ChevronRightIcon className="size-3.5 shrink-0 text-muted-foreground/40 transition-all group-hover:translate-x-0.5 group-hover:text-foreground" />
		</button>
	);
}

function SkeletonGrid() {
	return (
		<div className="grid grid-cols-1 sm:grid-cols-2">
			{[0, 1, 2, 3].map((i) => (
				<div
					key={i}
					className="flex items-center gap-3 border-border border-t p-2.5 first:border-t-0 sm:odd:border-r sm:[&:nth-child(2)]:border-t-0"
				>
					<div className="size-8 shrink-0 animate-pulse rounded-md bg-muted" />
					<div className="flex-1 space-y-1.5">
						<div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
						<div className="h-2.5 w-1/2 animate-pulse rounded bg-muted" />
					</div>
				</div>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Rail panel — compact bordered section with a labelled header
// ---------------------------------------------------------------------------

function RailPanel({
	title,
	icon: Icon,
	action,
	children,
}: {
	title: string;
	icon: LucideIcon;
	action?: string;
	children: React.ReactNode;
}) {
	return (
		<section className="overflow-hidden rounded-lg border bg-card">
			<header className="flex items-center justify-between border-b px-3 py-2">
				<span className="flex items-center gap-1.5 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
					<Icon className="size-3.5" />
					{title}
				</span>
				{action && (
					<button
						type="button"
						className="text-[11px] text-muted-foreground hover:text-foreground"
					>
						{action}
					</button>
				)}
			</header>
			<div className="py-1">{children}</div>
		</section>
	);
}

function CoverageRow({ label, value }: { label: string; value: string }) {
	return (
		<div className="flex items-center justify-between gap-3">
			<dt className="text-muted-foreground">{label}</dt>
			<dd className="truncate font-medium tabular-nums">{value}</dd>
		</div>
	);
}
