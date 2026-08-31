"use client";

// Carbon UI-shell-style header for the marketing site (client: mobile-menu
// state + active-route highlight). Spec: 48px gray-100 (#161616) bar, 14px
// items as full-height hit targets hovering to #292929, bold-prefix wordmark,
// a full-height Blue-60 CTA at the trailing edge, and a 3px blue bottom border
// on the current page's item (Carbon's "current" treatment).
//
// Data is a mega menu, on IBM's masthead model (the machinery is the former
// Products mega menu, which left with the product line-up on 2026-08-30): the
// item is a button that drops a full-bleed dark panel — a left rail that says
// what /data IS, then the two halves of the section, Data briefs and
// Coverage, each entry with a line of copy. It opens on hover AND on click,
// closes on Escape, on a click outside, on tabbing out, and on navigation.
// Below md the same list becomes an accordion inside the mobile menu, where a
// hover-opened panel would be unreachable.

import { ArrowRightIcon, ChevronDownIcon, MenuIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { GET_STARTED_URL, SIGN_IN_URL } from "@/lib/site";
import { cn } from "@/lib/utils";
import {
	ABOUT_HREF,
	ARTICLES_HREF,
	COVERAGE_EIGHTH_CIRCUIT_HREF,
	COVERAGE_IOWA_HREF,
	DATA_HREF,
	MARKETING_HOME,
	MOST_CITED_BRIEF_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "./chrome";

// The product leads the nav; Data renders as the mega-menu trigger between
// Pricing and Articles, holding its old slot in the order.
const NAV_LINKS_BEFORE = [
	{ label: "Hudson Corpus", href: PRODUCT_HREF },
	{ label: "Pricing", href: PRICING_HREF },
];
const NAV_LINKS_AFTER = [
	{ label: "Articles", href: ARTICLES_HREF },
	{ label: "About", href: ABOUT_HREF },
];

// The two halves of /data. Copy states what each destination IS — numbers
// stay on the pages themselves, where they render from frozen snapshots.
const DATA_COLUMNS: {
	label: string;
	entries: { title: string; tagline: string; href: string }[];
}[] = [
	{
		label: "Data briefs",
		entries: [
			{
				title: "The most-cited cases",
				tagline:
					"Brief 001. Which Iowa decisions do the work, measured across the whole citation graph.",
				href: MOST_CITED_BRIEF_HREF,
			},
			{
				title: "All briefs and the pipeline",
				tagline: "Published briefs, plus the questions being prepared next.",
				href: DATA_HREF,
			},
		],
	},
	{
		label: "Coverage",
		entries: [
			{
				title: "Coverage: Iowa",
				tagline:
					"The full inventory of what the corpus holds, counted from the live record.",
				href: COVERAGE_IOWA_HREF,
			},
			{
				title: "Coverage: Eighth Circuit",
				tagline: "The federal courts above Iowa practice, court by court.",
				href: COVERAGE_EIGHTH_CIRCUIT_HREF,
			},
			{
				title: "Request coverage",
				tagline: "Ask for the next state, court, or source.",
				href: `${COVERAGE_IOWA_HREF}#request`,
			},
		],
	},
];

// Carbon header-name treatment: bold prefix, regular product name.
export function CarbonWordmark() {
	return (
		<Link
			href={MARKETING_HOME}
			className="flex items-baseline gap-1.5 whitespace-nowrap text-sm"
		>
			<span className="font-semibold tracking-wide">Hudson</span>
			<span className="hidden text-[#c6c6c6] sm:inline">
				Legal Technologies
			</span>
		</Link>
	);
}

export function CarbonNav() {
	const [menuOpen, setMenuOpen] = useState(false);
	const [mobileDataOpen, setMobileDataOpen] = useState(false);
	const [megaOpen, setMegaOpen] = useState(false);
	const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
	const triggerRef = useRef<HTMLButtonElement>(null);
	const pathname = usePathname();

	const isCurrent = (href: string) =>
		pathname === href || pathname.startsWith(`${href}/`);
	const onData = isCurrent(DATA_HREF);

	// Hover intent: the panel sits flush under the bar, so a short grace period
	// is all that's needed to cross from trigger to panel without a flicker.
	const cancelClose = () => {
		if (closeTimer.current) {
			clearTimeout(closeTimer.current);
			closeTimer.current = null;
		}
	};
	const openMega = () => {
		cancelClose();
		setMegaOpen(true);
	};
	const scheduleClose = () => {
		cancelClose();
		closeTimer.current = setTimeout(() => setMegaOpen(false), 140);
	};

	// Navigating closes everything: the panel would otherwise still be hanging
	// open over the page it just linked to.
	// biome-ignore lint/correctness/useExhaustiveDependencies: pathname is the trigger
	useEffect(() => {
		setMegaOpen(false);
		setMenuOpen(false);
		setMobileDataOpen(false);
	}, [pathname]);

	useEffect(
		() => () => {
			if (closeTimer.current) clearTimeout(closeTimer.current);
		},
		[],
	);

	// Escape closes the panel and hands focus back to its trigger. Bound to the
	// document, not the header, so it fires wherever focus happens to be —
	// including the scrim.
	useEffect(() => {
		if (!megaOpen) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key !== "Escape") return;
			if (closeTimer.current) clearTimeout(closeTimer.current);
			setMegaOpen(false);
			triggerRef.current?.focus();
		};
		document.addEventListener("keydown", onKey);
		return () => document.removeEventListener("keydown", onKey);
	}, [megaOpen]);

	const navLink = (l: { label: string; href: string }) => (
		<Link
			key={l.label}
			href={l.href}
			className={cn(
				"flex items-center border-transparent border-b-[3px] px-4 text-sm transition-colors hover:bg-[#292929] hover:text-white",
				isCurrent(l.href) ? "border-[#0f62fe] text-white" : "text-[#c6c6c6]",
			)}
		>
			{l.label}
		</Link>
	);

	return (
		<header
			data-print="hide"
			className="sticky top-0 z-50 border-[#393939] border-b bg-[#161616] text-white"
		>
			<div className="mx-auto flex h-12 max-w-7xl items-stretch px-5 sm:px-8">
				<div className="flex items-center pr-6">
					<CarbonWordmark />
				</div>

				<nav className="hidden items-stretch md:flex">
					{NAV_LINKS_BEFORE.map(navLink)}
					<button
						type="button"
						ref={triggerRef}
						aria-expanded={megaOpen}
						aria-controls="data-mega"
						onClick={() => (megaOpen ? setMegaOpen(false) : openMega())}
						// Pointer events, filtered to a real mouse: a tap on a touch
						// device synthesizes mouseenter before click, so hover-to-open
						// would open the panel and the click would immediately shut it.
						onPointerEnter={(e) => {
							if (e.pointerType === "mouse") openMega();
						}}
						onPointerLeave={(e) => {
							if (e.pointerType === "mouse") scheduleClose();
						}}
						className={cn(
							"flex items-center gap-1.5 border-transparent border-b-[3px] px-4 text-sm transition-colors hover:bg-[#292929] hover:text-white",
							onData || megaOpen
								? "border-[#0f62fe] text-white"
								: "text-[#c6c6c6]",
							megaOpen && "bg-[#292929]",
						)}
					>
						Data
						<ChevronDownIcon
							aria-hidden
							className={cn(
								"size-3.5 transition-transform",
								megaOpen && "rotate-180",
							)}
						/>
					</button>
					{/* Rendered here, not further down the header, so the tab order
					    runs trigger → panel links → the rest of the nav. It is
					    absolutely positioned against the header either way. */}
					{megaOpen && (
						<>
							{/* Scrim: dims the page under an open panel and takes the
							    click-outside that closes it. */}
							<button
								type="button"
								tabIndex={-1}
								aria-label="Close data menu"
								onClick={() => setMegaOpen(false)}
								onMouseEnter={scheduleClose}
								className="fixed inset-x-0 top-12 bottom-0 cursor-default bg-black/50"
							/>
							<MegaPanel
								onMouseEnter={cancelClose}
								onMouseLeave={scheduleClose}
								onClose={() => setMegaOpen(false)}
							/>
						</>
					)}
					{NAV_LINKS_AFTER.map(navLink)}
				</nav>

				<div className="ms-auto hidden items-stretch md:flex">
					<a
						href={SIGN_IN_URL}
						className="flex items-center px-4 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
					>
						Sign in
					</a>
					<a
						href={GET_STARTED_URL}
						className="flex items-center gap-6 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9]"
					>
						Start researching
						<ArrowRightIcon className="size-4" />
					</a>
				</div>

				<button
					type="button"
					onClick={() => setMenuOpen(!menuOpen)}
					className="ms-auto flex w-12 items-center justify-center text-white transition-colors hover:bg-[#292929] md:hidden"
					aria-label="Toggle menu"
				>
					{menuOpen ? (
						<XIcon className="size-5" />
					) : (
						<MenuIcon className="size-5" />
					)}
				</button>
			</div>

			{menuOpen && (
				<div className="border-[#393939] border-t bg-[#161616] md:hidden">
					<nav className="flex flex-col">
						{NAV_LINKS_BEFORE.map((l) => (
							<Link
								key={l.label}
								href={l.href}
								onClick={() => setMenuOpen(false)}
								className={cn(
									"border-[#292929] border-b px-5 py-3.5 text-sm transition-colors hover:bg-[#292929] hover:text-white",
									isCurrent(l.href) ? "text-white" : "text-[#c6c6c6]",
								)}
							>
								{l.label}
							</Link>
						))}
						<button
							type="button"
							aria-expanded={mobileDataOpen}
							onClick={() => setMobileDataOpen(!mobileDataOpen)}
							className={cn(
								"flex items-center justify-between border-[#292929] border-b px-5 py-3.5 text-sm transition-colors hover:bg-[#292929] hover:text-white",
								onData ? "text-white" : "text-[#c6c6c6]",
							)}
						>
							Data
							<ChevronDownIcon
								aria-hidden
								className={cn(
									"size-4 transition-transform",
									mobileDataOpen && "rotate-180",
								)}
							/>
						</button>
						{mobileDataOpen && (
							<div className="border-[#292929] border-b bg-[#0b0b0b]">
								{DATA_COLUMNS.flatMap((col) => col.entries).map((e) => (
									<Link
										key={e.href}
										href={e.href}
										onClick={() => setMenuOpen(false)}
										className="block px-5 py-3 transition-colors hover:bg-[#292929]"
									>
										<span className="block text-sm text-white">{e.title}</span>
										<span className="mt-0.5 block text-[#a8a8a8] text-xs leading-snug">
											{e.tagline}
										</span>
									</Link>
								))}
								<Link
									href={DATA_HREF}
									onClick={() => setMenuOpen(false)}
									className="flex items-center justify-between px-5 py-3 text-[#78a9ff] text-sm transition-colors hover:bg-[#292929]"
								>
									All of Data
									<ArrowRightIcon className="size-4" />
								</Link>
							</div>
						)}
						{NAV_LINKS_AFTER.map((l) => (
							<Link
								key={l.label}
								href={l.href}
								onClick={() => setMenuOpen(false)}
								className={cn(
									"border-[#292929] border-b px-5 py-3.5 text-sm transition-colors hover:bg-[#292929] hover:text-white",
									isCurrent(l.href) ? "text-white" : "text-[#c6c6c6]",
								)}
							>
								{l.label}
							</Link>
						))}
						<a
							href={SIGN_IN_URL}
							className="border-[#292929] border-b px-5 py-3.5 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
						>
							Sign in
						</a>
						<a
							href={GET_STARTED_URL}
							className="flex items-center justify-between bg-[#0f62fe] px-5 py-3.5 text-sm text-white transition-colors hover:bg-[#0353e9]"
						>
							Start researching
							<ArrowRightIcon className="size-4" />
						</a>
					</nav>
				</div>
			)}
		</header>
	);
}

