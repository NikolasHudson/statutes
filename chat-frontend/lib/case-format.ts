"use client";

// Opinion-text structure logic for the caselaw reader, shared by the legacy
// reader (components/case-console.tsx) and the Carbon v2 reader
// (app/v2/case/[id]) so document parsing can't drift between skins. No JSX
// here — rendering is the skin's job.
//
// Opinion bodies are CourtListener HTML stripped to plain text. Two paragraph
// conventions appear: modern Iowa Supreme Court opinions put one paragraph per
// line (single \n); older / Court of Appeals text uses blank-line separators.
// Treating every non-empty line as a paragraph handles both. On top of that we
// detect the byline, Roman-numeral section headings, run-in subsection
// headings, head-matter labels, and West star-pagination markers.

import { type RefObject, useEffect, useState } from "react";
import type { CaseDetail, CaseOpinion } from "@/lib/iowa-browse";

export const COURT_CITE: Record<string, string> = {
	iowa: "Iowa",
	iowactapp: "Iowa Ct. App.",
};

export type Section = { id: string; label: string; depth: number };

const AUTHOR_LINE =
	/^[A-Z][A-Z.\s,'’-]{2,40},\s*(?:Chief Justice|Justice|Judge|C\.?J\.?|P\.?J\.?|J\.)\.?$/;
const ROMAN_HEADING = /^[IVXLC]{1,5}\.(?:\s|$)/;
const LETTER_HEADING = /^[A-D]\.$/;
// Standalone lettered subsection heading: "A. Applicable law." — a single
// comma-free title clause ending the line (so it is NOT a run-in, which has
// trailing body text). Letters only (A–D); digits are too easily confused with
// numbered list sentences.
const SUBHEADING = /^[A-D]\.\s+[A-Z][^.,]*[.?]?$/;
const HEAD_LABEL = /^(?:Syllabus|Headnotes|Summary|Opinion)$/;
const DIVIDER = /^[_=–—-]{3,}$/;
// Run-in heading: "A. Prejudicial Hearsay. <text…>" or "1. Hearsay. <text…>".
// The lead clause is a short Title-cased phrase (no internal period) ending in
// a period, which excludes ordinary numbered sentences.
export const RUNIN = /^((?:[A-D]|\d{1,2})\.\s+[A-Z][^.]{1,55}\.)\s+(.+)$/;
// West star-pagination page break, e.g. *830 — often glued to the next word
// ("*810Gray"), so no trailing word boundary.
export const STAR = /(\*\d{1,4})/;
export const STAR_ONLY = /^\*\d{1,4}$/;

export type Block =
	| {
			kind: "byline" | "heading" | "label" | "para";
			text: string;
			marker?: string;
	  }
	| { kind: "runin"; lead: string; rest: string; marker?: string };

// A section/subsection title line (Roman "I."/"II.", bare "A.", or a lettered
// "A. Title." subsection) — rendered bold.
export function isHeadingLine(text: string): boolean {
	return (
		text.length <= 80 &&
		(ROMAN_HEADING.test(text) ||
			LETTER_HEADING.test(text) ||
			SUBHEADING.test(text))
	);
}

// Indentation level for the outline: a lettered subsection (A.–D., including
// "C."/"D." which are also Roman numerals) nests under a Roman section (I./II.).
export function headingDepth(text: string): number {
	return /^[A-D]\./.test(text) ? 1 : 0;
}

// Ordered section-heading texts within one opinion. Uses the SAME predicate the
// renderer uses to detect+id headings, so outline jump targets line up with the
// anchor ids (op-<id>-s<k>) assigned in render order.
export function opinionHeadings(op: CaseOpinion): string[] {
	if (op.body_segments) {
		const out: string[] = [];
		for (const b of op.body_segments) {
			if (b.k !== "p") continue;
			const t = b.runs
				.map((r) => r.t ?? "")
				.join("")
				.trim();
			if (isHeadingLine(t)) out.push(t);
		}
		return out;
	}
	const out: string[] = [];
	for (const b of parseOpinion(op.body_text)) {
		if (b.kind === "heading") out.push(b.text);
	}
	return out;
}

// Lines that should stand on their own (never absorb, or be absorbed into,
// surrounding prose during the rejoin pass below).
function isStructural(line: string): boolean {
	return (
		AUTHOR_LINE.test(line) ||
		RUNIN.test(line) ||
		HEAD_LABEL.test(line) ||
		isHeadingLine(line)
	);
}

// True when the text ends a sentence (ignoring trailing quotes/brackets), i.e.
// the next line is a NEW paragraph rather than a continuation.
function endsTerminal(s: string): boolean {
	return /[.?!:;]$/.test(s.replace(/[\s)\]}"'”’]+$/, ""));
}

function classify(text: string, first: boolean): Block {
	if (first && AUTHOR_LINE.test(text)) return { kind: "byline", text };
	// Run-in BEFORE standalone heading: "C."/"D." are both run-in letters and
	// Roman numerals, so a run-in like "C. Proximate Cause. <text>" must not be
	// mistaken for a heading. Roman section headings (I/II/III…) never match the
	// run-in pattern (its lead is [A-D] or a digit), so they're unaffected.
	const m = RUNIN.exec(text);
	if (m) return { kind: "runin", lead: m[1], rest: m[2] };
	if (isHeadingLine(text)) return { kind: "heading", text };
	if (HEAD_LABEL.test(text)) return { kind: "label", text };
	return { kind: "para", text };
}

export function parseOpinion(text: string): Block[] {
	const lines = text
		.split("\n")
		.map((l) => l.trim())
		.filter(Boolean);

	// Stage 1 — fold lone page markers forward, drop divider rules, and rejoin
	// fragments that were split across lines (some opinions store each citation
	// on its own line). A non-structural fragment continues the previous
	// paragraph when that paragraph is prose that didn't end a sentence, or when
	// the fragment itself starts lowercase (e.g. "at 918-19.").
	type Entry = { text: string; marker: string; structural: boolean };
	const entries: Entry[] = [];
	let marker = "";
	for (const line of lines) {
		if (STAR_ONLY.test(line)) {
			marker = marker ? `${marker} ${line}` : line;
			continue;
		}
		if (DIVIDER.test(line)) continue;
		const structural = isStructural(line);
		const prev = entries[entries.length - 1];
		if (
			!structural &&
			prev &&
			!prev.structural &&
			(!endsTerminal(prev.text) || /^[a-z]/.test(line))
		) {
			prev.text += marker ? ` ${marker} ${line}` : ` ${line}`;
			marker = "";
		} else {
			entries.push({ text: line, marker, structural });
			marker = "";
		}
	}
	if (marker) entries.push({ text: marker, marker: "", structural: false });

	// Stage 2 — classify each rejoined line and attach any folded page marker.
	const out: Block[] = [];
	let first = true;
	for (const e of entries) {
		const block = classify(e.text, first);
		first = false;
		if (e.marker) block.marker = e.marker;
		out.push(block);
	}
	return out;
}

// A Bluebook-ish citation for the "Copy citation" action, e.g.
// "State v. Plain, 898 N.W.2d 801 (Iowa 2017)."
export function buildCitation(d: CaseDetail): string {
	const year = (d.date_filed || "").slice(0, 4);
	const court = COURT_CITE[d.court_id] || "Iowa";
	const paren = year ? `(${court} ${year})` : `(${court})`;
	const reporter = d.citations[0];
	return reporter
		? `${d.case_name}, ${reporter} ${paren}.`
		: `${d.case_name} ${paren}.`;
}

// Build the document outline for a case: syllabus, opinions, and per-opinion
// section headings (multi-opinion cases nest headings under each opinion).
export function caseSections(data: CaseDetail): Section[] {
	const list: Section[] = [];
	if (data.head_matter) {
		list.push({ id: "syllabus", label: "Syllabus", depth: 0 });
	}
	const multi = data.opinions.length > 1;
	for (const op of data.opinions) {
		const prefix = `op-${op.id}`;
		if (multi) list.push({ id: prefix, label: op.heading, depth: 0 });
		opinionHeadings(op).forEach((t, k) => {
			list.push({
				id: `${prefix}-s${k}`,
				label: t,
				depth: (multi ? 1 : 0) + headingDepth(t),
			});
		});
	}
	return list;
}

// Highlight the outline entry for the section crossing the top of the reading
// pane — geometric (top-edge) selection, correct regardless of section height,
// and snaps to the last section at the end of the scroll.
export function useActiveSection(
	ids: string[],
	rootRef: RefObject<HTMLElement | null>,
): string | null {
	const [active, setActive] = useState<string | null>(ids[0] ?? null);
	useEffect(() => {
		const root = rootRef.current;
		if (!root || ids.length === 0) {
			setActive(ids[0] ?? null);
			return;
		}
		let frame = 0;
		const compute = () => {
			frame = 0;
			if (root.scrollTop + root.clientHeight >= root.scrollHeight - 4) {
				setActive(ids[ids.length - 1]);
				return;
			}
			const rootTop = root.getBoundingClientRect().top;
			const offset = 96;
			let current = ids[0];
			for (const id of ids) {
				const el = root.querySelector<HTMLElement>(`#${CSS.escape(id)}`);
				if (!el) continue;
				const top = el.getBoundingClientRect().top - rootTop;
				if (top <= offset) current = id;
				else break;
			}
			setActive(current);
		};
		const onScroll = () => {
			if (!frame) frame = requestAnimationFrame(compute);
		};
		compute();
		root.addEventListener("scroll", onScroll, { passive: true });
		window.addEventListener("resize", onScroll);
		return () => {
			root.removeEventListener("scroll", onScroll);
			window.removeEventListener("resize", onScroll);
			if (frame) cancelAnimationFrame(frame);
		};
	}, [ids, rootRef]);
	return active;
}
