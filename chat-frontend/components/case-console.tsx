"use client";

// Westlaw-style three-pane reader for a single Iowa caselaw decision:
//   left   — document outline (scroll-spy) and/or case details
//   center — reporter-style caption + head-matter + formatted opinions
//   right  — cited authorities (simple linked case list)
// Accent color is blue (legal-research convention) over the app's neutral
// shadcn surfaces. The treatment/citator signal is a deliberate "pending"
// placeholder until the case→case citation graph is loaded.

import {
	CheckIcon,
	CircleDashedIcon,
	CopyIcon,
	ExternalLinkIcon,
	PrinterIcon,
} from "lucide-react";
import Link from "next/link";
import { Fragment, type ReactNode, useMemo, useRef, useState } from "react";
import {
	Breadcrumb,
	BreadcrumbItem,
	BreadcrumbLink,
	BreadcrumbList,
	BreadcrumbPage,
	BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
	type Block,
	buildCitation,
	COURT_CITE,
	caseSections,
	isHeadingLine,
	parseOpinion,
	RUNIN,
	type Section,
	STAR,
	useActiveSection,
} from "@/lib/case-format";
import {
	type CaseDetail,
	type CaseSegment,
	fmtEffective,
} from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

// Opinion parsing/outline logic lives in lib/case-format.ts, shared with the
// Carbon v2 reader (app/v2/case/[id]) so document structure can't drift
// between skins. This file is only the legacy skin.

// Render West star-pagination page breaks (e.g. *830) as bold "[*830]";
// everything else is plain text.
function renderInline(text: string): ReactNode[] {
	return text.split(STAR).map((p, i) => {
		if (/^\*\d{1,4}$/.test(p)) {
			return (
				// biome-ignore lint/suspicious/noArrayIndexKey: static inline split
				<strong key={i} className="mx-0.5 font-bold">
					[{p}]
				</strong>
			);
		}
		return p;
	});
}

function renderBlock(b: Block, headingId?: string): ReactNode {
	// A folded-in page marker renders inline at the start of the block ("[*830] ").
	const prefix = b.marker ? `${b.marker} ` : "";
	switch (b.kind) {
		case "byline":
			return (
				<p className="mb-5 font-semibold text-[0.85em] uppercase tracking-wide">
					{renderInline(prefix + b.text)}
				</p>
			);
		case "heading":
			return (
				<h3
					id={headingId}
					className="mt-7 mb-3 scroll-mt-4 font-bold text-[1.05em]"
				>
					{renderInline(prefix + b.text)}
				</h3>
			);
		case "label":
			return (
				<p className="mt-6 mb-2 font-semibold text-[0.8em] text-muted-foreground uppercase tracking-wide">
					{renderInline(prefix + b.text)}
				</p>
			);
		case "runin":
			return (
				<p className="mb-3.5 leading-relaxed">
					{b.marker ? renderInline(prefix) : null}
					<strong className="font-semibold">{b.lead} </strong>
					{renderInline(b.rest)}
				</p>
			);
		default:
			return (
				<p className="mb-3.5 leading-relaxed">
					{renderInline(prefix + b.text)}
				</p>
			);
	}
}

// Render the rich, citation-linked structure built from the source HTML.
function renderRuns(runs: CaseSegment["runs"]): ReactNode[] {
	return runs.map((r, i) => {
		if (r.star) {
			return (
				// biome-ignore lint/suspicious/noArrayIndexKey: static run list
				<strong key={i} className="mx-0.5 font-bold">
					[{r.star}]
				</strong>
			);
		}
		if (r.sup) {
			return (
				// biome-ignore lint/suspicious/noArrayIndexKey: static run list
				<sup key={i} className="text-[0.7em] text-muted-foreground">
					{r.sup}
				</sup>
			);
		}
		const text = r.t ?? "";
		if (r.case != null) {
			return (
				<Link
					// biome-ignore lint/suspicious/noArrayIndexKey: static run list
					key={i}
					href={`/cases/${r.case}`}
					className="text-blue-600 hover:underline dark:text-blue-400"
				>
					{text}
				</Link>
			);
		}
		if (r.em) {
			// biome-ignore lint/suspicious/noArrayIndexKey: static run list
			return <em key={i}>{text}</em>;
		}
		return text;
	});
}

