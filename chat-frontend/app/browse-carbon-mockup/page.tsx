"use client";

// Carbon (IBM design system) mockup of the corpus browser's Library home —
// a design exploration only, NOT wired to the live app. Lives at
// /browse-carbon-mockup so the real /browse and its components are untouched;
// everything here is self-contained (own fonts, own tokens, static data).
//
// Static data mirrors the live /api/browse/sources counts (2026-07):
// 76,293 decisions + 27,869 sections + 1,193 rules = 105,355 documents.
//
// The sun/moon control in the header toggles between Carbon's "white" and
// "g100" themes. Tokens (Carbon v11) are applied as CSS custom properties on
// the page wrapper, so both themes share one markup tree:
//   white: bg #ffffff  layer #f4f4f4  hairline #e0e0e0  link Blue60 #0f62fe
//   g100:  bg #161616  layer #262626  hairline #393939  link Blue40 #78a9ff
// The UI-shell header stays g100-dark in both themes, per Carbon convention.

import {
	ArrowRightIcon,
	GavelIcon,
	GitCompareArrowsIcon,
	LandmarkIcon,
	type LucideIcon,
	MenuIcon,
	MoonIcon,
	ScaleIcon,
	SearchIcon,
	SlidersHorizontalIcon,
	SunIcon,
} from "lucide-react";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { useState } from "react";
import { cn } from "@/lib/utils";

const plexSans = IBM_Plex_Sans({
	weight: ["300", "400", "600"],
	subsets: ["latin"],
	variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
	weight: ["400"],
	subsets: ["latin"],
	variable: "--font-plex-mono",
});

// ---------------------------------------------------------------------------
// Carbon v11 theme tokens
// ---------------------------------------------------------------------------

type ThemeName = "white" | "g100";

const THEMES: Record<ThemeName, Record<string, string>> = {
	white: {
		"--cds-bg": "#ffffff",
		"--cds-layer": "#f4f4f4",
		"--cds-layer-hover": "#e8e8e8",
		"--cds-layer-selected": "#e0e0e0",
		"--cds-field": "#f4f4f4",
		"--cds-border": "#e0e0e0",
		"--cds-border-strong": "#8d8d8d",
		"--cds-text": "#161616",
		"--cds-text-2": "#525252",
		"--cds-helper": "#6f6f6f",
		"--cds-placeholder": "#a8a8a8",
		"--cds-link": "#0f62fe",
	},
	g100: {
		"--cds-bg": "#161616",
		"--cds-layer": "#262626",
		"--cds-layer-hover": "#333333",
		"--cds-layer-selected": "#393939",
		"--cds-field": "#262626",
		"--cds-border": "#393939",
		"--cds-border-strong": "#6f6f6f",
		"--cds-text": "#f4f4f4",
		"--cds-text-2": "#c6c6c6",
		"--cds-helper": "#8d8d8d",
		"--cds-placeholder": "#6f6f6f",
		"--cds-link": "#78a9ff",
	},
};

// ---------------------------------------------------------------------------
// Static corpus data (mirrors /api/browse/sources)
// ---------------------------------------------------------------------------

type Source = {
	slug: string;
	name: string;
	blurb: string;
	entries: number;
	entryLabel: string;
	icon: LucideIcon;
};

const SOURCES: Source[] = [
	{
		slug: "iowa-caselaw",
		name: "Iowa Caselaw",
		blurb: "Reported & unreported decisions",
		entries: 76_293,
		entryLabel: "decisions",
		icon: ScaleIcon,
	},
	{
		slug: "iowa-code",
		name: "Iowa Code",
		blurb: "Codified Iowa statutes",
		entries: 27_869,
		entryLabel: "sections",
		icon: LandmarkIcon,
	},
	{
		slug: "iowa-court-rules",
		name: "Iowa Court Rules",
		blurb: "Rules of procedure & evidence",
		entries: 1_193,
		entryLabel: "rules",
		icon: GavelIcon,
	},
];

const TOTAL_DOCS = SOURCES.reduce((n, s) => n + s.entries, 0);

type Scope = "all" | "state" | "federal";

