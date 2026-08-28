"use client";

// Carbon case reader — /case/<id>, wired to /api/browse/cases/<id>.
//
// Layout (desktop): a 48px toolbar (breadcrumb + cite · find · copy · print ·
// Ask), then three panes — outline/details/display rail (lg+), the reading
// column (caption → authority strip → opinions), and the citator rail (xl+:
// Citing decisions · Authorities · Ask). Below xl the citator and Ask open
// in a drawer; below lg a bottom bar (Outline · Citator · Ask · Display)
// replaces both rails. Document structure (opinion parsing, outline,
// citation building, scroll-spy) comes from lib/case-format.ts; rendering
// pieces live in components/case-reader/.

import {
	CheckIcon,
	CopyIcon,
	ListIcon,
	MessageSquareTextIcon,
	PrinterIcon,
	ScaleIcon,
	SearchIcon,
	TypeIcon,
	XIcon,
} from "lucide-react";
import { IBM_Plex_Serif } from "next/font/google";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
	type ReactNode,
	Suspense,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { type DocAskHandle, useDocAsk } from "@/components/carbon/doc-ask";
import { Notification, Tag } from "@/components/carbon/primitives";
import { AuthorityStrip } from "@/components/case-reader/authority-strip";
import {
	CitatorPanel,
	type CitatorTab,
} from "@/components/case-reader/citator-rail";
import { CiteHoverProvider } from "@/components/case-reader/cite-hover-card";
import { Drawer } from "@/components/case-reader/drawer";
import { courtLong } from "@/components/case-reader/format";
import { OpinionBody, SegmentBody } from "@/components/case-reader/opinion";
import {
	Details,
	DisplayControls,
	Outline,
} from "@/components/case-reader/outline-rail";
import {
	buildCitation,
	caseSections,
	useActiveSection,
} from "@/lib/case-format";
import {
	browseCase,
	type CaseDetail,
	type CaseOpinion,
	fmtEffective,
} from "@/lib/iowa-browse";
import {
	loadReaderPrefs,
	type ReaderPrefs,
	saveReaderPrefs,
} from "@/lib/reader-prefs";
import { useSearchHighlight } from "@/lib/use-search-highlight";
import { cn } from "@/lib/utils";

const plexSerif = IBM_Plex_Serif({
	weight: ["400", "600"],
	style: ["normal", "italic"],
	subsets: ["latin"],
	variable: "--font-plex-serif",
});

// useSearchParams() must be read inside a Suspense boundary.
export default function V2CasePage() {
	return (
		<Suspense
			fallback={
				<div className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
					Loading…
				</div>
			}
		>
			<CasePageInner />
		</Suspense>
	);
}

function CasePageInner() {
	const params = useParams<{ id: string }>();
	// The query that led here (results-page click-through) — the reader
	// highlights its terms and jumps to the first match.
	const searchQuery = (useSearchParams().get("q") ?? "").trim();
	// Strict integer id — a malformed segment becomes NaN, caught below.
	const nodeId = /^\d+$/.test(params.id) ? Number(params.id) : Number.NaN;

	const [data, setData] = useState<CaseDetail | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		if (!Number.isFinite(nodeId)) {
			setError("Invalid case id.");
			setLoading(false);
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		// Clear the prior case so nothing stale shows while the next one loads
		// (cited-case links reuse this same route + component instance).
		setData(null);
		browseCase(nodeId)
			.then((d) => !cancelled && setData(d))
			.catch((e) =>
				!cancelled
					? setError(e instanceof Error ? e.message : "Failed to load case.")
					: undefined,
			)
			.finally(() => !cancelled && setLoading(false));
		return () => {
			cancelled = true;
		};
	}, [nodeId]);

	if (!data) {
		return (
			<div className="px-5 py-10 sm:px-8">
				{error ? (
					<Notification
						kind="error"
						title="Couldn't load this case"
						className="max-w-xl"
					>
						{error}
					</Notification>
				) : loading ? (
					<p className="text-[var(--cds-text-2)] text-sm">Loading case…</p>
				) : null}
			</div>
		);
	}

	// Keyed by case so the Ask conversation and rail state start fresh.
	return <CaseReader key={data.id} data={data} searchQuery={searchQuery} />;
}

