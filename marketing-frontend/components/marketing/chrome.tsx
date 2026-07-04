"use client";

// Shared chrome for the Hudson Legal Technologies marketing site: sticky top nav,
// footer, wordmark, and the deep-navy background treatments. Internal links use
// real routes (/, /products/corpus, /consulting, ...); links INTO the app
// (Sign in / Get started) point at the app origin via APP_URL — it's a separate
// deployment, so those are cross-origin hard navigations by design.

import {
	ArrowRightIcon,
	BadgeCheckIcon,
	BookOpenIcon,
	ChevronDownIcon,
	type LucideIcon,
	MenuIcon,
	ScaleIcon,
	ScrollTextIcon,
	SearchIcon,
	SparklesIcon,
	TerminalIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { APP_URL, GET_STARTED_URL, MCP_URL, SIGN_IN_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const MARKETING_HOME = "/";
export const ARTICLES_HREF = "/articles";
export const ARTICLE_HREF = "/articles/why-legal-ai-invents-citations";
export const PRODUCT_HREF = "/products/corpus";
export const CONSULTING_HREF = "/consulting";
export const PRICING_HREF = "/pricing";
export const ABOUT_HREF = "/about";

// Deep-navy hero/CTA background, shared with the app's login panel so the
// marketing site and product read as one brand.
export const navyBackdrop = {
	backgroundImage: [
		"radial-gradient(110% 120% at 78% -10%, rgba(59,96,232,0.40) 0%, rgba(31,58,95,0) 55%)",
		"linear-gradient(160deg, #0b1c30 0%, #14304f 58%, #1d3c61 100%)",
	].join(", "),
} as const;

export const gridTexture = {
	backgroundImage: [
		"linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px)",
		"linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)",
	].join(", "),
	backgroundSize: "44px 44px",
} as const;

const NAV_LINKS = [
	{ label: "Consulting", href: CONSULTING_HREF },
	{ label: "Articles", href: ARTICLES_HREF },
	{ label: "Pricing", href: PRICING_HREF },
	{ label: "About", href: ABOUT_HREF },
];

// Capability links shown in the Products mega menu. Most point at the product
// page; MCP goes to the live endpoint.
const PRODUCT_LINKS: {
	icon: LucideIcon;
	label: string;
	sub: string;
	href: string;
}[] = [
	{
		icon: SparklesIcon,
		label: "Assistant",
		sub: "Grounded, cited answers",
		href: PRODUCT_HREF,
	},
	{
		icon: BookOpenIcon,
		label: "Browse the corpus",
		sub: "Code, rules & caselaw",
		href: PRODUCT_HREF,
	},
	{
		icon: ScrollTextIcon,
		label: "Read the source",
		sub: "Effective text + citation",
		href: PRODUCT_HREF,
	},
	{
		icon: SearchIcon,
		label: "Hybrid search",
		sub: "Keyword + semantic",
		href: PRODUCT_HREF,
	},
	{
		icon: BadgeCheckIcon,
		label: "Verified citations",
		sub: "Checked before you see them",
		href: PRODUCT_HREF,
	},
	{
		icon: TerminalIcon,
		label: "MCP & API",
		sub: "Use it in Claude Desktop",
		href: MCP_URL,
	},
];

// Products mega menu (desktop): hover/focus reveals a spacious panel showcasing
// the single flagship product — a navy feature tile on the left + a roomy
// capability grid on the right. Pure CSS group-hover / group-focus-within (no JS
// state); the panel's top is flush to the trigger (pt-3 bridge, no dead gap).
function ProductsMega() {
	return (
		<div className="group relative">
			<Link
				href={PRODUCT_HREF}
				aria-haspopup="true"
				className="inline-flex items-center gap-1 font-medium text-muted-foreground text-sm transition-colors hover:text-foreground"
			>
				Products
				<ChevronDownIcon className="size-3.5 transition-transform duration-200 group-hover:rotate-180" />
			</Link>

			<div className="invisible absolute left-0 top-full z-50 translate-y-1 pt-3 opacity-0 transition duration-200 group-hover:visible group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:visible group-focus-within:translate-y-0 group-focus-within:opacity-100">
				<div className="w-[48rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-border bg-popover shadow-xl">
					<div className="flex">
						{/* Featured navy tile */}
						<div
							className="flex w-[17rem] shrink-0 flex-col p-6 text-white"
							style={navyBackdrop}
						>
							<span className="flex size-11 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
								<ScaleIcon className="size-5.5" />
							</span>
							<div className="mt-5 flex items-center gap-2">
								<span className="font-semibold text-lg tracking-tight">
									Hudson Corpus
								</span>
								<span className="rounded-full bg-white/15 px-2 py-0.5 font-medium text-[10px] text-white/90 uppercase tracking-wider">
									Flagship
								</span>
							</div>
							<p className="mt-2 text-[13px] text-white/70 leading-relaxed">
								Grounded legal research with citations you can actually follow —
								Iowa code, rules & caselaw in one place.
							</p>
							<div className="mt-auto pt-6">
								<Link
									href={PRODUCT_HREF}
									className="inline-flex h-9 items-center gap-1.5 rounded-md bg-white px-3.5 font-medium text-[#11243d] text-sm transition-colors hover:bg-white/90"
								>
									Explore Hudson Corpus
									<ArrowRightIcon className="size-4" />
								</Link>
								<p className="mt-3 text-[12px] text-white/50">
									Now in beta · Iowa
								</p>
							</div>
						</div>

						{/* Capabilities */}
						<div className="flex-1 p-6">
							<p className="px-2 font-semibold text-[11px] text-muted-foreground uppercase tracking-[0.14em]">
								Capabilities
							</p>
							<div className="mt-2 grid grid-cols-2 gap-1">
								{PRODUCT_LINKS.map((c) => {
									const Icon = c.icon;
									return (
										<Link
											key={c.label}
											href={c.href}
											className="flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-accent"
										>
											<span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
												<Icon className="size-4.5" />
											</span>
											<span className="min-w-0">
												<span className="block font-medium text-foreground text-sm">
													{c.label}
												</span>
												<span className="mt-0.5 block text-[13px] text-muted-foreground leading-snug">
													{c.sub}
												</span>
											</span>
										</Link>
									);
								})}
							</div>
						</div>
					</div>

					{/* Footer */}
					<div className="flex items-center justify-between border-border border-t bg-secondary/30 px-6 py-3.5 text-[13px]">
						<span className="text-muted-foreground">
							Iowa today — more jurisdictions on the way.
						</span>
						<div className="flex items-center gap-5">
							<Link
								href={PRICING_HREF}
								className="font-medium text-muted-foreground transition-colors hover:text-foreground"
							>
								See pricing
							</Link>
							<a
								href={APP_URL}
								className="inline-flex items-center gap-1 font-medium text-primary"
							>
								Open the app
								<ArrowRightIcon className="size-3.5" />
							</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

export function Wordmark({ tone = "dark" }: { tone?: "dark" | "light" }) {
	return (
		<Link href={MARKETING_HOME} className="flex items-center gap-2.5">
			<span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
				<ScaleIcon className="size-4.5" />
			</span>
			<span
				className={cn(
					"font-extrabold text-lg tracking-[0.2em]",
					tone === "light" ? "text-white" : "text-foreground",
				)}
			>
				HUDSON
			</span>
			<span
				className={cn(
					"rounded-sm px-1.5 py-0.5 font-semibold text-[10px] uppercase tracking-wider",
					tone === "light"
						? "bg-white/15 text-white/90"
						: "bg-primary/10 text-primary",
				)}
			>
				beta
			</span>
		</Link>
	);
}

export function SiteNav() {
	const [menuOpen, setMenuOpen] = useState(false);

	return (
		<header className="sticky top-0 z-50 border-b border-border/70 bg-background/80 backdrop-blur-md">
			<div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
				<Wordmark />

				<nav className="hidden items-center gap-7 md:flex">
					<ProductsMega />
					{NAV_LINKS.map((l) => (
						<Link
							key={l.label}
							href={l.href}
							className="font-medium text-muted-foreground text-sm transition-colors hover:text-foreground"
						>
							{l.label}
						</Link>
					))}
				</nav>

				<div className="hidden items-center gap-2 md:flex">
					<Button asChild variant="ghost" size="sm">
						<a href={SIGN_IN_URL}>Sign in</a>
					</Button>
					<Button asChild size="sm">
						<a href={GET_STARTED_URL}>
							Get started
							<ArrowRightIcon />
						</a>
					</Button>
				</div>

				<button
					type="button"
					onClick={() => setMenuOpen(!menuOpen)}
					className="flex size-9 items-center justify-center rounded-md text-foreground hover:bg-accent md:hidden"
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
				<div className="border-border/70 border-t bg-background px-5 py-4 md:hidden">
					<nav className="flex flex-col gap-1">
						<Link
							href={PRODUCT_HREF}
							onClick={() => setMenuOpen(false)}
							className="rounded-md px-2 py-2 font-medium text-foreground text-sm hover:bg-accent"
						>
							Products
						</Link>
						{NAV_LINKS.map((l) => (
							<Link
								key={l.label}
								href={l.href}
								onClick={() => setMenuOpen(false)}
								className="rounded-md px-2 py-2 font-medium text-foreground text-sm hover:bg-accent"
							>
								{l.label}
							</Link>
						))}
					</nav>
					<div className="mt-3 flex flex-col gap-2">
						<Button asChild variant="outline" size="sm">
							<a href={SIGN_IN_URL}>Sign in</a>
						</Button>
						<Button asChild size="sm">
							<a href={GET_STARTED_URL}>Get started</a>
						</Button>
					</div>
				</div>
			)}
		</header>
	);
}

// Footer link groups. Internal marketing routes use <Link>; app-bound entries
// are absolute URLs (also fine through <Link>, rendered as plain anchors).
const FOOTER_COLS: {
	heading: string;
	links: { label: string; href: string }[];
}[] = [
	{
		heading: "Product",
		links: [
			{ label: "Hudson Corpus", href: PRODUCT_HREF },
			{ label: "Open the app", href: APP_URL },
			{ label: "MCP & API", href: MCP_URL },
		],
	},
	{
		heading: "Resources",
		links: [
			{ label: "Articles", href: ARTICLES_HREF },
			{ label: "Pricing", href: PRICING_HREF },
			{ label: "Documentation", href: APP_URL },
		],
	},
	{
		heading: "Company",
		links: [
			{ label: "About", href: ABOUT_HREF },
			{ label: "Consulting", href: CONSULTING_HREF },
			{ label: "Contact", href: `${CONSULTING_HREF}#contact` },
		],
	},
	{
		heading: "Legal",
		links: [
			{ label: "Terms of Service", href: `${APP_URL}/terms` },
			{ label: "Privacy", href: `${APP_URL}/privacy` },
		],
	},
];

export function SiteFooter() {
	return (
		<footer className="border-border border-t bg-card">
			<div className="mx-auto max-w-7xl px-5 py-14 sm:px-8">
				<div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
					<div className="max-w-xs">
						<Wordmark />
						<p className="mt-4 text-[13px] text-muted-foreground leading-relaxed">
							Grounded, citable legal research for practitioners. Built by
							Hudson Legal Technologies.
						</p>
					</div>
					{FOOTER_COLS.map((col) => (
						<div key={col.heading}>
							<h4 className="font-semibold text-[13px] text-foreground">
								{col.heading}
							</h4>
							<ul className="mt-3 space-y-2.5">
								{col.links.map((l) => (
									<li key={l.label}>
										<Link
											href={l.href}
											className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
										>
											{l.label}
										</Link>
									</li>
								))}
							</ul>
						</div>
					))}
				</div>

				<div className="mt-12 flex flex-col items-start justify-between gap-3 border-border border-t pt-6 text-[12px] text-muted-foreground sm:flex-row sm:items-center">
					<p>© 2026 Hudson Legal Technologies. All rights reserved.</p>
					<p>
						Sourced from legis.iowa.gov · Not a substitute for the official
						publication.
					</p>
				</div>
			</div>
		</footer>
	);
}
