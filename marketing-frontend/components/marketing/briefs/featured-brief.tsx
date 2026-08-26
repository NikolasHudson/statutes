// The "latest brief" card — the same object on the marketing home and on the
// /data index, so the two can never disagree about what the latest brief says.
// Every number is read from the frozen snapshot (lib/briefs);
// nothing here is transcribed by hand, and a refresh that drops a key fails the
// build rather than publishing a stale sentence.
//
// Ink-band only: the categorical hues travel inside the snapshot and were
// validated colorblind-safe on #161616 (palette.ts), so both hosts place this
// card on a gray-100 band.

import Link from "next/link";
import { briefNo, formatAsOf, MOST_CITED_CASES } from "@/lib/briefs";
import { cn } from "@/lib/utils";
import { BubbleThumb } from "./bubble-thumb";
import { tint } from "./palette";

// Where the current latest brief lives. One constant so the home band, the
// index card, and anything else pointing at "the latest" move together the day
// brief 002 takes the slot.
export const LATEST_BRIEF_HREF = "/data/most-cited-cases";

const snap = MOST_CITED_CASES;
const fig1 = snap.figures[0];
const n = (x: number) => x.toLocaleString("en-US");

export function FeaturedBrief({ className }: { className?: string }) {
	return (
		<Link
			href={LATEST_BRIEF_HREF}
			className={cn(
				"group grid border border-[#393939] transition-colors hover:bg-[#262626] md:grid-cols-[1.1fr_1fr]",
				className,
			)}
		>
			<div className="flex flex-col p-6 sm:p-9">
				<div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
					<span className="font-mono text-[#78a9ff] text-xs uppercase tracking-[0.16em]">
						Latest · Data brief {briefNo(snap)}
					</span>
					<span className="font-mono text-[#a8a8a8] text-xs uppercase tracking-[0.1em]">
						As of {formatAsOf(snap.as_of)}
					</span>
				</div>
				<h2 className="mt-4 text-balance font-light text-3xl leading-[1.18] tracking-[-0.01em] sm:text-4xl">
					The Most-Cited Cases in Iowa
				</h2>
				<p className="mt-4 max-w-[34em] text-[#c6c6c6] text-[15.5px] leading-relaxed">
					{`The fifty decisions Iowa's appellate courts cite most, counted from ${n(snap.totals.edges)} citations across ${n(snap.totals.decisions)} decisions. The case they reach for most is not a constitutional landmark: it is `}
					<strong className="font-semibold text-[#f4f4f4]">
						In&nbsp;re&nbsp;P.L.
					</strong>
					{`, a ${fig1.bubbles[0].year} termination decision cited by ${n(fig1.bubbles[0].cites)} opinions. The full list, the chart, and how it was counted.`}
				</p>
				<div className="mt-5 flex flex-wrap gap-x-5 gap-y-1.5">
					{Object.entries(fig1.categories).map(([key, cat]) => (
						<span
							key={key}
							className="inline-flex items-center gap-2 text-[#c6c6c6] text-[13px]"
						>
							<span
								aria-hidden
								className="inline-block size-[11px] rounded-full border-[1.5px]"
								style={{
									borderColor: cat.color,
									background: tint(cat.color),
								}}
							/>
							{cat.label}
							<span className="font-mono text-[#a8a8a8] text-[11.5px]">
								{fig1.bubbles.filter((b) => b.cat === key).length}
							</span>
						</span>
					))}
				</div>
				<div className="mt-auto flex flex-wrap items-center justify-between gap-x-6 gap-y-2 pt-7">
					<span className="font-semibold text-[#78a9ff] text-sm">
						Read the brief{" "}
						<span
							aria-hidden
							className="inline-block transition-transform group-hover:translate-x-1 motion-reduce:transition-none"
						>
							→
						</span>
					</span>
					<span className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.1em]">
						1 figure · full table · method on the page
					</span>
				</div>
			</div>
			<div className="flex items-center border-[#393939] border-t p-4 md:border-t-0 md:border-l">
				<BubbleThumb figure={fig1} className="block h-auto w-full" />
			</div>
		</Link>
	);
}
