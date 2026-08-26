"use client";

// Interactive packed-bubble figure for data briefs. The geometry (positions,
// radii, label lines, font sizes) is precomputed by the backend export and
// frozen in the snapshot — this component only draws it and layers on the
// hover/keyboard affordances: a tooltip carrying every bubble's full data
// (three of the fifty are too small to label in place; the tooltip and the
// table are how they stay reachable) and legend hover/focus that dims the
// other categories of THIS figure only.

import { useRef, useState } from "react";
import type { BriefBubble, BriefFigure } from "@/lib/briefs";
import { tint } from "./palette";

// Label lines sit on a 1.12em grid centred on the bubble; the count line
// runs 0.74× the name size. Mirrors the backend fitter — the two must agree
// or labels drift off the chords they were fitted to.
const LINE_STEP = 1.12;
const COUNT_FS = 0.74;

function BubbleLabel({ b }: { b: BriefBubble }) {
	if (!b.label.length) return null;
	const total = b.label.length + (b.count_label ? 1 : 0);
	const lineY = (i: number) => b.y + (i - (total - 1) / 2) * LINE_STEP * b.fs;
	return (
		<>
			{b.label.map((line, i) => (
				<text
					key={line}
					x={b.x}
					y={lineY(i)}
					fontSize={b.fs}
					textAnchor="middle"
					dominantBaseline="central"
					className="pointer-events-none fill-[#f4f4f4] font-semibold"
					style={{ fontFamily: "var(--font-plex-sans)" }}
				>
					{line}
				</text>
			))}
			{b.count_label && (
				<text
					x={b.x}
					y={lineY(total - 1)}
					fontSize={Math.round(COUNT_FS * b.fs * 10) / 10}
					textAnchor="middle"
					dominantBaseline="central"
					className="pointer-events-none fill-[#c6c6c6]"
					style={{ fontFamily: "var(--font-plex-mono)" }}
				>
					{b.cites.toLocaleString("en-US")}
				</text>
			)}
		</>
	);
}

