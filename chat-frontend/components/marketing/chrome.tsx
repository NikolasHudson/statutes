"use client";

// Shared chrome for the Hudson Legal Tech marketing site mockup (everything
// under /home-mockup): the sticky top nav, the footer, the wordmark, and the
// deep-navy background treatments. Kept in one place so the landing page,
// article pages, and future product/consulting pages all read as one site.

import { ArrowRightIcon, MenuIcon, ScaleIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const MARKETING_HOME = "/home-mockup";
export const ARTICLE_HREF =
	"/home-mockup/articles/why-legal-ai-invents-citations";
export const PRODUCT_HREF = "/home-mockup/products/corpus";
export const CONSULTING_HREF = "/home-mockup/consulting";

// Deep-navy hero/CTA background, lifted from the login panel so the marketing
// site and the product read as one brand. A royal-blue radial glow sits behind
// the headline; a faint grid texture keeps the large dark fields from going flat.
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
	{ label: "Product", href: PRODUCT_HREF },
	{ label: "How it works", href: `${MARKETING_HOME}#how` },
	{ label: "Articles", href: `${MARKETING_HOME}#more` },
	{ label: "Consulting", href: CONSULTING_HREF },
	{ label: "Pricing", href: `${MARKETING_HOME}#pricing` },
];

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
						<Link href="/">Sign in</Link>
					</Button>
					<Button asChild size="sm">
						<Link href="/">
							Get started
							<ArrowRightIcon />
						</Link>
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
							<Link href="/">Sign in</Link>
						</Button>
						<Button asChild size="sm">
							<Link href="/">Get started</Link>
						</Button>
					</div>
				</div>
			)}
		</header>
	);
}

const FOOTER_COLS: {
	heading: string;
	links: { label: string; href: string }[];
}[] = [
	{
		heading: "Product",
		links: [
			{ label: "Assistant", href: "/" },
			{ label: "Browse corpus", href: "/" },
			{ label: "Search", href: "/" },
			{ label: "MCP & API", href: "/" },
		],
	},
	{
		heading: "Resources",
		links: [
			{ label: "Articles", href: `${MARKETING_HOME}#more` },
			{ label: "Documentation", href: "/" },
			{ label: "Changelog", href: "/" },
		],
	},
	{
		heading: "Company",
		links: [
			{ label: "About", href: "/" },
			{ label: "Consulting", href: CONSULTING_HREF },
			{ label: "Contact", href: `${CONSULTING_HREF}#contact` },
		],
	},
	{
		heading: "Legal",
		links: [
			{ label: "Terms of Service", href: "/terms" },
			{ label: "Privacy", href: "/privacy" },
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
							Hudson Legal Tech.
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
					<p>© 2026 Hudson Legal Tech. All rights reserved.</p>
					<p>
						Sourced from legis.iowa.gov · Not a substitute for the official
						publication.
					</p>
				</div>
			</div>
		</footer>
	);
}
