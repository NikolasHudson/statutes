"use client";

// v2 Carbon case reader — the three-pane decision console wired to
// /api/browse/cases/<id>. Document structure (opinion parsing, outline,
// citation building, scroll-spy) comes from lib/case-format.ts, shared with
// the legacy reader; this file is the Carbon skin: outline/details rail,
// Plex-Serif opinion column with star pagination and linked citations, and a
// cited-authorities rail. Citator treatment is honestly "pending" — the
// case→case treatment graph isn't served yet.

import {
	CheckIcon,
	CircleDashedIcon,
	CopyIcon,
	ExternalLinkIcon,
	MinusIcon,
	PlusIcon,
	PrinterIcon,
} from "lucide-react";
import { IBM_Plex_Serif } from "next/font/google";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
	Fragment,
	type ReactNode,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	KVList,
	Notification,
	Panel,
	Tag,
} from "@/components/carbon/primitives";
import {
	type Block,
	buildCitation,
	COURT_CITE,
	caseSections,
	isHeadingLine,
	parseOpinion,
	RUNIN,
	STAR,
	useActiveSection,
} from "@/lib/case-format";
import {
	browseCase,
	type CaseDetail,
	type CaseSegment,
	fmtEffective,
} from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

const plexSerif = IBM_Plex_Serif({
	weight: ["400", "600"],
	style: ["normal", "italic"],
	subsets: ["latin"],
	variable: "--font-plex-serif",
});

export default function V2CasePage() {
	const params = useParams<{ id: string }>();
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

	return <CaseReader data={data} />;
}

