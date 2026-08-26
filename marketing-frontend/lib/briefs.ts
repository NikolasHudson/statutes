// Data-brief snapshots for the /data section. Each snapshot is frozen JSON
// exported by the backend (`manage.py export_data_brief <name>`) and
// committed under content/data/ — the numbers on a published brief never
// drift; refreshing one is a deliberate re-export reviewed as a git diff,
// and deploy is the publish step (DATA_BRIEFS.md).

import citationConcentration from "@/content/data/citation-concentration.json";
import mostCitedCases from "@/content/data/most-cited-cases.json";

export type BriefCategory = { label: string; color: string };

export type BriefBubble = {
	rank: number;
	name: string;
	full: string;
	year: string;
	court: string;
	cites: number;
	cat: string;
	x: number;
	y: number;
	r: number;
	label: string[];
	fs: number;
	count_label: boolean;
};

export type BriefFigure = {
	id: string;
	viewbox: number[];
	categories: Record<string, BriefCategory>;
	bubbles: BriefBubble[];
};

export type BriefSnapshot = {
	slug: string;
	brief_no: number;
	as_of: string;
	totals: { edges: number; decisions: number };
	figures: BriefFigure[];
};

// Through `unknown` because TS unions the per-figure category literals
// ("family" | … vs "counsel" | …) into optional-key shapes that don't
// overlap the Record type, even though every snapshot satisfies it.
export const MOST_CITED_CASES = mostCitedCases as unknown as BriefSnapshot;

// Corpus-wide concentration counts behind brief 001's introduction (how many
// decisions are never cited, how many pass 100/500/1,000, the Varnum count).
// Frozen from the same corpus snapshot as MOST_CITED_CASES; the brief asserts
// the two agree on as-of and edge total before it will build.
export type ConcentrationSnapshot = {
	slug: string;
	as_of: string;
	provenance: string;
	definitions: Record<string, string>;
	numbers: Record<string, number>;
};

export const CITATION_CONCENTRATION =
	citationConcentration as ConcentrationSnapshot;

// Prose numbers are looked up, never typed into the copy — a refresh that
// drops a key fails the build instead of quietly publishing a stale number.
export function concentration(key: string): number {
	const v = CITATION_CONCENTRATION.numbers[key];
	if (v === undefined)
		throw new Error(
			`brief prose references a missing citation-concentration number: ${key}`,
		);
	return v;
}

export const n = (x: number): string => x.toLocaleString("en-US");
export const pct = (x: number, digits = 0): string =>
	`${(x * 100).toFixed(digits)}%`;

// Brief numbers render as a zero-padded series ("Data brief 001").
export function briefNo(snapshot: BriefSnapshot): string {
	return String(snapshot.brief_no).padStart(3, "0");
}

// "2026-08-13" → "13 Aug 2026", the as-of style used across the section.
export function formatAsOf(isoDate: string): string {
	const [y, m, d] = isoDate.split("-").map(Number);
	return `${d} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]} ${y}`;
}
