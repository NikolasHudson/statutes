// Carbon (IBM Design System) look for the marketing site — shared page
// wrapper, footer, and editorial primitives. Promoted from the /home-2
// experiment once the direction was approved; every marketing page except the
// legacy home ("/") builds on this module.
//
// Token cheatsheet (Carbon v11):
//   dark band        gray-100 #161616   hairline on dark   gray-80 #393939
//   secondary text   #c6c6c6 / #a8a8a8  primary action     Blue 60 #0f62fe
//   action hover     #0353e9            action active      Blue 80 #002d9c
//   link on dark     Blue 40 #78a9ff    tile hover (light) #e8e8e8
// Type: IBM Plex Sans — display/section headings LIGHT (300), body 400,
// small headings 600. Mono (Plex Mono) for eyebrows/spec labels. Everything
// square: no border radii, buttons 48px with label left + arrow trailing.

import { ArrowRightIcon } from "lucide-react";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { APP_HOST, APP_URL, PRIVACY_URL, TERMS_URL } from "@/lib/site";
import { cn } from "@/lib/utils";
import { CarbonNav, CarbonWordmark } from "./carbon-nav";
import {
	ABOUT_HREF,
	ARTICLES_HREF,
	CONSULTING_HREF,
	CONTACT_HREF,
	COVERAGE_EIGHTH_CIRCUIT_HREF,
	COVERAGE_IOWA_HREF,
	DATA_HREF,
	MCP_PRODUCT_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "./chrome";
import { Reveal } from "./reveal";

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

// Carbon gray-100 for the dark bands.
export const INK = "bg-[#161616]";

// Page shell: scoped Plex fonts plus the Carbon nav and footer. Every
// marketing page wraps its sections in this.
export function CarbonPage({ children }: { children: React.ReactNode }) {
	return (
		<div
			className={cn(
				"min-h-dvh bg-background text-foreground",
				plexSans.variable,
				plexMono.variable,
			)}
			style={
				{
					fontFamily: "var(--font-plex-sans)",
					// font-mono utilities resolve this var per-element, so pointing it
					// at Plex Mono re-skins every mono usage inside Carbon pages only.
					"--font-geist-mono": "var(--font-plex-mono)",
				} as React.CSSProperties
			}
		>
			<CarbonNav />
			{children}
			<CarbonFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Editorial primitives
// ---------------------------------------------------------------------------

export function Eyebrow({
	children,
	tone = "light",
}: {
	children: React.ReactNode;
	tone?: "light" | "dark";
}) {
	return (
		<p
			className={cn(
				"font-mono text-[11px] uppercase tracking-[0.22em]",
				tone === "dark" ? "text-[#a8a8a8]" : "text-muted-foreground",
			)}
		>
			{children}
		</p>
	);
}

// Section opener: hairline rule + numbered mono eyebrow, IBM-style. Headlines
// are Plex light per Carbon's expressive type set. On first scroll into view
// the rule draws in from the left and the text settles up (Reveal stamps
// data-shown; reduced-motion users see it static).
export function SectionHead({
	n,
	label,
	title,
	tone = "light",
}: {
	n?: string;
	label: string;
	title: string;
	tone?: "light" | "dark";
}) {
	return (
		<Reveal>
			<header>
				<div
					aria-hidden
					className={cn(
						"h-px w-full origin-left scale-x-0 transition-transform duration-700 ease-out group-data-[shown]/rv:scale-x-100 motion-reduce:scale-x-100 motion-reduce:transition-none",
						tone === "dark" ? "bg-[#393939]" : "bg-border",
					)}
				/>
				<div className="translate-y-3 pt-6 opacity-0 transition delay-150 duration-700 ease-out group-data-[shown]/rv:translate-y-0 group-data-[shown]/rv:opacity-100 motion-reduce:translate-y-0 motion-reduce:opacity-100 motion-reduce:transition-none">
					<Eyebrow tone={tone}>{n ? `${n} — ${label}` : label}</Eyebrow>
					<h2 className="mt-8 max-w-5xl font-light text-3xl sm:text-4xl lg:text-[2.75rem] lg:leading-[1.15]">
						{title}
					</h2>
				</div>
			</header>
		</Reveal>
	);
}

// Dark leadspace for subpages: eyebrow → light-weight H1 → blue accent rule →
// lede → actions. Keeps every page opening on the same beat as the home.
// Heroes sit above the fold, so the entrance is pure CSS keyframes
// (globals.css: hero-rise / hero-draw) that play as soon as styles load —
// no hydration dependency, unlike SectionHead's scroll-triggered reveal.
// `both` fill keeps elements hidden until their delay elapses.

// Shared enter animation; callers append their own [animation-delay:*] step.
const heroStep =
	"animate-[hero-rise_700ms_ease-out_both] motion-reduce:animate-none";

// `visual` is opt-in: without it the hero is untouched (every other page).
// With it, the visual paints the whole band as a background layer — the way
// the home hero does — and the copy is held to the left of it so the two never
// meet. Deliberately not a boxed second column: any box, however masked, shows
// its own edges against the ink. The visual is responsible for fading itself
// out where the copy is. It's decoration, so it stays off the narrow
// viewports, where a full-bleed layer would sit under the text.
export function PageHero({
	eyebrow,
	title,
	lede,
	actions,
	visual,
}: {
	eyebrow: string;
	title: React.ReactNode;
	lede?: React.ReactNode;
	actions?: React.ReactNode;
	visual?: React.ReactNode;
}) {
	const copy = (
		<div className={cn(visual && "lg:max-w-[58%]")}>
			<div className={heroStep}>
				<Eyebrow tone="dark">{eyebrow}</Eyebrow>
			</div>
			<h1
				className={cn(
					"mt-8 max-w-5xl font-light text-4xl leading-[1.1] [animation-delay:100ms] sm:text-5xl lg:text-[3.5rem]",
					heroStep,
				)}
			>
				{title}
			</h1>
			<div
				aria-hidden
				className="mt-10 h-0.5 w-24 origin-left animate-[hero-draw_500ms_ease-out_both] bg-[#0f62fe] [animation-delay:300ms] motion-reduce:animate-none"
			/>
			{lede && (
				<p
					className={cn(
						"mt-10 max-w-2xl text-[#c6c6c6] text-lg leading-relaxed [animation-delay:400ms]",
						heroStep,
					)}
				>
					{lede}
				</p>
			)}
			{actions && (
				<div
					className={cn(
						"mt-12 flex flex-col gap-3 [animation-delay:500ms] sm:flex-row sm:items-center",
						heroStep,
					)}
				>
					{actions}
				</div>
			)}
		</div>
	);
	return (
		<section className={cn("relative overflow-hidden text-white", INK)}>
			{visual && (
				<div
					aria-hidden
					className="hidden animate-[hero-fade_1200ms_ease-out_both] [animation-delay:500ms] motion-reduce:animate-none lg:block"
				>
					{visual}
				</div>
			)}
			<div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				{copy}
			</div>
		</section>
	);
}

// Carbon primary button: Blue 60, square, 48px, label left with the arrow at
// the trailing edge; hover Blue-60-hover, active Blue 80. Works for internal
// routes and absolute app URLs alike.
export function SolidLink({
	href,
	children,
}: {
	href: string;
	children: React.ReactNode;
}) {
	return (
		<Link
			href={href}
			className="inline-flex h-12 items-center justify-between gap-10 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
		>
			{children}
			<ArrowRightIcon className="size-4" />
		</Link>
	);
}

// Carbon tertiary button. On dark: white outline, fills white on hover. On
// light: Blue-60 outline, fills blue on hover.
export function HairlineLink({
	href,
	children,
	tone = "dark",
}: {
	href: string;
	children: React.ReactNode;
	tone?: "light" | "dark";
}) {
	return (
		<Link
			href={href}
			className={cn(
				"inline-flex h-12 items-center border px-4 text-sm transition-colors",
				tone === "dark"
					? "border-white text-white hover:bg-white hover:text-[#161616]"
					: "border-[#0f62fe] text-[#0f62fe] hover:bg-[#0f62fe] hover:text-white",
			)}
		>
			{children}
		</Link>
	);
}

// Inline text link with trailing arrow — Blue 60 on light, Blue 40 on dark.
export function TextLink({
	href,
	children,
	tone = "light",
}: {
	href: string;
	children: React.ReactNode;
	tone?: "light" | "dark";
}) {
	return (
		<Link
			href={href}
			className={cn(
				"group inline-flex items-center gap-2 font-medium text-sm hover:underline",
				tone === "dark" ? "text-[#78a9ff]" : "text-[#0f62fe]",
			)}
		>
			{children}
			<ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
		</Link>
	);
}

// Screenshot frame: hairline border + mono caption bar (replaces the rounded
// mac-dots Screenshot component on Carbon pages). `aspect` crops tall shots.
// `url` is the address bar of the shot: defaults to the app's host, since every
// capture so far is of the app — pass it explicitly for anything else.
export function Frame({
	src,
	alt,
	caption,
	url = APP_HOST,
	aspect,
	className,
}: {
	src: string;
	alt: string;
	caption: string;
	url?: string;
	aspect?: string;
	className?: string;
}) {
	return (
		<figure className={cn("border border-border bg-card", className)}>
			<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
				<span className="truncate">{caption}</span>
				<span className="shrink-0">{url}</span>
			</figcaption>
			{aspect ? (
				<div className="relative w-full" style={{ aspectRatio: aspect }}>
					{/* biome-ignore lint/performance/noImgElement: static marketing capture, no next/image needed */}
					<img
						src={src}
						alt={alt}
						className="absolute inset-0 size-full object-cover object-top"
					/>
				</div>
			) : (
				// biome-ignore lint/performance/noImgElement: static marketing capture, no next/image needed
				<img src={src} alt={alt} className="w-full" />
			)}
		</figure>
	);
}

// The Frame's sibling for the products whose surface is text, not pixels: same
// hairline border and mono caption bar, with an ink code block in place of the
// capture. Used by the MCP page's config blocks and the feature panels.
export function CodeFrame({
	caption,
	code,
	url = APP_HOST,
	className,
}: {
	caption: string;
	code: string;
	url?: string;
	className?: string;
}) {
	return (
		// min-w-0 so the pre's own horizontal scroll is what absorbs a long line —
		// as a flex/grid item the figure would otherwise be sized to the widest
		// line of code and push the layout past the viewport.
		<figure className={cn("min-w-0 border border-border bg-card", className)}>
			<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
				<span className="truncate">{caption}</span>
				<span className="shrink-0">{url}</span>
			</figcaption>
			<pre className="overflow-x-auto bg-[#161616] p-5 font-mono text-[13px] text-[#e0e0e0] leading-relaxed">
				<code>{code}</code>
			</pre>
		</figure>
	);
}

// ---------------------------------------------------------------------------
// Footer — ibm.com register: near-black, hairline top rule, gray link columns
// ---------------------------------------------------------------------------

const FOOTER_COLS: {
	heading: string;
	links: { label: string; href: string }[];
}[] = [
	{
		// One product. The former EDMSpro / email-assistant links left with the
		// product line-up (2026-08-30); MCP stays as the developer door into the
		// corpus, not a product of its own.
		heading: "Product",
		links: [
			{ label: "Hudson Corpus", href: PRODUCT_HREF },
			{ label: "MCP endpoint", href: MCP_PRODUCT_HREF },
			{ label: "Pricing", href: PRICING_HREF },
			{ label: "Open the app", href: APP_URL },
		],
	},
	{
		heading: "Research",
		links: [
			{ label: "Data briefs", href: DATA_HREF },
			{ label: "Coverage: Iowa", href: COVERAGE_IOWA_HREF },
			{ label: "Coverage: Eighth Circuit", href: COVERAGE_EIGHTH_CIRCUIT_HREF },
			{ label: "Articles", href: ARTICLES_HREF },
		],
	},
	{
		heading: "Company",
		links: [
			{ label: "About", href: ABOUT_HREF },
			{ label: "Consulting", href: CONSULTING_HREF },
			{ label: "Contact", href: CONTACT_HREF },
		],
	},
	{
		heading: "Legal",
		// Both live on the app origin and both resolve: /privacy redirects to
		// /terms#privacy, which is where the data practices actually are. There is
		// no standalone privacy policy yet - when one is written, PRIVACY_URL is
		// the single place this footer, and both lead forms, learn about it.
		links: [
			{ label: "Terms of Service", href: TERMS_URL },
			{ label: "Privacy", href: PRIVACY_URL },
		],
	},
];

export function CarbonFooter() {
	return (
		<footer
			data-print="hide"
			className="border-[#393939] border-t bg-[#161616] text-white"
		>
			<div className="mx-auto max-w-7xl px-5 py-16 sm:px-8">
				<div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
					<div className="max-w-xs">
						<CarbonWordmark />
						<p className="mt-4 text-[#a8a8a8] text-sm leading-relaxed">
							Affordable, accessible, intuitive research for the lawyers who
							actually practice. One product, one standard.
						</p>
					</div>
					{FOOTER_COLS.map((col) => (
						<div key={col.heading}>
							<h4 className="font-semibold text-sm">{col.heading}</h4>
							<ul className="mt-4 space-y-3">
								{col.links.map((l) => (
									<li key={l.label}>
										<Link
											href={l.href}
											className="text-[#c6c6c6] text-sm transition-colors hover:text-white hover:underline"
										>
											{l.label}
										</Link>
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
