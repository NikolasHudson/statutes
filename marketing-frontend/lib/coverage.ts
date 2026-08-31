// Coverage snapshots for the /data/coverage/<unit> pages. Same contract as
// the data briefs (lib/briefs.ts): each snapshot is frozen JSON exported by
// the backend (`manage.py export_coverage_snapshot iowa`) and committed under
// content/data/ — the numbers on a published coverage page never drift, and
// refreshing one is a deliberate re-export reviewed as a git diff.

import coverageEighthCircuit from "@/content/data/coverage-eighth-circuit.json";
import coverageIowa from "@/content/data/coverage-iowa.json";

export type CoverageCourt = { key: string; name: string; decisions: number };

export type CoverageSnapshot = {
	slug: string;
	as_of: string;
	totals: {
		authorities: number;
		decisions: number;
		connections: number;
		sources: number;
	};
	iowa_code: { sections: number; chapters: number; edition_years: number[] };
	iowa_admin_code: { rules: number; chapters: number; agencies: number };
	iowa_acts: {
		sections: number;
		chapters: number;
		sessions: number;
		first_year: number;
		last_year: number;
		first_ga: number;
		last_ga: number;
	};
	iowa_court_rules: { rules: number; chapters: number };
	iowa_caselaw: {
		decisions: number;
		first: string;
		last: string;
		courts: CoverageCourt[];
	};
	federal_caselaw: {
		decisions: number;
		first: string;
		last: string;
		courts: CoverageCourt[];
	};
	connections: { statute_rule: number; act_code: number };
};

export const COVERAGE_IOWA = coverageIowa as CoverageSnapshot;

// A caselaw holding with its date span, the building block of the
// eighth-circuit snapshot.
export type CoverageBucket = { decisions: number; first: string; last: string };

export type EighthCircuitSnapshot = {
	slug: string;
	as_of: string;
	totals: { decisions: number; cross_citations: number; states: number };
	ca8: CoverageBucket;
	bap: CoverageBucket;
	iowa_federal: CoverageBucket & {
		courts: { name: string; decisions: number }[];
	};
	historical: CoverageBucket;
	connections: {
		federal_to_iowa: number;
		iowa_to_federal: number;
		graph_edges: number;
	};
};

export const COVERAGE_EIGHTH_CIRCUIT =
	coverageEighthCircuit as EighthCircuitSnapshot;

// "88" → "88th", "91" → "91st". Derived here so the source data's ordinal
// typos ("91th") can never reach the page.
export function ordinal(x: number): string {
	const rem100 = x % 100;
	if (rem100 >= 11 && rem100 <= 13) return `${x}th`;
	return `${x}${["th", "st", "nd", "rd"][x % 10] ?? "th"}`;
}

export const isoYear = (iso: string): number => Number(iso.slice(0, 4));

// "2026-08-31" → "August 31, 2026" for the hero's counted-on line.
export function formatCounted(iso: string): string {
	const [y, m, d] = iso.split("-").map(Number);
	return `${isoMonthYear(`${y}-${String(m).padStart(2, "0")}`).split(" ")[0]} ${d}, ${y}`;
}

// "2026-08-19" → "August 2026", the span style used on the shelf rows.
export function isoMonthYear(iso: string): string {
	const [y, m] = iso.split("-").map(Number);
	return `${
		[
			"January",
			"February",
			"March",
			"April",
			"May",
			"June",
			"July",
			"August",
			"September",
			"October",
			"November",
			"December",
		][m - 1]
	} ${y}`;
}