function SegmentBody({
	segments,
	idPrefix,
}: {
	segments: CaseSegment[];
	idPrefix: string;
}) {
	let headingCount = 0;
	return (
		<div className="text-[0.95em]">
			{segments.map((b, i) => {
				const text = b.runs
					.map((r) => r.t ?? "")
					.join("")
					.trim();
				if (b.k === "byline") {
					return (
						<p
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							className="mb-5 font-semibold text-[0.85em] uppercase tracking-wide"
						>
							{renderRuns(b.runs)}
						</p>
					);
				}
				if (b.k === "quote") {
					return (
						<blockquote
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							className="my-4 border-l-2 pl-4 text-muted-foreground italic"
						>
							{renderRuns(b.runs)}
						</blockquote>
					);
				}
				if (b.k === "fn") {
					return (
						<p
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							className="mt-2 text-[0.85em] text-muted-foreground leading-relaxed"
						>
							{b.mark ? (
								<sup className="mr-1 font-semibold">{b.mark}</sup>
							) : null}
							{renderRuns(b.runs)}
						</p>
					);
				}
				if (isHeadingLine(text)) {
					const hid = `${idPrefix}-s${headingCount++}`;
					return (
						<h3
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							id={hid}
							className="mt-7 mb-3 scroll-mt-4 font-bold text-[1.05em]"
						>
							{renderRuns(b.runs)}
						</h3>
					);
				}
				// Run-in subsection heading ("A. Prejudicial Hearsay. <text>"): bold the
				// lead clause, which is plain text at the start of the first run.
				const runin = RUNIN.exec(text);
				const first = b.runs[0];
				if (
					runin &&
					first?.t &&
					!first.em &&
					first.case == null &&
					first.t.startsWith(runin[1])
				) {
					const rest = [
						{ ...first, t: first.t.slice(runin[1].length) },
						...b.runs.slice(1),
					];
					return (
						<p
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							className="mb-3.5 leading-relaxed"
						>
							<strong className="font-semibold">{runin[1]}</strong>
							{renderRuns(rest)}
						</p>
					);
				}
				return (
					<p
						// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
						key={i}
						className="mb-3.5 leading-relaxed"
					>
						{renderRuns(b.runs)}
					</p>
				);
			})}
		</div>
	);
}

function OpinionBody({ text, idPrefix }: { text: string; idPrefix: string }) {
	const blocks = useMemo(() => parseOpinion(text), [text]);
	let headingCount = 0;
	return (
		<div className="text-[0.95em]">
			{blocks.map((b, i) => {
				const hid =
					b.kind === "heading" ? `${idPrefix}-s${headingCount++}` : undefined;
				return (
					// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered opinion blocks
					<Fragment key={i}>{renderBlock(b, hid)}</Fragment>
				);
			})}
		</div>
	);
}

function RailLabel({ children }: { children: ReactNode }) {
	return (
		<p className="mb-2 font-semibold text-muted-foreground text-xs uppercase tracking-wide">
			{children}
		</p>
	);
}

function OutlineList({
	sections,
	active,
	onJump,
}: {
	sections: Section[];
	active: string | null;
	onJump: (id: string) => void;
}) {
	return (
		<ul className="space-y-0.5">
			{sections.map((s) => (
				<li key={s.id}>
					<button
						type="button"
						onClick={() => onJump(s.id)}
						aria-current={active === s.id ? "true" : undefined}
						style={{ paddingLeft: `${0.5 + s.depth * 0.75}rem` }}
						className={cn(
							"w-full truncate rounded py-1 pr-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
							active === s.id
								? "bg-blue-600/10 font-medium text-blue-700 dark:text-blue-300"
								: "text-muted-foreground hover:bg-accent hover:text-foreground",
						)}
					>
						{s.label}
					</button>
				</li>
			))}
		</ul>
	);
}

function DetailsList({
	details,
}: {
	details: { label: string; value: string }[];
}) {
	return (
		<dl className="space-y-2.5">
			{details.map((d) => (
				<div key={d.label}>
					<dt className="text-muted-foreground text-xs uppercase tracking-wide">
						{d.label}
					</dt>
					<dd className="mt-0.5 text-sm">{d.value}</dd>
				</div>
			))}
		</dl>
	);
}

function Authorities({ data }: { data: CaseDetail }) {
	return (
		<>
			{data.cited_cases.length > 0 ? (
				<ul className="space-y-2">
					{data.cited_cases.map((c) => (
						<li key={c.case_id}>
							<Link
								href={`/cases/${c.case_id}`}
								className="block text-sm leading-snug hover:text-blue-600 hover:underline dark:hover:text-blue-400"
							>
								{c.case_name}
							</Link>
						</li>
					))}
				</ul>
			) : (
				<p className="text-muted-foreground text-sm">
					No in-corpus authorities cited.
				</p>
			)}
			{data.external_citation_count > 0 ? (
				<>
					<Separator className="my-4" />
					<p className="text-muted-foreground text-xs leading-relaxed">
						{data.external_citation_count} additional citation
						{data.external_citation_count === 1 ? "" : "s"} to authorities
						outside this corpus.
					</p>
				</>
			) : null}
		</>
	);
}