const TABS: { id: Scope; label: string }[] = [
	{ id: "all", label: "All content" },
	{ id: "state", label: "State" },
	{ id: "federal", label: "Federal" },
];

// Everything in the corpus is Iowa (state) today; the Federal tab is honestly
// empty, same as the live Library home.
const tabCount = (id: Scope) => (id === "federal" ? 0 : SOURCES.length);

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BrowseCarbonMockupPage() {
	const [theme, setTheme] = useState<ThemeName>("g100");
	const [tab, setTab] = useState<Scope>("all");
	const [activeSlug, setActiveSlug] = useState<string | null>(null);
	const [query, setQuery] = useState("");

	const shown = tab === "federal" ? [] : SOURCES;

	return (
		<div
			className={cn(
				"flex h-dvh flex-col bg-[var(--cds-bg)] text-[var(--cds-text)]",
				plexSans.variable,
				plexMono.variable,
			)}
			style={
				{
					...THEMES[theme],
					fontFamily: "var(--font-plex-sans)",
					// font-mono utilities resolve --font-geist-mono in this app, so
					// pointing it at Plex Mono re-skins mono usage inside this page only.
					"--font-geist-mono": "var(--font-plex-mono)",
				} as React.CSSProperties
			}
		>
			<ShellHeader theme={theme} onToggleTheme={setTheme} />

			<div className="flex min-h-0 flex-1">
				<SideNav activeSlug={activeSlug} onOpenSource={setActiveSlug} />

				<main className="min-w-0 flex-1 overflow-y-auto">
					{/* Full-window search interface — no max-width cap; the rail widens
					    a touch on very large screens so the source list carries the rest. */}
					<div className="px-5 py-10 sm:px-8 lg:py-14">
						<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
							Iowa corpus — {TOTAL_DOCS.toLocaleString()} documents
						</p>
						<h1 className="mt-4 font-light text-3xl sm:text-4xl">Library</h1>
						<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
							Search Iowa case law, statutes, and court rules — one box.
						</p>

						<SearchField query={query} onQueryChange={setQuery} />

						<Tabs tab={tab} onTab={setTab} />

						<div className="mt-8 grid gap-10 lg:grid-cols-[1fr_17rem] xl:grid-cols-[1fr_20rem]">
							<div className="min-w-0">
								{shown.length === 0 ? (
									<div className="border border-[var(--cds-border)] px-6 py-14 text-center text-[var(--cds-text-2)] text-sm">
										No federal sources yet.
									</div>
								) : (
									<div className="divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
										{shown.map((s) => (
											<SourceRow
												key={s.slug}
												source={s}
												active={activeSlug === s.slug}
												onOpen={() => setActiveSlug(s.slug)}
											/>
										))}
									</div>
								)}
								{shown.length > 0 && (
									<p className="mt-3 text-[var(--cds-helper)] text-xs">
										{shown.length} sources
										{tab !== "all" && ` · ${tab} materials`}
									</p>
								)}
							</div>

							<Rail />
						</div>
					</div>
				</main>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// UI shell header — g100-dark in both themes, per Carbon
// ---------------------------------------------------------------------------

function ShellHeader({
	theme,
	onToggleTheme,
}: {
	theme: ThemeName;
	onToggleTheme: (t: ThemeName) => void;
}) {
	const next: ThemeName = theme === "g100" ? "white" : "g100";
	return (
		<header className="flex h-12 shrink-0 items-center border-[#393939] border-b bg-[#161616] text-white">
			<button
				type="button"
				aria-label="Menu"
				className="flex size-12 items-center justify-center transition-colors hover:bg-[#353535]"
			>
				<MenuIcon className="size-4" />
			</button>

			<p className="text-sm">
				<span className="font-semibold">HUDSON</span>
				<span className="ml-2 text-[#a8a8a8]">Corpus</span>
			</p>

			<p className="ml-6 hidden font-mono text-[#6f6f6f] text-[11px] uppercase tracking-[0.2em] sm:block">
				Carbon mockup — not the live app
			</p>

			<div className="ml-auto flex items-center">
				<span className="mr-1 hidden font-mono text-[#a8a8a8] text-[11px] sm:block">
					theme: {theme}
				</span>
				<button
					type="button"
					onClick={() => onToggleTheme(next)}
					aria-label={`Switch to ${next} theme`}
					title={`Switch to ${next} theme`}
					className="flex size-12 items-center justify-center transition-colors hover:bg-[#353535]"
				>
					{theme === "g100" ? (
						<SunIcon className="size-4" />
					) : (
						<MoonIcon className="size-4" />
					)}
				</button>
				<span className="flex size-12 items-center justify-center bg-[#0f62fe] font-semibold text-xs">
					NH
				</span>
			</div>
		</header>
	);
}

// ---------------------------------------------------------------------------
// Side nav — flat source list, Carbon side-nav register
// ---------------------------------------------------------------------------

function NavGroupLabel({ children }: { children: React.ReactNode }) {
	return (
		<p className="px-4 pt-6 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
			{children}
		</p>
	);
}

function NavItem({
	icon: Icon,
	label,
	detail,
	active,
	onClick,
}: {
	icon: LucideIcon;
	label: string;
	detail?: string;
	active?: boolean;
	onClick?: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"flex w-full items-start gap-3 border-l-[3px] px-3.5 py-2 text-left transition-colors",
				active
					? "border-[#0f62fe] bg-[var(--cds-layer-selected)]"
					: "border-transparent text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]",
			)}
		>
			<Icon className="mt-0.5 size-4 shrink-0" strokeWidth={1.5} />
			<span className="flex min-w-0 flex-col">
				<span className={cn("truncate text-sm", active && "font-semibold")}>
					{label}
				</span>
				{detail && (
					<span className="truncate text-[var(--cds-helper)] text-xs tabular-nums">
						{detail}
					</span>
				)}
			</span>
		</button>
	);
}

