"use client";

// The /browse landing — a Westlaw/Lexis-grade "Library" home. Rendered when the
// browser is in "home" mode (no search, no open source). It lists the real
// corpus sources (passed in from the page's /api/browse/sources fetch) as a
// dense, scannable grid with live counts, plus a keyword search box (with an
// inline advanced-search panel) and a small honest rail (coverage + search
// tips). State/Federal tabs derive from each source's jurisdiction. Promoted
// from the /browse-mockup design; the royal accent + higher-contrast light
// palette are the app-wide light theme (globals.css `:root`).

import {
	BookOpenIcon,
	ChevronRightIcon,
	GavelIcon,
	LandmarkIcon,
	type LucideIcon,
	ScaleIcon,
	SearchIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
	type AdvancedFilters,
	filterChips,
} from "@/components/browse/advanced-search";
import { Button } from "@/components/ui/button";
import type { BrowseSource } from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

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

// State vs federal from the jurisdiction name (everything is Iowa today, so the
// Federal tab is honestly empty).
function scopeOf(s: BrowseSource): "state" | "federal" {
	return /federal|united states|u\.s\./i.test(s.jurisdiction)
		? "federal"
		: "state";
}

export function LibraryHome({
	sources,
	query,
	onQueryChange,
	filters,
	onSubmit,
	onOpenSource,
}: {
	sources: BrowseSource[] | null;
	query: string;
	onQueryChange: (q: string) => void;
	filters: AdvancedFilters;
	onSubmit: () => void;
	onOpenSource: (slug: string) => void;
}) {
	const [tab, setTab] = useState<Scope>("all");

	const jurisdictions = useMemo(
		() => [...new Set((sources ?? []).map((s) => s.jurisdiction))],
		[sources],
	);
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
	const chips = filterChips(filters);
	// Carry whatever is in the search box into the full-page advanced builder.
	const advancedHref = query.trim()
		? `/browse/advanced?q=${encodeURIComponent(query.trim())}`
		: "/browse/advanced";

	return (
		<main className="min-w-0 flex-1 overflow-y-auto">
			<div className="mx-auto max-w-6xl px-5 py-6">
				<h1 className="font-semibold text-xl tracking-tight">Library</h1>
				<p className="mt-0.5 text-muted-foreground text-xs">
					Search Iowa case law, statutes, and court rules — one box.
				</p>

				{/* Search */}
				<form
					className="mt-3"
					onSubmit={(e) => {
						e.preventDefault();
						onSubmit();
					}}
				>
					<div className="flex items-stretch rounded-lg border bg-card shadow-xs transition focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
						<div className="relative flex flex-1 items-center">
							<SearchIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
							<input
								value={query}
								onChange={(e) => onQueryChange(e.target.value)}
								placeholder="Search by keyword, citation, or party name…"
								aria-label="Search the corpus"
								className="h-11 w-full bg-transparent pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground"
							/>
						</div>
						<div className="flex items-center p-1.5">
							<Button type="submit" size="sm" className="h-8 gap-1.5 px-4">
								<SearchIcon className="size-3.5" />
								Search
							</Button>
						</div>
					</div>

					<div className="mt-2 flex items-center justify-between gap-2">
						<Link
							href={advancedHref}
							className="inline-flex items-center gap-1 text-muted-foreground text-xs hover:text-foreground"
						>
							<SlidersHorizontalIcon className="size-3.5" />
							Advanced search
						</Link>
						{chips.length > 0 && (
							<span className="text-muted-foreground text-xs">
								{chips.join(" · ")}
							</span>
						)}
					</div>
				</form>

				{/* Tabs */}
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

				{/* Source grid + rail */}
				<div className="mt-4 grid gap-5 lg:grid-cols-[1fr_18rem]">
					<div className="min-w-0">
						<div className="overflow-hidden rounded-lg border bg-card">
							{!sources ? (
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
											onOpen={() => onOpenSource(s.slug)}
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
					</div>

					{/* Rail */}
					<aside className="space-y-4">
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
									value={jurisdictions.length ? jurisdictions.join(", ") : "—"}
								/>
							</dl>
						</RailPanel>

						<RailPanel title="Search tips" icon={SearchIcon}>
							<ul className="space-y-1.5 px-3 py-2 text-[12px] text-muted-foreground leading-snug">
								<li>
									Combine terms with <span className="font-mono">AND</span>,{" "}
									<span className="font-mono">OR</span>, and{" "}
									<span className="font-mono">-exclude</span>.
								</li>
								<li>
									Quote an{" "}
									<span className="font-mono">&ldquo;exact phrase&rdquo;</span>.
								</li>
								<li>
									Paste a citation (e.g.{" "}
									<span className="font-mono">714.16</span>) to jump straight to
									it.
								</li>
							</ul>
						</RailPanel>
					</aside>
				</div>
			</div>
		</main>
	);
}

// ---------------------------------------------------------------------------
// Bits
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

function RailPanel({
	title,
	icon: Icon,
	children,
}: {
	title: string;
	icon: LucideIcon;
	children: React.ReactNode;
}) {
	return (
		<section className="overflow-hidden rounded-lg border bg-card">
			<header className="flex items-center gap-1.5 border-b px-3 py-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
				<Icon className="size-3.5" />
				{title}
			</header>
			{children}
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
