// US tile-grid coverage map for the /data/coverage pages. Three tiers in the
// Carbon blue ramp: Iowa (Blue 60, the full stack), the Eighth Circuit states
// (Blue 30, federal appellate decisions), and everything else (gray-10, not
// in the corpus yet). Tile positions follow the standard NPR-style tile-grid
// layout — geography readers expect Iowa mid-map with MN above and MO below.

import { cn } from "@/lib/utils";

type Tier = "ia" | "ca8" | "base";

// [abbr, gridColumn, gridRow, tier]
const STATES: [string, number, number, Tier][] = [
	["AK", 1, 1, "base"],
	["ME", 11, 1, "base"],

	["WI", 6, 2, "base"],
	["VT", 10, 2, "base"],
	["NH", 11, 2, "base"],

	["WA", 1, 3, "base"],
	["ID", 2, 3, "base"],
	["MT", 3, 3, "base"],
	["ND", 4, 3, "ca8"],
	["MN", 5, 3, "ca8"],
	["IL", 6, 3, "base"],
	["MI", 7, 3, "base"],
	["NY", 9, 3, "base"],
	["MA", 10, 3, "base"],
	["RI", 11, 3, "base"],

	["OR", 1, 4, "base"],
	["NV", 2, 4, "base"],
	["WY", 3, 4, "base"],
	["SD", 4, 4, "ca8"],
	["IA", 5, 4, "ia"],
	["IN", 6, 4, "base"],
	["OH", 7, 4, "base"],
	["PA", 8, 4, "base"],
	["NJ", 9, 4, "base"],
	["CT", 10, 4, "base"],

	["CA", 1, 5, "base"],
	["UT", 2, 5, "base"],
	["CO", 3, 5, "base"],
	["NE", 4, 5, "ca8"],
	["MO", 5, 5, "ca8"],
	["KY", 6, 5, "base"],
	["WV", 7, 5, "base"],
	["VA", 8, 5, "base"],
	["MD", 9, 5, "base"],
	["DE", 10, 5, "base"],

	["AZ", 2, 6, "base"],
	["NM", 3, 6, "base"],
	["KS", 4, 6, "base"],
	["AR", 5, 6, "ca8"],
	["TN", 6, 6, "base"],
	["NC", 7, 6, "base"],
	["SC", 8, 6, "base"],
	["DC", 9, 6, "base"],

	["OK", 4, 7, "base"],
	["LA", 5, 7, "base"],
	["MS", 6, 7, "base"],
	["AL", 7, 7, "base"],
	["GA", 8, 7, "base"],

	["HI", 1, 8, "base"],
	["TX", 4, 8, "base"],
	["FL", 8, 8, "base"],
];

const TIER_CLASS: Record<Tier, string> = {
	ia: "bg-[#0f62fe] font-medium text-white",
	ca8: "bg-[#a6c8ff] text-[#002d9c]",
	base: "bg-[#f4f4f4] text-[#a8a8a8]",
};

export function CoverageMap({ className }: { className?: string }) {
	return (
		<div
			role="img"
			aria-label="Tile map of the United States: Iowa holds the full stack, the Eighth Circuit states carry federal appellate decisions, the rest is not in the corpus yet."
			className={cn("grid w-full max-w-[616px] grid-cols-11 gap-1", className)}
		>
			{STATES.map(([abbr, col, row, tier]) => (
				<div
					key={abbr}
					style={{ gridColumn: col, gridRow: row }}
					className={cn(
						"aspect-square p-1 font-mono text-[9px] sm:p-1.5 sm:text-[11px]",
						TIER_CLASS[tier],
					)}
				>
					{abbr}
				</div>
			))}
		</div>
	);
}

const LEGEND: { swatch: string; label: string; body: string }[] = [
	{
		swatch: "bg-[#0f62fe]",
		label: "Iowa",
		body: "The full stack. Statutes, regulations, session laws, court rules, and state and federal case law.",
	},
	{
		swatch: "bg-[#a6c8ff]",
		label: "Eighth Circuit",
		body: "Federal appellate decisions that bind Iowa's district courts.",
	},
	{
		swatch: "border border-[#e0e0e0] bg-[#f4f4f4]",
		label: "Elsewhere",
		body: "Not in the corpus yet. Coverage is continuously expanding.",
	},
];

export function CoverageMapLegend({ className }: { className?: string }) {
	return (
		<ul className={cn("flex flex-col gap-5", className)}>
			{LEGEND.map((t) => (
				<li key={t.label} className="flex gap-3">
					<span aria-hidden className={cn("mt-1 size-3 shrink-0", t.swatch)} />
					<div>
						<p className="font-mono text-[11px] uppercase tracking-[0.12em]">
							{t.label}
						</p>
						<p className="mt-1 max-w-md text-[#525252] text-[13px] leading-relaxed">
							{t.body}
						</p>
					</div>
				</li>
			))}
		</ul>
	);
}