function SideNav({
	activeSlug,
	onOpenSource,
}: {
	activeSlug: string | null;
	onOpenSource: (slug: string) => void;
}) {
	return (
		<nav className="hidden w-64 shrink-0 flex-col overflow-y-auto border-[var(--cds-border)] border-r md:flex">
			<div className="flex-1">
				<NavGroupLabel>Search</NavGroupLabel>
				<NavItem
					icon={SearchIcon}
					label="Search the corpus"
					active={!activeSlug}
				/>
				<NavItem icon={SlidersHorizontalIcon} label="Advanced search" />
				<NavItem icon={GitCompareArrowsIcon} label="Compare editions" />

				<NavGroupLabel>Sources</NavGroupLabel>
				{SOURCES.map((s) => (
					<NavItem
						key={s.slug}
						icon={s.icon}
						label={s.name}
						detail={`${s.entries.toLocaleString()} ${s.entryLabel}`}
						active={activeSlug === s.slug}
						onClick={() => onOpenSource(s.slug)}
					/>
				))}
			</div>

			<div className="border-[var(--cds-border)] border-t px-4 py-4">
				<p className="font-mono text-[11px] text-[var(--cds-helper)]">
					corpus.nick.law · beta
				</p>
			</div>
		</nav>
	);
}

// ---------------------------------------------------------------------------
// Search field — Carbon fluid input: square, field bg, strong bottom border
// ---------------------------------------------------------------------------

function SearchField({
	query,
	onQueryChange,
}: {
	query: string;
	onQueryChange: (q: string) => void;
}) {
	return (
		<form className="mt-8" onSubmit={(e) => e.preventDefault()}>
			<div className="flex items-stretch">
				<div className="relative flex flex-1 items-center border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
					<SearchIcon className="pointer-events-none absolute left-4 size-4 text-[var(--cds-text-2)]" />
					<input
						value={query}
						onChange={(e) => onQueryChange(e.target.value)}
						placeholder="Search by keyword, citation, or party name…"
						aria-label="Search the corpus"
						className="h-12 w-full bg-transparent pr-4 pl-11 text-sm outline-none placeholder:text-[var(--cds-placeholder)]"
					/>
				</div>
				<button
					type="submit"
					className="flex h-12 items-center gap-8 bg-[#0f62fe] px-5 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
				>
					Search
					<ArrowRightIcon className="size-4" />
				</button>
			</div>

			<div className="mt-3">
				<span className="inline-flex cursor-pointer items-center gap-1.5 font-medium text-[13px] text-[var(--cds-link)] hover:underline">
					<SlidersHorizontalIcon className="size-3.5" />
					Advanced search
				</span>
			</div>
		</form>
	);
}

