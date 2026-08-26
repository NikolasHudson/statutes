"use client";

// The Features panel, on the ibm.com product-page model: a rail of feature
// names beside one panel that swaps — the whole feature set is legible at a
// glance without a page of stacked screenshots, and the selected feature gets
// the room a dense app capture needs (the rail takes ~1/4 of the container, the
// shot the rest).
//
// Carbon tab treatment: the rail is gray-100, the same ink as the masthead and
// the dark bands, and the selected item carries a Blue-60 edge (leading edge on
// the vertical rail, bottom on the small-screen strip) against a lifted row;
// the panel beside it stays on the white layer. Real tablist semantics — roving
// tabindex, arrow / Home / End keys — because the rail is a tab list, not a
// list of links.

import { useRef, useState } from "react";
import { CodeFrame, Frame, INK, TextLink } from "@/components/marketing/carbon";
import { cn } from "@/lib/utils";

export type ProductFeature = {
	id: string;
	/** Short rail label, e.g. "Search". */
	label: string;
	/** Panel headline. IBM writes these as "Capability: what you get". */
	title: string;
	body: string;
	points: string[];
	links?: { label: string; href: string }[];
	/** A product capture… */
	shot?: { src: string; alt: string; caption: string; url?: string };
	/** …or a config/code block, for the products whose surface is text. */
	code?: { caption: string; code: string; url?: string };
};

export function FeatureTabs({ features }: { features: ProductFeature[] }) {
	const [active, setActive] = useState(0);
	const tabs = useRef<(HTMLButtonElement | null)[]>([]);

	const move = (to: number) => {
		const i = (to + features.length) % features.length;
		setActive(i);
		tabs.current[i]?.focus();
	};

	const onKeyDown = (e: React.KeyboardEvent) => {
		// Both axes: the rail is vertical on lg and a horizontal strip below it.
		if (e.key === "ArrowDown" || e.key === "ArrowRight") move(active + 1);
		else if (e.key === "ArrowUp" || e.key === "ArrowLeft") move(active - 1);
		else if (e.key === "Home") move(0);
		else if (e.key === "End") move(features.length - 1);
		else return;
		e.preventDefault();
	};

	const f = features[active];

	return (
		<div className="grid gap-px border border-border bg-border lg:grid-cols-[minmax(200px,1fr)_3fr]">
			{/* The tablist itself is never focused: focus lives on the tabs, and the
			    arrow keys are handled here so they work from whichever one has it. */}
			<div
				role="tablist"
				onKeyDown={onKeyDown}
				// min-w-0: a grid item's automatic minimum is its content, so without
				// this the nowrap tab strip widens the whole grid past the viewport
				// on a phone instead of scrolling inside its own row.
				// The rail carries the brand's own colours — gray-100 with a Blue-60
				// selection edge, the same pair as the masthead — because a white rail
				// beside a white panel had nothing but a hairline holding it, and read
				// as floating rather than as the page's own navigation.
				className={cn(
					"flex min-w-0 overflow-x-auto [scrollbar-width:none] lg:flex-col lg:overflow-visible [&::-webkit-scrollbar]:hidden",
					INK,
				)}
			>
				{features.map((feat, i) => (
					<button
						key={feat.id}
						type="button"
						role="tab"
						id={`tab-${feat.id}`}
						aria-selected={i === active}
						aria-controls={`panel-${feat.id}`}
						tabIndex={i === active ? 0 : -1}
						ref={(el) => {
							tabs.current[i] = el;
						}}
						onClick={() => setActive(i)}
						className={cn(
							// Carbon's side-nav selection on dark: a Blue-60 edge — bottom
							// on the small-screen strip, leading edge on the vertical rail —
							// with the selected row lifted to gray-80's neighbour.
							"whitespace-nowrap border-b-2 px-5 py-4 text-left text-sm transition-colors lg:border-b-0 lg:border-l-2 lg:px-6 lg:py-5",
							i === active
								? "border-[#0f62fe] bg-[#262626] font-semibold text-white"
								: "border-transparent text-[#c6c6c6] hover:bg-[#292929] hover:text-white",
						)}
					>
						{feat.label}
					</button>
				))}
			</div>

			<div
				role="tabpanel"
				id={`panel-${f.id}`}
				aria-labelledby={`tab-${f.id}`}
				className="min-w-0 bg-card p-6 sm:p-8 lg:p-10"
			>
				<h3 className="max-w-2xl font-light text-2xl leading-snug sm:text-[1.75rem]">
					{f.title}
				</h3>
				<p className="mt-4 max-w-2xl text-[15.5px] text-foreground/80 leading-[1.7]">
					{f.body}
				</p>

				<ul className="mt-8 grid gap-x-8 gap-y-5 sm:grid-cols-3">
					{f.points.map((p) => (
						<li
							key={p}
							className="border-border border-t pt-4 text-[13.5px] text-foreground/85 leading-snug"
						>
							{p}
						</li>
					))}
				</ul>

				{f.links && f.links.length > 0 && (
					<div className="mt-8 flex flex-wrap gap-x-8 gap-y-3">
						{f.links.map((l) => (
							<TextLink key={l.href + l.label} href={l.href}>
								{l.label}
							</TextLink>
						))}
					</div>
				)}

				{f.shot && (
					<Frame
						className="mt-10"
						src={f.shot.src}
						alt={f.shot.alt}
						caption={f.shot.caption}
						url={f.shot.url}
					/>
				)}
				{f.code && (
					<CodeFrame
						className="mt-10"
						caption={f.code.caption}
						code={f.code.code}
						url={f.code.url}
					/>
				)}
			</div>
		</div>
	);
}