function CaseReader({ data }: { data: CaseDetail }) {
	const scrollRef = useRef<HTMLElement>(null);
	const [fontSize, setFontSize] = useState(16);
	const [copied, setCopied] = useState(false);

	const sections = useMemo(() => caseSections(data), [data]);
	const ids = useMemo(() => sections.map((s) => s.id), [sections]);
	const active = useActiveSection(ids, scrollRef);

	const details = useMemo(() => {
		const d: [string, string][] = [];
		const add = (label: string, value: string) => {
			if (value?.trim()) d.push([label, value.trim()]);
		};
		add("Disposition", data.disposition);
		add("Posture", data.posture);
		add("Nature of suit", data.nature_of_suit);
		add("Panel", data.judges);
		return d;
	}, [data]);

	const court = data.court_name || COURT_CITE[data.court_id] || data.court_id;
	const hasAuthorities =
		data.cited_cases.length > 0 || data.external_citation_count > 0;

	const jump = (id: string) =>
		scrollRef.current
			?.querySelector(`#${CSS.escape(id)}`)
			?.scrollIntoView({ behavior: "smooth", block: "start" });

	const copyCitation = async () => {
		try {
			await navigator.clipboard.writeText(buildCitation(data));
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	};

	return (
		<div className={cn("flex h-full min-h-0 flex-col", plexSerif.variable)}>
			{/* Toolbar */}
			<div className="flex h-12 shrink-0 items-center gap-1 border-[var(--cds-border)] border-b px-5 print:hidden sm:px-8">
				<p className="min-w-0 truncate text-sm">
					<Link
						href="/v2"
						className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
					>
						Library
					</Link>
					<span className="mx-2 text-[var(--cds-helper)]">/</span>
					<span className="font-semibold">{data.case_name}</span>
				</p>
				<div className="ml-auto flex shrink-0 items-center gap-1">
					<div className="mr-2 hidden items-center border border-[var(--cds-border)] sm:flex">
						<button
							type="button"
							aria-label="Smaller text"
							onClick={() => setFontSize((p) => Math.max(14, p - 1))}
							className="flex size-9 items-center justify-center transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<MinusIcon className="size-3.5" />
						</button>
						<span className="w-10 text-center font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
							{fontSize}px
						</span>
						<button
							type="button"
							aria-label="Larger text"
							onClick={() => setFontSize((p) => Math.min(22, p + 1))}
							className="flex size-9 items-center justify-center transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<PlusIcon className="size-3.5" />
						</button>
					</div>
					<ToolbarButton onClick={copyCitation}>
						{copied ? (
							<CheckIcon className="size-4 text-[var(--cds-success-text)]" />
						) : (
							<CopyIcon className="size-4" />
						)}
						{copied ? "Copied" : "Copy citation"}
					</ToolbarButton>
					<ToolbarButton onClick={() => window.print()}>
						<PrinterIcon className="size-4" />
						Print
					</ToolbarButton>
				</div>
			</div>

			<div className="flex min-h-0 flex-1">
				{/* Left rail — outline scroll-spy + details */}
				{(sections.length > 1 || details.length > 0) && (
					<aside className="hidden w-60 shrink-0 flex-col overflow-y-auto border-[var(--cds-border)] border-r py-6 print:hidden lg:flex">
						{sections.length > 1 && (
							<nav aria-label="Document outline">
								<p className="px-4 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
									Outline
								</p>
								{sections.map((s) => (
									<button
										key={s.id}
										type="button"
										onClick={() => jump(s.id)}
										aria-current={active === s.id ? "true" : undefined}
										style={{ paddingLeft: `${0.875 + s.depth * 1.125}rem` }}
										className={cn(
											"flex w-full border-l-[3px] py-1.5 pr-3 text-left text-[13px] transition-colors",
											active === s.id
												? "border-[#0f62fe] font-semibold"
												: "border-transparent text-[var(--cds-text-2)] hover:text-[var(--cds-text)]",
										)}
									>
										<span className="truncate">{s.label}</span>
									</button>
								))}
							</nav>
						)}
						{details.length > 0 && (
							<>
								<p className="px-4 pt-8 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
									Details
								</p>
								<dl className="text-xs">
									{details.map(([k, v]) => (
										<div key={k} className="px-4 py-1.5">
											<dt className="text-[var(--cds-helper)]">{k}</dt>
											<dd className="mt-0.5">{v}</dd>
										</div>
									))}
								</dl>
							</>
						)}
					</aside>
				)}

				{/* Center — the document */}
				<article
					ref={scrollRef}
					aria-label={data.case_name}
					className="min-w-0 flex-1 overflow-y-auto print:overflow-visible"
				>
					<div className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
						<header>
							<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
								{court}
							</p>
							<h1 className="mt-3 font-light text-3xl sm:text-4xl">
								{data.case_name}
							</h1>
							{data.case_name_full &&
								data.case_name_full !== data.case_name && (
									<p className="mt-2 text-[var(--cds-text-2)] text-sm">
										{data.case_name_full}
									</p>
								)}
							{data.citations.length > 0 && (
								<p className="mt-3 font-mono text-[13px]">
									{data.citations.join(" · ")}
								</p>
							)}
							<p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--cds-text-2)]">
								{data.date_filed && (
									<span>Decided {fmtEffective(data.date_filed)}</span>
								)}
								{data.docket_number && <span>No. {data.docket_number}</span>}
								{data.precedential_status && (
									<Tag kind="gray">{data.precedential_status}</Tag>
								)}
							</p>

							<div className="mt-4 flex flex-wrap items-center gap-3">
								<Tag kind="outline">
									<CircleDashedIcon className="size-3" />
									Citator treatment — not yet available
								</Tag>
								{data.official_url && (
									<a
										href={data.official_url}
										target="_blank"
										rel="noopener noreferrer"
										className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-link)] hover:underline"
									>
										View on CourtListener
										<ExternalLinkIcon className="size-3.5" />
									</a>
								)}
							</div>
						</header>

						<div
							className="mt-4 [font-family:var(--font-plex-serif)] leading-[1.75]"
							style={{ fontSize }}
						>
							{data.head_matter && (
								<section id="syllabus" className="scroll-mt-4">
									<SectionHeading>Syllabus</SectionHeading>
									<OpinionBody text={data.head_matter} idPrefix="syllabus" />
								</section>
							)}
							{data.opinions.map((op) => (
								<section key={op.id} id={`op-${op.id}`} className="scroll-mt-4">
									<SectionHeading>
										{op.heading}
										{op.per_curiam && (
											<span className="ml-2 normal-case tracking-normal">
												(Per Curiam)
											</span>
										)}
									</SectionHeading>
									{op.body_segments ? (
										<SegmentBody
											segments={op.body_segments}
											idPrefix={`op-${op.id}`}
										/>
									) : op.has_content ? (
										<OpinionBody text={op.body_text} idPrefix={`op-${op.id}`} />
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

				{/* Right rail — cited authorities */}
				{hasAuthorities && (
					<aside
						aria-label="Cited authorities"
						className="hidden w-80 shrink-0 space-y-6 overflow-y-auto border-[var(--cds-border)] border-l p-5 print:hidden xl:block"
					>
						<Panel title="Cited authorities">
							{data.cited_cases.length > 0 ? (
								<div className="divide-y divide-[var(--cds-border)]">
									{data.cited_cases.map((c) => (
										<Link
											key={c.case_id}
											href={`/v2/case/${c.case_id}`}
											className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
										>
											<span className="min-w-0 flex-1 truncate text-[13px] group-hover:underline">
												{c.case_name}
											</span>
											<span className="shrink-0 font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
												×{c.count}
											</span>
										</Link>
									))}
								</div>
							) : (
								<p className="px-4 py-3 text-[13px] text-[var(--cds-text-2)]">
									No in-corpus authorities cited.
								</p>
							)}
							{data.external_citation_count > 0 && (
								<p className="border-[var(--cds-border)] border-t px-4 py-2.5 text-[11px] text-[var(--cds-helper)]">
									{data.external_citation_count} additional citation
									{data.external_citation_count === 1 ? "" : "s"} to authorities
									outside this corpus.
								</p>
							)}
						</Panel>

						<Panel title="Case facts">
							<KVList
								rows={[
									["Cites in corpus", String(data.cited_cases.length)],
									["External cites", String(data.external_citation_count)],
									["Opinions", String(data.opinions.length)],
								]}
							/>
						</Panel>
					</aside>
				)}
			</div>
		</div>
	);
}

function ToolbarButton({
	children,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
	return (
		<button
			type="button"
			{...props}
			className="flex h-9 items-center gap-2 px-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
		>
			{children}
		</button>
	);
}

function SectionHeading({ children }: { children: ReactNode }) {
	return (
		<h2 className="mt-10 border-[var(--cds-border)] border-t pt-6 pb-3 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em] [font-family:var(--font-plex-mono)]">
			{children}
		</h2>
	);
}

// ---------------------------------------------------------------------------
// Opinion rendering — Carbon skin over the shared lib/case-format structure.
// ---------------------------------------------------------------------------

// West star-pagination page breaks (e.g. *830) as "[*830]" in link blue.
function renderInline(text: string): ReactNode[] {
	return text.split(STAR).map((p, i) => {
		if (/^\*\d{1,4}$/.test(p)) {
			return (
				<span
					// biome-ignore lint/suspicious/noArrayIndexKey: static inline split
					key={i}
					className="mx-1 font-mono text-[0.8em] text-[var(--cds-link)]"
				>
					[{p}]
				</span>
			);
		}
		return p;
	});
}

function renderBlock(b: Block, headingId?: string): ReactNode {
	// A folded-in page marker renders inline at the start of the block.
	const prefix = b.marker ? `${b.marker} ` : "";
	switch (b.kind) {
		case "byline":
			return (
				<p className="mt-4 mb-5 font-semibold text-[0.85em] uppercase tracking-wide">
					{renderInline(prefix + b.text)}
				</p>
			);
		case "heading":
			return (
				<h3
					id={headingId}
					className="mt-7 mb-3 scroll-mt-4 font-semibold text-[1.05em]"
				>
					{renderInline(prefix + b.text)}
				</h3>
			);
		case "label":
			return (
				<p className="mt-6 mb-2 font-semibold text-[0.8em] text-[var(--cds-helper)] uppercase tracking-wide">
					{renderInline(prefix + b.text)}
				</p>
			);
		case "runin":
			return (
				<p className="mt-4 leading-[1.75]">
					{b.marker ? renderInline(prefix) : null}
					<strong className="font-semibold">{b.lead} </strong>
					{renderInline(b.rest)}
				</p>
			);
		default:
			return (
				<p className="mt-4 leading-[1.75]">{renderInline(prefix + b.text)}</p>
			);
	}
}

// Render the rich, citation-linked structure built from the source HTML.
// Case references stay inside the v2 reader.
function renderRuns(runs: CaseSegment["runs"]): ReactNode[] {
	return runs.map((r, i) => {
		if (r.star) {
			return (
				<span
					// biome-ignore lint/suspicious/noArrayIndexKey: static run list
					key={i}
					className="mx-1 font-mono text-[0.8em] text-[var(--cds-link)]"
				>
					[{r.star}]
				</span>
			);
		}
		if (r.sup) {
			return (
				// biome-ignore lint/suspicious/noArrayIndexKey: static run list
				<sup key={i} className="font-mono text-[0.7em] text-[var(--cds-link)]">
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
					href={`/v2/case/${r.case}`}
					className="text-[var(--cds-link)] hover:underline"
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
		<div>
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
							className="mt-4 mb-5 font-semibold text-[0.85em] uppercase tracking-wide"
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
							className="my-4 border-[var(--cds-border-strong)] border-l-2 pl-5 text-[0.95em] italic"
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
							className="mt-2 text-[0.85em] text-[var(--cds-text-2)] leading-relaxed"
						>
							{b.mark ? (
								<sup className="mr-1 font-mono font-semibold text-[var(--cds-link)]">
									{b.mark}
								</sup>
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
							className="mt-7 mb-3 scroll-mt-4 font-semibold text-[1.05em]"
						>
							{renderRuns(b.runs)}
						</h3>
					);
				}
				// Run-in subsection heading ("A. Prejudicial Hearsay. <text>"): bold
				// the lead clause, which is plain text at the start of the first run.
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
							className="mt-4 leading-[1.75]"
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
						className="mt-4 leading-[1.75]"
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
		<div>
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
