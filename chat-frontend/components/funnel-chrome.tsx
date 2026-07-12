"use client";

// Marketing-register chrome for the app's public funnel pages (/start,
// /invite). A visitor lands here straight off the marketing site, so these
// pages keep ITS look — dark Carbon nav, ink leadspace, ibm.com-style footer —
// not the app shell's. The wizard lives in this app only because it needs the
// session cookie and the billing API on the same origin.
//
// This is a hand-kept replica of marketing-frontend/components/marketing/
// carbon.tsx + carbon-nav.tsx (separate deployment, so the code can't be
// shared). If the marketing chrome changes register, re-sync this file.
//
// Links back to the marketing site go through NEXT_PUBLIC_MARKETING_URL.
// While the marketing domain is unset (prod today), those links vanish and
// the chrome degrades to wordmark + Sign in + legal footer — never a dead link.

import { ArrowRightIcon } from "lucide-react";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { THEMES } from "@/components/carbon/primitives";
import { cn } from "@/lib/utils";

const plexSans = IBM_Plex_Sans({
	weight: ["300", "400", "600"],
	subsets: ["latin"],
	variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
	weight: ["400"],
	subsets: ["latin"],
	variable: "--font-plex-mono",
});

const MARKETING_URL = process.env.NEXT_PUBLIC_MARKETING_URL ?? "";

// Absolute link into the marketing site, or null while its domain is unset.
const mk = (path: string) => (MARKETING_URL ? `${MARKETING_URL}${path}` : null);

// ---------------------------------------------------------------------------
// Page shell — white Carbon theme vars + Plex, normal document scroll
// (funnel pages are long marketing-style pages, not viewport-clamped shells)
// ---------------------------------------------------------------------------

