// Small formatting helpers for the case reader's citator surfaces.

import type { CitingDecision, TreatmentInfo } from "@/lib/iowa-browse";

// Short court labels, keyed by CourtListener slug.
const COURT_SHORT: Record<string, string> = {
	iowa: "Iowa",
	iowactapp: "Iowa Ct. App.",
};

export function courtShort(courtId: string, fallback = ""): string {
	return COURT_SHORT[courtId] || fallback || courtId;
}

export function courtLong(courtId: string, fallback = ""): string {
	if (fallback) return fallback;
	if (courtId === "iowa") return "Supreme Court of Iowa";
	if (courtId === "iowactapp") return "Court of Appeals of Iowa";
	return courtId;
}

export function yearOf(iso: string): string {
	return (iso || "").slice(0, 4);
}

export function fmtMonthYear(iso: string): string {
	if (!iso) return "";
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return iso;
	return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
}

// "Busker v. Sokolowski" → "Busker"; "State v. Plain" → "Plain"; "In re P.L."
// → "P.L." — the party a lawyer would use as the short form.
export function shortName(caseName: string): string {
	const name = caseName.trim();
	const parts = name.split(/\s+v(?:s)?\.\s+/i);
	const generic =
		/^(state|in re|in the matter of|estate of|city of|county of)\b/i;
	let side = parts[0];
	if (parts.length > 1 && generic.test(parts[0])) side = parts[1];
	side = side.replace(/^(in re|in the matter of|estate of)\s+/i, "");
	const first = side.split(/[,;]/)[0].trim().split(/\s+/);
	// Drop leading given names / initials when the party is a person:
	// "Joseph C. Kirk" → "Kirk". Company names keep their first word.
	const surnameish = first.filter((w) => !/^[A-Z]\.$/.test(w));
	if (
		surnameish.length >= 2 &&
		surnameish.length <= 4 &&
		/^[A-Z][a-z'’-]+$/.test(surnameish[surnameish.length - 1])
	) {
		return surnameish[surnameish.length - 1];
	}
	return surnameish[0] || name;
}

export function prettyLabel(t: TreatmentInfo): string {
	const raw = (t.label || t.status || "").replace(/-/g, " ");
	return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : "";
}

// The most recent citing decision, for the authority strip's helper line.
export function mostRecent(rows: CitingDecision[]): CitingDecision | null {
	let best: CitingDecision | null = null;
	for (const r of rows) {
		if (!best || r.date_filed > best.date_filed) best = r;
	}
	return best;
}
