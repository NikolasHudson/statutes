"use client";

// Opinion rendering for the case reader — the Carbon skin over the shared
// lib/case-format structure. Two paths: the rich, citation-linked
// body_segments built from the source HTML (case links get the hover card),
// and the plain-text fallback parsed by parseOpinion. Section headings hang
// their Roman numeral in the margin; West star-page breaks are quiet grey
// marginal marks rather than blue interruptions.

import { Fragment, memo, type ReactNode, useMemo } from "react";
import {
	type Block,
	isHeadingLine,
	parseOpinion,
	RUNIN,
	STAR,
} from "@/lib/case-format";
import type { CaseSegment } from "@/lib/iowa-browse";
import { CiteLink } from "./cite-hover-card";

const HEADING_NUM = /^([IVXLC]{1,5}|[A-D])\.\s+(.+)$/;

function StarPage({ page }: { page: string }) {
	return (
		<span
			title={`Reporter page ${page.replace("*", "")}`}
			className="mx-1 select-none align-[2px] font-mono text-[11px] text-[var(--cds-placeholder)] [font-family:var(--font-plex-mono)]"
		>
			{page}
		</span>
	);
}

// A section heading with its numeral hung to the left of the title.
function Heading({
	id,
	children,
	text,
}: {
	id?: string;
	children: ReactNode;
	text: string;
}) {
	const m = HEADING_NUM.exec(text);
	if (!m) {
		return (
			<h3
				id={id}
				className="mt-9 mb-1 scroll-mt-4 font-semibold text-[1.1em] leading-[1.35]"
			>
				{children}
			</h3>
		);
	}
	return (
		<h3
			id={id}
			className="mt-9 mb-1 flex gap-4 scroll-mt-4 font-semibold text-[1.1em] leading-[1.35]"
		>
			<span className="shrink-0 pt-[3px] font-mono text-[0.65em] text-[var(--cds-helper)] [font-family:var(--font-plex-mono)]">
				{m[1]}
			</span>
			<span>{m[2]}</span>
		</h3>
	);
}

const BYLINE_CLS =
	"mt-4 mb-5 font-semibold text-[13px] uppercase tracking-[0.06em] leading-[1.5] [font-family:var(--font-plex-sans)]";
const PARA_CLS = "mt-4 leading-[1.7]";

// Plain-text path — star pages only (no case links in the raw text).
function renderInline(text: string): ReactNode[] {
	return text.split(STAR).map((p, i) =>
		/^\*\d{1,4}$/.test(p) ? (
			// biome-ignore lint/suspicious/noArrayIndexKey: static inline split
			<StarPage key={i} page={p} />
		) : (
			p
		),
	);
}

// Strip the numeral for the hanging layout; keep any folded page marker.
function headingParts(text: string) {
	const m = HEADING_NUM.exec(text);
	return m ? m[2] : text;
}

function renderBlock(b: Block, headingId?: string): ReactNode {
	const prefix = b.marker ? `${b.marker} ` : "";
	switch (b.kind) {
		case "byline":
			return <p className={BYLINE_CLS}>{renderInline(prefix + b.text)}</p>;
		case "heading":
			return (
				<Heading id={headingId} text={b.text}>
					{b.marker ? renderInline(prefix) : null}
					{renderInline(headingParts(b.text))}
				</Heading>
			);
		case "label":
			return (
				<p className="mt-6 mb-2 font-semibold text-[0.8em] text-[var(--cds-helper)] uppercase tracking-wide">
					{renderInline(prefix + b.text)}
				</p>
			);
		case "runin":
			return (
				<p className={PARA_CLS}>
					{b.marker ? renderInline(prefix) : null}
					<strong className="font-semibold">{b.lead} </strong>
					{renderInline(b.rest)}
				</p>
			);
		default:
			return <p className={PARA_CLS}>{renderInline(prefix + b.text)}</p>;
	}
}

export const OpinionBody = memo(function OpinionBody({
	text,
	idPrefix,
}: {
	text: string;
	idPrefix: string;
}) {
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
});

// Rich path — runs with case links, star pages, footnote marks, italics.
function renderRuns(runs: CaseSegment["runs"]): ReactNode[] {
	return runs.map((r, i) => {
		if (r.star) {
			// biome-ignore lint/suspicious/noArrayIndexKey: static run list
			return <StarPage key={i} page={r.star} />;
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
				// biome-ignore lint/suspicious/noArrayIndexKey: static run list
				<CiteLink key={i} caseId={r.case}>
					{text}
				</CiteLink>
			);
		}
		if (r.em) {
			// biome-ignore lint/suspicious/noArrayIndexKey: static run list
			return <em key={i}>{text}</em>;
		}
		return text;
	});
}

// Drop the leading "I. " from a heading's first plain run so the numeral can
// hang in the margin; the rest of the runs are untouched.
function stripHeadingNumeral(runs: CaseSegment["runs"]): CaseSegment["runs"] {
	const first = runs[0];
	if (!first?.t || first.em || first.case != null) return runs;
	const m = /^([IVXLC]{1,5}|[A-D])\.\s+/.exec(first.t);
	if (!m) return runs;
	return [{ ...first, t: first.t.slice(m[0].length) }, ...runs.slice(1)];
}

export const SegmentBody = memo(function SegmentBody({
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
						// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
						<p key={i} className={BYLINE_CLS}>
							{renderRuns(b.runs)}
						</p>
					);
				}
				if (b.k === "quote") {
					return (
						<blockquote
							// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
							key={i}
							className="my-4 border-[var(--cds-border-strong)] border-l-2 pl-5 text-[0.95em] italic leading-[1.65]"
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
						// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
						<Heading key={i} id={hid} text={text}>
							{renderRuns(stripHeadingNumeral(b.runs))}
						</Heading>
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
						// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
						<p key={i} className={PARA_CLS}>
							<strong className="font-semibold">{runin[1]}</strong>
							{renderRuns(rest)}
						</p>
					);
				}
				return (
					// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered blocks
					<p key={i} className={PARA_CLS}>
						{renderRuns(b.runs)}
					</p>
				);
			})}
		</div>
	);
});