export function FunnelPage({ children }: { children: React.ReactNode }) {
	return (
		<div
			className={cn(
				"flex min-h-dvh flex-col bg-[var(--cds-bg)] text-[var(--cds-text)]",
				plexSans.variable,
				plexMono.variable,
			)}
			style={
				{
					...THEMES.white,
					fontFamily: "var(--font-plex-sans)",
					"--font-geist-mono": "var(--font-plex-mono)",
				} as React.CSSProperties
			}
		>
			<FunnelHeader />
			{children}
			<FunnelFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Header — the marketing site's Carbon UI-shell bar, minus its "Get started"
// CTA: the visitor is already inside the funnel it points at.
// ---------------------------------------------------------------------------

const NAV_LINKS = [
	{ label: "Products", href: mk("/products") },
	{ label: "Pricing", href: mk("/pricing") },
	{ label: "About", href: mk("/about") },
].filter((l): l is { label: string; href: string } => l.href !== null);

function Wordmark() {
	const home = mk("/");
	const inner = (
		<>
			<span className="font-semibold tracking-wide">Hudson</span>
			<span className="hidden text-[#c6c6c6] sm:inline">
				Legal Technologies
			</span>
		</>
	);
	const className = "flex items-baseline gap-1.5 whitespace-nowrap text-sm";
	return home ? (
		<a href={home} className={className}>
			{inner}
		</a>
	) : (
		<Link href="/" className={className}>
			{inner}
		</Link>
	);
}

function FunnelHeader() {
	return (
		<header className="sticky top-0 z-50 border-[#393939] border-b bg-[#161616] text-white">
			<div className="mx-auto flex h-12 w-full max-w-7xl items-stretch px-5 sm:px-8">
				<div className="flex items-center pr-6">
					<Wordmark />
				</div>

				<nav className="hidden items-stretch md:flex">
					{NAV_LINKS.map((l) => (
						<a
							key={l.label}
							href={l.href}
							className="flex items-center px-4 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
						>
							{l.label}
						</a>
					))}
				</nav>

				<div className="ms-auto flex items-stretch">
					<Link
						href="/"
						className="flex items-center px-4 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
					>
						Sign in
					</Link>
				</div>
			</div>
		</header>
	);
}

// ---------------------------------------------------------------------------
// Leadspace — dark ink band with the blue accent rule, same beat as the
// marketing PageHero (static: this app has no hero-rise/hero-draw keyframes)
// ---------------------------------------------------------------------------

export function FunnelHero({
	eyebrow,
	title,
	lede,
}: {
	eyebrow: string;
	title: React.ReactNode;
	lede?: React.ReactNode;
}) {
	return (
		<section className="bg-[#161616] text-white">
			<div className="mx-auto w-full max-w-7xl px-5 py-14 sm:px-8 lg:py-16">
				<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
					{eyebrow}
				</p>
				<h1 className="mt-6 max-w-3xl font-light text-3xl leading-[1.15] sm:text-4xl lg:text-[2.75rem]">
					{title}
				</h1>
				<div aria-hidden className="mt-8 h-0.5 w-24 bg-[#0f62fe]" />
				{lede && (
					<p className="mt-8 max-w-2xl text-[#c6c6c6] text-[15px] leading-relaxed sm:text-base">
						{lede}
					</p>
				)}
			</div>
		</section>
	);
}

// Inline text link with trailing arrow, marketing TextLink register.
export function FunnelTextLink({
	href,
	children,
}: {
	href: string;
	children: React.ReactNode;
}) {
	return (
		<a
			href={href}
			className="group inline-flex items-center gap-2 font-medium text-[#0f62fe] text-sm hover:underline"
		>
			{children}
			<ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
		</a>
	);
}

// ---------------------------------------------------------------------------
// Footer — ibm.com register, mirroring the marketing CarbonFooter. Marketing
// columns render only when the marketing origin is configured; the legal
// column is in-app and always present.
// ---------------------------------------------------------------------------

const FOOTER_COLS: {
	heading: string;
	links: { label: string; href: string }[];
}[] = [
	{
		heading: "Product",
		links: [
			{ label: "Hudson Corpus", href: mk("/products/corpus") },
			{ label: "Corpus MCP", href: mk("/products/mcp") },
			{ label: "Email assistant", href: mk("/products/email") },
		].filter((l): l is { label: string; href: string } => l.href !== null),
	},
	{
		heading: "Resources",
		links: [
			{ label: "Articles", href: mk("/articles") },
			{ label: "Pricing", href: mk("/pricing") },
		].filter((l): l is { label: string; href: string } => l.href !== null),
	},
	{
		heading: "Company",
		links: [
			{ label: "About", href: mk("/about") },
			{ label: "Consulting", href: mk("/consulting") },
			{ label: "Contact", href: mk("/contact") },
		].filter((l): l is { label: string; href: string } => l.href !== null),
	},
	{
		heading: "Legal",
		links: [
			{ label: "Terms of Service", href: "/terms" },
			{ label: "Privacy", href: "/privacy" },
		],
	},
].filter((col) => col.links.length > 0);

function FunnelFooter() {
	return (
		<footer className="border-[#393939] border-t bg-[#161616] text-white">
			<div className="mx-auto w-full max-w-7xl px-5 py-16 sm:px-8">
				<div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
					<div className="max-w-xs">
						<Wordmark />
						<p className="mt-4 text-[#a8a8a8] text-sm leading-relaxed">
							Grounded, citable legal research for practitioners.
						</p>
					</div>
					{FOOTER_COLS.map((col) => (
						<div key={col.heading}>
							<h4 className="font-semibold text-sm">{col.heading}</h4>
							<ul className="mt-4 space-y-3">
								{col.links.map((l) => (
									<li key={l.label}>
										<a
											href={l.href}
											className="text-[#c6c6c6] text-sm transition-colors hover:text-white hover:underline"
										>
											{l.label}
										</a>
									</li>
								))}
							</ul>
						</div>
					))}
				</div>

				<div className="mt-14 flex flex-col items-start justify-between gap-3 border-[#393939] border-t pt-6 text-[#6f6f6f] text-xs sm:flex-row sm:items-center">
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