// ---------------------------------------------------------------------------
// Tabs — Carbon line tabs: 2px bottom border, no pills
// ---------------------------------------------------------------------------

function Tabs({ tab, onTab }: { tab: Scope; onTab: (t: Scope) => void }) {
	return (
		<div className="mt-10 border-[var(--cds-border)] border-b">
			<div className="flex gap-8">
				{TABS.map((t) => {
					const active = t.id === tab;
					return (
						<button
							key={t.id}
							type="button"
							onClick={() => onTab(t.id)}
							className={cn(
								"-mb-px border-b-2 px-0.5 pb-2.5 text-[13px] transition-colors",
								active
									? "border-[#0f62fe] font-semibold"
									: "border-transparent text-[var(--cds-text-2)] hover:border-[var(--cds-border-strong)] hover:text-[var(--cds-text)]",
							)}
						>
							{t.label}
							<span className="ml-1.5 text-[var(--cds-helper)] tabular-nums">
								{tabCount(t.id)}
							</span>
						</button>
					);
				})}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Source rows — hairline-ruled tiles, whole row clickable
// ---------------------------------------------------------------------------

function SourceRow({
	source,
	active,
	onOpen,
}: {
	source: Source;
	active: boolean;
	onOpen: () => void;
}) {
	const Icon = source.icon;
	return (
		<button
			type="button"
			onClick={onOpen}
			className={cn(
				"group flex w-full items-center gap-4 p-4 text-left transition-colors sm:p-5",
				active
					? "bg-[var(--cds-layer-selected)]"
					: "bg-[var(--cds-layer)] hover:bg-[var(--cds-layer-hover)]",
			)}
		>
			<Icon
				className="size-5 shrink-0 text-[var(--cds-text-2)]"
				strokeWidth={1.5}
			/>
			<span className="flex min-w-0 flex-1 flex-col">
				<span className="truncate font-semibold text-sm">{source.name}</span>
				<span className="truncate text-[var(--cds-text-2)] text-xs">
					{source.blurb}
				</span>
			</span>
			<span className="shrink-0 whitespace-nowrap font-mono text-[var(--cds-helper)] text-xs tabular-nums">
				{source.entries.toLocaleString()} {source.entryLabel}
			</span>
			<ArrowRightIcon className="size-4 shrink-0 text-[var(--cds-link)] transition-transform group-hover:translate-x-0.5" />
		</button>
	);
}

// ---------------------------------------------------------------------------
// Rail — coverage + search tips as Carbon structured lists
// ---------------------------------------------------------------------------

function RailPanel({
	title,
	children,
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section className="border border-[var(--cds-border)]">
			<header className="border-[var(--cds-border)] border-b px-4 py-2.5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				{title}
			</header>
			{children}
		</section>
	);
}

function Rail() {
	return (
		<aside className="space-y-6">
			<RailPanel title="Coverage">
				<dl className="divide-y divide-[var(--cds-border)] text-xs">
					{(
						[
							["Documents", TOTAL_DOCS.toLocaleString()],
							["Sources", String(SOURCES.length)],
							["Jurisdiction", "Iowa"],
						] as const
					).map(([label, value]) => (
						<div
							key={label}
							className="flex items-center justify-between gap-3 px-4 py-2.5"
						>
							<dt className="text-[var(--cds-text-2)]">{label}</dt>
							<dd className="font-medium tabular-nums">{value}</dd>
						</div>
					))}
				</dl>
			</RailPanel>

			<RailPanel title="Search tips">
				<ul className="space-y-2 px-4 py-3 text-[12px] text-[var(--cds-text-2)] leading-snug">
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
						Paste a citation (e.g. <span className="font-mono">714.16</span>) to
						jump straight to it.
					</li>
				</ul>
			</RailPanel>
		</aside>
	);
}