// ---------------------------------------------------------------------------
// The panel
// ---------------------------------------------------------------------------

function MegaPanel({
	onMouseEnter,
	onMouseLeave,
	onClose,
}: {
	onMouseEnter: () => void;
	onMouseLeave: () => void;
	onClose: () => void;
}) {
	return (
		// biome-ignore lint/a11y/noStaticElementInteractions: hover intent for a menu the keyboard reaches by tabbing
		<div
			id="data-mega"
			onMouseEnter={onMouseEnter}
			onMouseLeave={onMouseLeave}
			onBlur={(e) => {
				// Tabbing past the last link closes the panel behind you.
				if (!e.currentTarget.contains(e.relatedTarget)) onClose();
			}}
			className="absolute inset-x-0 top-full animate-[mega-drop_180ms_ease-out] border-[#393939] border-b bg-[#161616] text-left shadow-[0_16px_40px_rgba(0,0,0,0.5)] motion-reduce:animate-none"
		>
			<div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 lg:py-12">
				<div className="grid gap-10 lg:grid-cols-[0.85fr_1fr_1fr] lg:gap-0">
					<div className="lg:pr-12">
						<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
							Data
						</p>
						<p className="mt-6 font-light text-2xl leading-snug">
							Research from the record itself.
						</p>
						<p className="mt-4 text-[#a8a8a8] text-sm leading-relaxed">
							Original analysis of Iowa law, and a public inventory of what the
							corpus holds. Every number is computed from the full record,
							frozen, and citable.
						</p>
						<Link
							href={DATA_HREF}
							className="group mt-7 inline-flex items-center gap-2 font-medium text-[#78a9ff] text-sm hover:underline"
						>
							All of Data
							<ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
						</Link>
					</div>

					{DATA_COLUMNS.map((col) => (
						<div
							key={col.label}
							// pr-8 buys room for the link rows' -mx-4 hover bleed: with
							// gap-0 columns, a column's content box ends exactly on the
							// next one's border-l, so the highlight would cross the rule.
							className="lg:border-[#393939] lg:border-l lg:pr-8 lg:pl-12"
						>
							<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
								{col.label}
							</p>
							<ul className="mt-4">
								{col.entries.map((e) => (
									<li key={e.href}>
										<Link
											href={e.href}
											className="group -mx-4 block px-4 py-4 transition-colors hover:bg-[#292929]"
										>
											<span className="flex items-center justify-between gap-4">
												<span className="text-[15px] text-white">
													{e.title}
												</span>
												<ArrowRightIcon
													aria-hidden
													className="size-4 shrink-0 text-[#78a9ff] opacity-0 transition-opacity group-hover:opacity-100"
												/>
											</span>
											<span className="mt-1 block text-[#a8a8a8] text-[13px] leading-relaxed">
												{e.tagline}
											</span>
										</Link>
									</li>
								))}
							</ul>
						</div>
					))}
				</div>
			</div>
		</div>
	);
}
