"use client";

// The in-page product nav — ibm.com's product-page signature: a second sticky
// bar under the masthead carrying the product's name and anchors to every
// section on the page.
//
// IBM pins a buy/try action at this bar's trailing edge too; we don't. The
// Carbon masthead directly above already ends in a full-height Blue-60 CTA, so
// a second blue button 48px below it is the same call to action twice, stacked.
// Each page's own actions live in the leadspace and the closing band instead.
//
// Sits at top-12 because the Carbon masthead (carbon-nav.tsx) is a 48px sticky
// bar; the two stack to 96px, which is why every section anchored here carries
// scroll-mt-24. Below lg the product name drops and the links scroll
// horizontally — a 48px bar cannot hold both on a phone.
//
// Active state is observed, not computed from scroll offsets: an
// IntersectionObserver marks which sections are in the band between the sticky
// chrome and the fold, and the deepest one whose top has already passed under
// that chrome wins — the section you are reading, not the one still leaving.
// Clicking a link claims the active state immediately so the highlight never
// lags the smooth scroll.

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export type SubnavSection = { id: string; label: string };

// Just under the two sticky bars (48 + 48): the line a section's heading has
// to cross before the bar calls it the current one.
const READING_LINE = 112;

export function ProductSubnav({
	product,
	sections,
}: {
	/** Product name, shown at the leading edge on large screens. */
	product: string;
	sections: SubnavSection[];
}) {
	// Starts on the first section rather than blank: at the top of the page the
	// bar has just scrolled up out of the leadspace, and an unmarked nav reads
	// as broken.
	const [active, setActive] = useState<string | null>(sections[0]?.id ?? null);
	// Set by a click; suppresses observer updates until the scroll settles, or
	// the sections passed on the way down would each flash active in turn.
	const claimed = useRef<string | null>(null);
	const claimTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

	// biome-ignore lint/correctness/useExhaustiveDependencies: the id list, not the array identity, is what matters
	useEffect(() => {
		const ids = sections.map((s) => s.id);
		const els = ids
			.map((id) => document.getElementById(id))
			.filter((el): el is HTMLElement => el !== null);
		if (els.length === 0) return;

		const visible = new Set<string>();
		const io = new IntersectionObserver(
			(entries) => {
				for (const e of entries) {
					if (e.isIntersecting) visible.add(e.target.id);
					else visible.delete(e.target.id);
				}
				if (claimed.current) return;
				const onScreen = els.filter((el) => visible.has(el.id));
				if (onScreen.length === 0) return; // above the first / past the last
				// The section being READ is the last one whose top has already
				// crossed under the sticky chrome — not the first one still
				// clinging to the top edge on its way out.
				const crossed = onScreen.filter(
					(el) => el.getBoundingClientRect().top <= READING_LINE,
				);
				const el =
					crossed.length > 0 ? crossed[crossed.length - 1] : onScreen[0];
				setActive(el.id);
			},
			// Top edge sits just under the two sticky bars; the bottom margin keeps
			// a section from counting as "current" while it is still a sliver at the
			// foot of the viewport.
			{ rootMargin: "-104px 0px -55% 0px", threshold: 0 },
		);
		for (const el of els) io.observe(el);
		return () => io.disconnect();
	}, [sections.map((s) => s.id).join("|")]);

	useEffect(
		() => () => {
			if (claimTimer.current) clearTimeout(claimTimer.current);
		},
		[],
	);

	const claim = (id: string) => {
		setActive(id);
		claimed.current = id;
		if (claimTimer.current) clearTimeout(claimTimer.current);
		claimTimer.current = setTimeout(() => {
			claimed.current = null;
		}, 700);
	};

	return (
		<div
			data-print="hide"
			className="sticky top-12 z-40 border-border border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
		>
			<div className="mx-auto flex h-12 max-w-7xl items-stretch px-5 sm:px-8">
				<span className="hidden shrink-0 items-center pr-8 font-semibold text-sm lg:flex">
					{product}
				</span>
				<nav
					aria-label={`${product} sections`}
					className="flex min-w-0 items-stretch overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
				>
					{sections.map((s) => (
						<a
							key={s.id}
							href={`#${s.id}`}
							onClick={() => claim(s.id)}
							aria-current={active === s.id ? "true" : undefined}
							className={cn(
								"flex items-center whitespace-nowrap border-b-2 px-4 text-sm transition-colors hover:text-foreground",
								active === s.id
									? "border-[#0f62fe] text-foreground"
									: "border-transparent text-muted-foreground",
							)}
						>
							{s.label}
						</a>
					))}
				</nav>
			</div>
		</div>
	);
}