export function BubbleChart({
	figure,
	unit,
	note,
}: {
	figure: BriefFigure;
	// Tooltip unit line, e.g. "citing opinions" / "citing Iowa opinions".
	unit: string;
	note?: string;
}) {
	const wrapRef = useRef<HTMLDivElement>(null);
	const tipRef = useRef<HTMLDivElement>(null);
	const [tip, setTip] = useState<{
		b: BriefBubble;
		x: number;
		y: number;
	} | null>(null);
	const [focusRank, setFocusRank] = useState<number | null>(null);
	const [dimCat, setDimCat] = useState<string | null>(null);

	const [vw, vh] = figure.viewbox;
	const counts = new Map<string, number>();
	for (const b of figure.bubbles) {
		counts.set(b.cat, (counts.get(b.cat) ?? 0) + 1);
	}

	const showTip = (b: BriefBubble, clientX: number, clientY: number) => {
		const wrap = wrapRef.current;
		if (!wrap) return;
		const wr = wrap.getBoundingClientRect();
		const tw = tipRef.current?.offsetWidth ?? 240;
		const th = tipRef.current?.offsetHeight ?? 120;
		let x = clientX - wr.left + 14;
		let y = clientY - wr.top + 14;
		if (x + tw > wrap.clientWidth - 8) x = clientX - wr.left - tw - 14;
		if (y + th > wrap.clientHeight - 8) y = clientY - wr.top - th - 14;
		setTip({ b, x: Math.max(4, x), y: Math.max(4, y) });
	};

	return (
		<div>
			<ul
				className="mt-6 flex flex-wrap gap-x-6 gap-y-2"
				aria-label="Categories"
			>
				{Object.entries(figure.categories).map(([key, cat]) => (
					<li key={key}>
						<button
							type="button"
							className="inline-flex cursor-default items-center gap-2 py-1 text-[#c6c6c6] text-sm"
							onPointerEnter={() => setDimCat(key)}
							onPointerLeave={() => setDimCat(null)}
							onFocus={() => setDimCat(key)}
							onBlur={() => setDimCat(null)}
						>
							<span
								aria-hidden
								className="inline-block size-[13px] rounded-full border-[1.5px]"
								style={{ borderColor: cat.color, background: tint(cat.color) }}
							/>
							{cat.label}
							<span className="font-mono text-[#a8a8a8] text-xs">
								{counts.get(key) ?? 0}
							</span>
						</button>
					</li>
				))}
			</ul>

			<div className="mt-7 overflow-x-auto">
				<div ref={wrapRef} className="relative min-w-[720px]">
					<svg
						viewBox={`0 0 ${vw} ${vh}`}
						role="img"
						aria-label={`Packed bubble chart: ${figure.bubbles.length} cases, bubble area proportional to ${unit}`}
						className="block h-auto w-full"
					>
						{figure.bubbles.map((b) => {
							const color = figure.categories[b.cat]?.color ?? "#c6c6c6";
							const active = tip?.b.rank === b.rank;
							const dimmed = dimCat !== null && b.cat !== dimCat;
							return (
								// biome-ignore lint/a11y/noInteractiveElementToNoninteractiveRole: each bubble is a keyboard-reachable data point — tabIndex opens the tooltip, the img role + label carry its data to screen readers
								<g
									key={b.rank}
									tabIndex={0}
									role="img"
									aria-label={`Rank ${b.rank}: ${b.name}, ${b.year}, ${b.court}, ${b.cites.toLocaleString("en-US")} ${unit}`}
									className="outline-none transition-opacity duration-150 motion-reduce:transition-none"
									style={{ opacity: dimmed ? 0.22 : 1 }}
									onPointerMove={(e) => showTip(b, e.clientX, e.clientY)}
									onPointerLeave={() => setTip(null)}
									onFocus={(e) => {
										setFocusRank(b.rank);
										const r = e.currentTarget.getBoundingClientRect();
										showTip(b, r.left + r.width / 2, r.top + r.height / 2);
									}}
									onBlur={() => {
										setFocusRank(null);
										setTip(null);
									}}
								>
									<circle
										cx={b.x}
										cy={b.y}
										r={b.r}
										fill={color}
										fillOpacity={active ? 0.52 : 0.32}
										stroke={focusRank === b.rank ? "#ffffff" : color}
										strokeWidth={active ? 2.5 : 1.5}
										className="transition-[fill-opacity,stroke-width] duration-150 motion-reduce:transition-none"
									/>
									<BubbleLabel b={b} />
								</g>
							);
						})}
					</svg>

					<div
						ref={tipRef}
						role="status"
						aria-hidden={tip ? "false" : "true"}
						className={
							tip
								? "pointer-events-none absolute z-10 block min-w-[200px] max-w-[320px] border border-[#393939] bg-[#262626] px-3.5 py-3"
								: "hidden"
						}
						style={tip ? { left: tip.x, top: tip.y } : undefined}
					>
						{tip && (
							<>
								<div className="font-light text-[#f4f4f4] text-[26px] leading-tight">
									{tip.b.cites.toLocaleString("en-US")}
									<span className="ml-1 font-normal text-[#a8a8a8] text-[13px]">
										{unit}
									</span>
								</div>
								<div className="mt-1.5 font-semibold text-[#f4f4f4] text-sm">
									{tip.b.name} ({tip.b.year})
								</div>
								{tip.b.full.toLowerCase() !== tip.b.name.toLowerCase() && (
									<div className="mt-0.5 text-[#a8a8a8] text-xs">
										{tip.b.full}
									</div>
								)}
								<div className="mt-2 flex items-center gap-2 text-[#c6c6c6] text-xs">
									<span
										aria-hidden
										className="inline-block w-3.5 border-t-[2.5px]"
										style={{
											borderTopColor:
												figure.categories[tip.b.cat]?.color ?? "#c6c6c6",
										}}
									/>
									{figure.categories[tip.b.cat]?.label} · {tip.b.court}
								</div>
							</>
						)}
					</div>
				</div>
			</div>

			{note && (
				<p className="mt-9 max-w-[52em] text-[#a8a8a8] text-[13px]">{note}</p>
			)}
		</div>
	);
}