type Panel = "outline" | "citator" | "ask" | "display";

// The citator rail shows at Tailwind's xl breakpoint; below it the same
// panel opens in a drawer.
const isRailVisible = () =>
	typeof window !== "undefined" &&
	window.matchMedia("(min-width: 1280px)").matches;

// True when a keystroke belongs to a field, so global shortcuts stay out of
// the way — same guard as the shell's "[" and the DocChat "/" shortcut.
function isTypingTarget(target: EventTarget | null): boolean {
	const el = target as HTMLElement | null;
	return !!(
		el &&
		(el.tagName === "INPUT" ||
			el.tagName === "TEXTAREA" ||
			el.tagName === "SELECT" ||
			el.isContentEditable)
	);
}

function CaseReader({
	data,
	searchQuery,
}: {
	data: CaseDetail;
	searchQuery: string;
}) {
	const router = useRouter();
	const scrollRef = useRef<HTMLElement>(null);
	const askRef = useRef<DocAskHandle>(null);

	// Display prefs — read synchronously in the initializer. This tree only
	// mounts client-side (AuthGate renders a placeholder until the session
	// resolves), so there is no SSR markup to disagree with, and reading
	// up front spares the whole opinion a second layout at the default size.
	const [prefs, setPrefs] = useState<ReaderPrefs>(() => loadReaderPrefs());
	const updatePrefs = (p: ReaderPrefs) => {
		setPrefs(p);
		saveReaderPrefs(p);
	};

	// Find in opinion — seeded by the search click-through, editable here.
	const [find, setFind] = useState(searchQuery);
	const [findLive, setFindLive] = useState(searchQuery);
	useEffect(() => {
		const t = window.setTimeout(() => setFindLive(find.trim()), 200);
		return () => window.clearTimeout(t);
	}, [find]);
	const matches = useSearchHighlight(scrollRef, findLive, true);

	const [copied, setCopied] = useState(false);
	const [tab, setTab] = useState<CitatorTab>("citing");
	const [panel, setPanel] = useState<Panel | null>(null);
	const closePanel = useCallback(() => setPanel(null), []);

	const ask = useDocAsk(data.id);

	const sections = useMemo(() => caseSections(data), [data]);
	const ids = useMemo(() => sections.map((s) => s.id), [sections]);
	const active = useActiveSection(ids, scrollRef);

	const court = courtLong(data.court_id, data.court_name);
	const primaryCite = data.citations[0] ?? "";

	// Stable so the memoized Outline doesn't re-render on every reader tick.
	const jump = useCallback((id: string) => {
		scrollRef.current
			?.querySelector(`#${CSS.escape(id)}`)
			?.scrollIntoView({ behavior: "smooth", block: "start" });
		setPanel(null);
	}, []);

	const copyCitation = async () => {
		try {
			await navigator.clipboard.writeText(buildCitation(data));
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	};

	// Open the citator on a tab: in the rail at xl+, in the drawer below.
	const openCitator = useCallback((t: CitatorTab) => {
		setTab(t);
		if (isRailVisible()) setPanel(null);
		else setPanel(t === "ask" ? "ask" : "citator");
		if (t === "ask") {
			// Composer mounts on the next paint when the tab/drawer changes.
			window.setTimeout(() => askRef.current?.focus(), 30);
		}
	}, []);
	const openCiting = useCallback(() => openCitator("citing"), [openCitator]);
	const openAuthorities = useCallback(
		() => openCitator("authorities"),
		[openCitator],
	);

	// "/" opens Ask (never from a field; once in the composer it owns "/").
	useEffect(() => {
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
			if (isTypingTarget(e.target)) return;
			e.preventDefault();
			openCitator("ask");
		};
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	}, [openCitator]);

	const bodyFont =
		prefs.family === "serif"
			? "[font-family:var(--font-plex-serif)]"
			: "[font-family:var(--font-plex-sans)]";
	const measure = prefs.measure === "narrow" ? "max-w-[44rem]" : "max-w-4xl";

	const citatorPanel = (header: boolean) => (
		<CitatorPanel
			data={data}
			tab={tab}
			onTab={setTab}
			ask={ask}
			askRef={askRef}
			header={header}
		/>
	);

	return (
		<CiteHoverProvider cases={data.cited_cases}>
			<div className={cn("flex h-full min-h-0 flex-col", plexSerif.variable)}>
				{/* Toolbar */}
				<div className="flex h-12 shrink-0 items-center gap-1 border-[var(--cds-border)] border-b px-4 print:hidden sm:px-6">
					<p className="min-w-0 truncate text-sm">
						<Link
							href="/"
							className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
						>
							Library
						</Link>
						<span className="mx-2 text-[var(--cds-helper)]">/</span>
						<span className="font-semibold">{data.case_name}</span>
						{primaryCite && (
							<span className="ml-2.5 hidden font-mono text-[12px] text-[var(--cds-helper)] md:inline">
								{primaryCite}
							</span>
						)}
					</p>
					<div className="ml-auto flex shrink-0 items-center gap-1">
						<label className="mr-2 hidden h-8 w-56 items-center gap-2 border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-3 text-[13px] focus-within:border-[#0f62fe] lg:flex">
							<SearchIcon className="size-4 shrink-0 text-[var(--cds-helper)]" />
							<input
								type="search"
								value={find}
								onChange={(e) => setFind(e.target.value)}
								placeholder="Find in opinion"
								aria-label="Find in opinion"
								className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--cds-placeholder)] [&::-webkit-search-cancel-button]:hidden"
							/>
							{findLive && matches !== null ? (
								<span className="shrink-0 font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
									{matches.toLocaleString()}
								</span>
							) : null}
							{find && (
								<button
									type="button"
									aria-label="Clear find"
									onClick={() => {
										setFind("");
										if (searchQuery) router.replace(`/case/${data.id}`);
									}}
									className="shrink-0 text-[var(--cds-helper)] hover:text-[var(--cds-text)]"
								>
									<XIcon className="size-3.5" />
								</button>
							)}
						</label>
						<ToolbarButton onClick={copyCitation} className="hidden sm:flex">
							{copied ? (
								<CheckIcon className="size-4 text-[var(--cds-success-text)]" />
							) : (
								<CopyIcon className="size-4" />
							)}
							{copied ? "Copied" : "Copy citation"}
						</ToolbarButton>
						<ToolbarButton
							onClick={() => window.print()}
							className="hidden sm:flex"
						>
							<PrinterIcon className="size-4" />
							Print
						</ToolbarButton>
						<ToolbarButton
							onClick={() => openCitator("citing")}
							className="hidden lg:flex xl:hidden"
						>
							<ScaleIcon className="size-4" />
							Citator
							<span className="font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
								{data.citing_count.toLocaleString()}
							</span>
						</ToolbarButton>
						<button
							type="button"
							onClick={() => openCitator("ask")}
							className="ml-2 hidden h-9 items-center gap-2 bg-[#0f62fe] px-4 text-[13px] text-white transition-colors hover:bg-[#0353e9] lg:flex"
						>
							<MessageSquareTextIcon className="size-4" />
							Ask about this case
							<span className="font-mono text-[11px] opacity-70">/</span>
						</button>
					</div>
				</div>

				<div className="flex min-h-0 flex-1">
					{/* Left rail — outline · details · display */}
					<aside className="hidden w-56 shrink-0 flex-col gap-8 overflow-y-auto border-[var(--cds-border)] border-r py-6 print:hidden lg:flex">
						<Outline sections={sections} active={active} onJump={jump} />
						<Details data={data} />
						<DisplayControls prefs={prefs} onChange={updatePrefs} />
					</aside>

					{/* Center — the document */}
					<article
						ref={scrollRef}
						aria-label={data.case_name}
						className="min-w-0 flex-1 overflow-y-auto pb-14 print:overflow-visible lg:pb-0"
					>
						<div className={cn("mx-auto px-5 py-8 sm:px-8 sm:py-10", measure)}>
							<header>
								<p className="flex flex-wrap items-center gap-x-2.5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
									<span>{court}</span>
									{data.date_filed && (
										<>
											<span className="text-[var(--cds-border-strong)]">·</span>
											<span>Decided {fmtEffective(data.date_filed)}</span>
										</>
									)}
								</p>
								<h1 className="mt-3 font-light text-3xl leading-[1.15] sm:text-4xl">
									{data.case_name}
								</h1>
								{data.case_name_full &&
									data.case_name_full !== data.case_name && (
										<p className="mt-2 text-[var(--cds-text-2)] text-sm">
											{data.case_name_full}
										</p>
									)}
								{data.citations.length > 0 && (
									<p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[13px]">
										{data.citations.map((c, i) => (
											<span
												key={c}
												className={cn(i > 0 && "text-[var(--cds-text-2)]")}
											>
												{i > 0 && (
													<span className="mr-3 text-[var(--cds-border-strong)]">
														·
													</span>
												)}
												{c}
											</span>
										))}
										<button
											type="button"
											onClick={copyCitation}
											className="inline-flex h-6 items-center gap-1.5 border border-[var(--cds-border)] px-2 font-sans text-[12px] text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)] print:hidden"
										>
											{copied ? (
												<CheckIcon className="size-3" />
											) : (
												<CopyIcon className="size-3" />
											)}
											{copied ? "Copied" : "Copy"}
										</button>
									</p>
								)}
								<p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--cds-text-2)]">
									{data.docket_number && <span>No. {data.docket_number}</span>}
									{data.precedential_status && (
										<Tag kind="gray">{data.precedential_status}</Tag>
									)}
									{data.judges?.trim() && (
										<span className="min-w-0 truncate">
											{data.judges.trim()}
										</span>
									)}
								</p>

								<AuthorityStrip
									data={data}
									onCitedBy={openCiting}
									onCites={openAuthorities}
								/>
							</header>

							<div
								className={cn("mt-2", bodyFont)}
								style={{ fontSize: prefs.fontSize }}
							>
								{data.head_matter && (
									<section id="syllabus" className="scroll-mt-4">
										<SectionHeading label="Syllabus" />
										<OpinionBody text={data.head_matter} idPrefix="syllabus" />
									</section>
								)}
								{data.opinions.map((op) => (
									<section
										key={op.id}
										id={`op-${op.id}`}
										className="scroll-mt-4"
									>
										<SectionHeading
											label={opinionLabel(op)}
											right={opinionAuthor(op)}
										/>
										{op.body_segments ? (
											<SegmentBody
												segments={op.body_segments}
												idPrefix={`op-${op.id}`}
											/>
										) : op.has_content ? (
											<OpinionBody
												text={op.body_text}
												idPrefix={`op-${op.id}`}
											/>
										) : (
											<p className="mt-4 text-[var(--cds-text-2)] text-sm italic [font-family:var(--font-plex-sans)]">
												No opinion text available.
											</p>
										)}
									</section>
								))}
							</div>
						</div>
					</article>

					{/* Right rail — the citator */}
					<aside
						aria-label="Citator"
						className="hidden w-[352px] shrink-0 flex-col border-[var(--cds-border)] border-l print:hidden xl:flex"
					>
						{citatorPanel(true)}
					</aside>
				</div>

				{/* Below lg: bottom bar */}
				<nav
					aria-label="Reader panels"
					className="fixed inset-x-0 bottom-0 z-30 flex h-14 border-[var(--cds-border)] border-t bg-[var(--cds-bg)] print:hidden lg:hidden"
				>
					<BarTab
						icon={<ListIcon className="size-5" />}
						label="Outline"
						onClick={() => setPanel("outline")}
					/>
					<BarTab
						icon={<ScaleIcon className="size-5" />}
						label={`Citator · ${data.citing_count.toLocaleString()}`}
						onClick={() => openCitator("citing")}
					/>
					<BarTab
						icon={<MessageSquareTextIcon className="size-5" />}
						label="Ask"
						onClick={() => openCitator("ask")}
					/>
					<BarTab
						icon={<TypeIcon className="size-5" />}
						label="Display"
						onClick={() => setPanel("display")}
					/>
				</nav>

				{/* Drawers */}
				<Drawer open={panel === "outline"} title="Outline" onClose={closePanel}>
					<div className="flex flex-col gap-8 overflow-y-auto py-6">
						<Outline sections={sections} active={active} onJump={jump} />
						<Details data={data} />
					</div>
				</Drawer>
				<Drawer open={panel === "citator"} title="Citator" onClose={closePanel}>
					{citatorPanel(true)}
				</Drawer>
				<Drawer
					open={panel === "ask"}
					title="Ask about this case"
					onClose={closePanel}
				>
					{citatorPanel(false)}
				</Drawer>
				<Drawer
					open={panel === "display"}
					title="Display"
					onClose={closePanel}
					className="sm:max-w-xs"
				>
					<div className="py-6">
						<DisplayControls prefs={prefs} onChange={updatePrefs} />
						<div className="mt-8 flex flex-col">
							<button
								type="button"
								onClick={copyCitation}
								className="flex h-11 items-center gap-3 px-4 text-left text-sm transition-colors hover:bg-[var(--cds-layer-hover)]"
							>
								{copied ? (
									<CheckIcon className="size-4 text-[var(--cds-success-text)]" />
								) : (
									<CopyIcon className="size-4" />
								)}
								{copied ? "Copied" : "Copy citation"}
							</button>
							<button
								type="button"
								onClick={() => window.print()}
								className="flex h-11 items-center gap-3 px-4 text-left text-sm transition-colors hover:bg-[var(--cds-layer-hover)]"
							>
								<PrinterIcon className="size-4" />
								Print
							</button>
						</div>
					</div>
				</Drawer>
			</div>
		</CiteHoverProvider>
	);
}