function StatusPill({ status }: { status: string }) {
	return (
		<span className="inline-flex items-center rounded-full bg-blue-600/10 px-2 py-0.5 font-medium text-blue-700 text-xs dark:text-blue-300">
			{status}
		</span>
	);
}

function TreatmentPill() {
	return (
		<span className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-muted-foreground text-xs">
			<CircleDashedIcon className="size-3.5" />
			Citator treatment — not yet available
		</span>
	);
}

function CourtListenerLink({ url }: { url: string }) {
	return (
		<a
			href={url}
			target="_blank"
			rel="noopener noreferrer"
			className="inline-flex items-center gap-1 text-blue-600 text-sm hover:underline dark:text-blue-400"
		>
			View on CourtListener
			<ExternalLinkIcon className="size-3.5" />
		</a>
	);
}

export function CaseConsole({ data }: { data: CaseDetail }) {
	const scrollRef = useRef<HTMLElement>(null);
	const [readingPx, setReadingPx] = useState(18);
	const [copied, setCopied] = useState(false);

	// For multi-opinion cases, the opinion is a top-level outline entry and
	// its section headings nest under it; for a single opinion, the section
	// headings ARE the outline (so you can still jump within the document).
	const sections = useMemo<Section[]>(() => caseSections(data), [data]);
	const ids = useMemo(() => sections.map((s) => s.id), [sections]);
	const active = useActiveSection(ids, scrollRef);

	const details = useMemo(() => {
		const d: { label: string; value: string }[] = [];
		const add = (label: string, value: string) => {
			if (value?.trim()) d.push({ label, value: value.trim() });
		};
		add("Disposition", data.disposition);
		add("Posture", data.posture);
		add("Nature of suit", data.nature_of_suit);
		add("Panel", data.judges);
		return d;
	}, [data]);

	const court = data.court_name || COURT_CITE[data.court_id] || data.court_id;
	const hasOutline = sections.length > 1;
	const hasLeftRail = hasOutline || details.length > 0;
	const hasAuthorities =
		data.cited_cases.length > 0 || data.external_citation_count > 0;

	function jump(id: string) {
		scrollRef.current
			?.querySelector(`#${CSS.escape(id)}`)
			?.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	async function copyCitation() {
		try {
			await navigator.clipboard.writeText(buildCitation(data));
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	}

	return (
		<div className="flex min-h-0 flex-1 flex-col print:h-auto">
			<header className="flex h-16 shrink-0 items-center gap-2 border-b bg-background px-4 print:hidden">
				<SidebarTrigger />
				<Separator orientation="vertical" className="mx-1 h-5" />
				<Breadcrumb className="min-w-0">
					<BreadcrumbList className="flex-nowrap">
						<BreadcrumbItem>
							<BreadcrumbLink asChild>
								<Link href="/browse">Browse the corpus</Link>
							</BreadcrumbLink>
						</BreadcrumbItem>
						<BreadcrumbSeparator />
						<BreadcrumbItem className="min-w-0">
							<BreadcrumbPage className="truncate">
								{data.case_name}
							</BreadcrumbPage>
						</BreadcrumbItem>
					</BreadcrumbList>
				</Breadcrumb>
				<div className="ml-auto flex shrink-0 items-center gap-1">
					<div className="mr-1 flex items-center rounded-md border">
						<button
							type="button"
							onClick={() => setReadingPx((p) => Math.max(14, p - 1))}
							disabled={readingPx <= 14}
							aria-label="Decrease text size"
							className="rounded-l-md px-2 py-1 text-muted-foreground text-xs outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-40"
						>
							A
						</button>
						<Separator orientation="vertical" className="h-4" />
						<button
							type="button"
							onClick={() => setReadingPx((p) => Math.min(22, p + 1))}
							disabled={readingPx >= 22}
							aria-label="Increase text size"
							className="rounded-r-md px-2 py-1 text-base text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-40"
						>
							A
						</button>
					</div>
					<Button variant="outline" size="sm" onClick={copyCitation}>
						{copied ? (
							<CheckIcon className="size-4 text-blue-600 dark:text-blue-400" />
						) : (
							<CopyIcon className="size-4" />
						)}
						{copied ? "Copied" : "Copy citation"}
					</Button>
					<Button
						variant="ghost"
						size="sm"
						onClick={() => window.print()}
						aria-label="Print"
					>
						<PrinterIcon className="size-4" />
					</Button>
				</div>
			</header>

			<div className="flex min-h-0 flex-1">
				{/* Left rail: outline and/or case details */}
				{hasLeftRail ? (
					<div className="hidden w-60 shrink-0 overflow-y-auto border-r p-4 lg:block print:hidden">
						{hasOutline ? (
							<nav aria-label="Document outline">
								<RailLabel>Outline</RailLabel>
								<OutlineList
									sections={sections}
									active={active}
									onJump={jump}
								/>
							</nav>
						) : null}
						{details.length > 0 ? (
							<div className={hasOutline ? "mt-6" : ""}>
								<RailLabel>Details</RailLabel>
								<DetailsList details={details} />
							</div>
						) : null}
					</div>
				) : null}

				{/* Center: the document — fills the pane */}
				<main
					ref={scrollRef}
					aria-label={data.case_name}
					className="min-w-0 flex-1 overflow-y-auto print:overflow-visible"
				>
					<article className="mx-auto max-w-5xl px-6 py-8 sm:px-10">
						<header className="border-b pb-5">
							<p className="font-medium text-muted-foreground text-xs uppercase tracking-widest">
								{court}
							</p>
							<h1 className="mt-1.5 text-balance font-semibold text-2xl leading-tight tracking-tight sm:text-3xl">
								{data.case_name}
							</h1>
							{data.case_name_full && data.case_name_full !== data.case_name ? (
								<p className="mt-1.5 text-muted-foreground text-sm">
									{data.case_name_full}
								</p>
							) : null}
							{data.citations.length > 0 ? (
								<p className="mt-3 font-medium text-sm tracking-tight">
									{data.citations.join("  ·  ")}
								</p>
							) : null}
							<div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground text-sm">
								{data.date_filed ? (
									<span>Decided {fmtEffective(data.date_filed)}</span>
								) : null}
								{data.docket_number ? (
									<>
										<span aria-hidden>·</span>
										<span>No. {data.docket_number}</span>
									</>
								) : null}
								{data.precedential_status ? (
									<StatusPill status={data.precedential_status} />
								) : null}
							</div>
							<div className="mt-3 flex flex-wrap items-center gap-3">
								<TreatmentPill />
								{data.official_url ? (
									<CourtListenerLink url={data.official_url} />
								) : null}
							</div>
						</header>

						{/* Compact navigation for viewports where the rails are hidden */}
						{hasLeftRail ? (
							<details className="mt-4 rounded-md border lg:hidden">
								<summary className="cursor-pointer select-none px-3 py-2 font-medium text-sm">
									Outline &amp; details
								</summary>
								<div className="space-y-4 border-t px-3 py-3">
									{hasOutline ? (
										<nav aria-label="Document outline">
											<OutlineList
												sections={sections}
												active={active}
												onJump={jump}
											/>
										</nav>
									) : null}
									{details.length > 0 ? (
										<DetailsList details={details} />
									) : null}
								</div>
							</details>
						) : null}

						<div
							className="mt-6 text-foreground"
							style={{ fontSize: `${readingPx}px` }}
						>
							{data.head_matter ? (
								<section id="syllabus" className="scroll-mt-4">
									<SectionHeadingLabel>Syllabus</SectionHeadingLabel>
									<OpinionBody text={data.head_matter} idPrefix="syllabus" />
								</section>
							) : null}
							{data.opinions.map((op) => (
								<section
									key={op.id}
									id={`op-${op.id}`}
									className="mt-10 scroll-mt-4"
								>
									<SectionHeadingLabel>
										{op.heading}
										{op.per_curiam ? (
											<span className="ml-2 font-normal text-[0.85em] text-muted-foreground">
												(Per Curiam)
											</span>
										) : null}
									</SectionHeadingLabel>
									{op.body_segments ? (
										<SegmentBody
											segments={op.body_segments}
											idPrefix={`op-${op.id}`}
										/>
									) : op.has_content ? (
										<OpinionBody text={op.body_text} idPrefix={`op-${op.id}`} />
									) : (
										<p className="text-muted-foreground text-sm italic">
											No opinion text available.
										</p>
									)}
								</section>
							))}
						</div>

						{/* Cited authorities for viewports below the right-rail breakpoint */}
						{hasAuthorities ? (
							<details className="mt-10 rounded-md border xl:hidden">
								<summary className="cursor-pointer select-none px-3 py-2 font-medium text-sm">
									Cited authorities
								</summary>
								<div className="border-t px-3 py-3">
									<Authorities data={data} />
								</div>
							</details>
						) : null}
					</article>
				</main>

				{/* Right rail: cited authorities */}
				{hasAuthorities ? (
					<aside
						aria-label="Cited authorities"
						className="hidden w-72 shrink-0 overflow-y-auto border-l p-4 xl:block print:hidden"
					>
						<RailLabel>Cited authorities</RailLabel>
						<Authorities data={data} />
					</aside>
				) : null}
			</div>
		</div>
	);
}

function SectionHeadingLabel({ children }: { children: ReactNode }) {
	return (
		<h2 className="mb-3 border-b pb-1.5 font-semibold text-[1.1em] text-foreground">
			{children}
		</h2>
	);
}