// "020lead" → Opinion, "030concurrence" → Concurrence, "040dissent" →
// Dissent, "035concurrenceinpart" → Concurring in part; else the heading.
function opinionLabel(op: CaseOpinion): string {
	const t = (op.type || "").toLowerCase();
	if (t.includes("dissent") && t.includes("part")) return "Dissenting in part";
	if (t.includes("concur") && t.includes("part")) return "Concurring in part";
	if (t.includes("dissent")) return "Dissent";
	if (t.includes("concur")) return "Concurrence";
	if (t.includes("lead") || t.includes("combined") || t.includes("unanimous"))
		return "Opinion";
	if (t.includes("addendum")) return "Addendum";
	return op.heading || "Opinion";
}

// "Larson, J." from author_str ("Larson") or the heading's parenthetical.
function opinionAuthor(op: CaseOpinion): string {
	if (op.per_curiam) return "Per curiam";
	const raw = op.author_str?.trim();
	if (raw) return raw;
	const m = /\(([^)]+)\)\s*$/.exec(op.heading || "");
	return m ? m[1] : "";
}

function ToolbarButton({
	children,
	className,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
	return (
		<button
			type="button"
			{...props}
			className={cn(
				"flex h-9 items-center gap-2 px-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]",
				className,
			)}
		>
			{children}
		</button>
	);
}

function BarTab({
	icon,
	label,
	onClick,
}: {
	icon: ReactNode;
	label: string;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="flex flex-1 flex-col items-center justify-center gap-1 text-[11px] text-[var(--cds-text-2)] transition-colors hover:text-[var(--cds-text)]"
		>
			{icon}
			{label}
		</button>
	);
}

function SectionHeading({ label, right }: { label: string; right?: string }) {
	return (
		<div className="mt-8 flex items-baseline justify-between gap-4 border-[var(--cds-border)] border-t pt-5 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em] [font-family:var(--font-plex-mono)]">
			<h2>{label}</h2>
			{right && <span className="truncate tracking-[0.14em]">{right}</span>}
		</div>
	);
}
