// The product-page shell, laid out the way ibm.com/products/* is.
//
// Every product page is the same sequence of moves, and this module is that
// sequence: breadcrumb → leadspace (product NAME as the headline, the promise
// as the subhead, the visual to the right) → a sticky in-page nav that keeps
// the section anchors and the primary action on screen → Overview → Features →
// Use cases → Resources → Pricing → "Take the next step" → the rest of the
// family. The pages themselves supply copy and data; none of them re-implement
// the frame.
//
// It stays in the Carbon register the rest of the site uses (carbon.tsx):
// gray-100 bands, hairline rules, Plex-light headlines, square Blue-60
// actions. What changes here versus the old product pages is the LAYOUT —
// numbered editorial sections stacked one under the next become a navigable
// product page with a persistent CTA.

import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";
import {
	Eyebrow,
	HairlineLink,
	INK,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import {
	MARKETING_HOME,
	PRODUCTS_INDEX_HREF,
} from "@/components/marketing/chrome";
import {
	BILLING_LIVE,
	COMPARE_PLANS_HREF,
	PLANS,
	PRICING_NOTE,
} from "@/lib/pricing";
import { cn } from "@/lib/utils";

// Shared hero entrance (globals.css keyframes), same as PageHero: pure CSS so
// it plays on paint rather than waiting for hydration.
const heroStep =
	"animate-[hero-rise_700ms_ease-out_both] motion-reduce:animate-none";

// ---------------------------------------------------------------------------
// Leadspace
// ---------------------------------------------------------------------------

export function ProductBreadcrumb({ product }: { product: string }) {
	const sep = (
		<ChevronRightIcon aria-hidden className="size-3.5 text-[#6f6f6f]" />
	);
	return (
		<nav aria-label="Breadcrumb" className={cn("text-[13px]", heroStep)}>
			<ol className="flex flex-wrap items-center gap-2 text-[#a8a8a8]">
				<li>
					<Link
						href={MARKETING_HOME}
						className="hover:text-white hover:underline"
					>
						Home
					</Link>
				</li>
				<li aria-hidden>{sep}</li>
				<li>
					<Link
						href={PRODUCTS_INDEX_HREF}
						className="hover:text-white hover:underline"
					>
						Products
					</Link>
				</li>
				<li aria-hidden>{sep}</li>
				<li className="text-white" aria-current="page">
					{product}
				</li>
			</ol>
		</nav>
	);
}

// The ibm.com product leadspace: the H1 is the product's NAME, the promise is
// the subhead under it, and the supporting paragraph carries the substance.
// `visual` paints the band's right side — either a full-bleed ambient layer
// (the way PageHero takes one) or a framed capture, so it is positioned by the
// caller inside the right column.
export function ProductLeadspace({
	product,
	tagline,
	lede,
	actions,
	visual,
	backdrop,
}: {
	product: string;
	tagline: React.ReactNode;
	lede?: React.ReactNode;
	actions?: React.ReactNode;
	/** Right-column content — a Frame or CodeFrame. */
	visual?: React.ReactNode;
	/** Full-bleed ambient layer behind the band (canvas heroes). */
	backdrop?: React.ReactNode;
}) {
	return (
		<section className={cn("relative overflow-hidden text-white", INK)}>
			{backdrop && (
				<div
					aria-hidden
					className="hidden animate-[hero-fade_1200ms_ease-out_both] [animation-delay:500ms] motion-reduce:animate-none lg:block"
				>
					{backdrop}
				</div>
			)}
			<div className="relative mx-auto max-w-7xl px-5 pt-8 pb-20 sm:px-8 lg:pb-24">
				<ProductBreadcrumb product={product} />

				<div
					className={cn(
						"mt-10 grid gap-12 lg:mt-12 lg:gap-12",
						visual ? "lg:grid-cols-12 lg:items-center" : "",
					)}
				>
					{/* min-w-0 on both columns: a grid item's automatic minimum is its
					    content, so a code block or a wide capture would otherwise
					    stretch the whole leadspace past a phone's viewport instead of
					    scrolling inside its own frame. */}
					<div
						className={cn(
							"min-w-0",
							visual ? "lg:col-span-6 xl:col-span-5" : "",
						)}
					>
						<h1
							className={cn(
								"font-light text-4xl leading-[1.1] [animation-delay:100ms] sm:text-5xl lg:text-[3.5rem]",
								heroStep,
							)}
						>
							{product}
						</h1>
						<div
							aria-hidden
							className="mt-8 h-0.5 w-24 origin-left animate-[hero-draw_500ms_ease-out_both] bg-[#0f62fe] [animation-delay:300ms] motion-reduce:animate-none"
						/>
						<p
							className={cn(
								"mt-8 max-w-2xl font-light text-2xl leading-snug [animation-delay:350ms] sm:text-[1.75rem]",
								heroStep,
							)}
						>
							{tagline}
						</p>
						{lede && (
							<p
								className={cn(
									"mt-6 max-w-2xl text-[#c6c6c6] text-[17px] leading-relaxed [animation-delay:450ms]",
									heroStep,
								)}
							>
								{lede}
							</p>
						)}
						{actions && (
							<div
								className={cn(
									"mt-10 flex flex-col gap-3 [animation-delay:550ms] sm:flex-row sm:items-center",
									heroStep,
								)}
							>
								{actions}
							</div>
						)}
					</div>

					{visual && (
						<div
							className={cn(
								"min-w-0 lg:col-span-6 xl:col-span-7",
								"animate-[hero-fade_900ms_ease-out_both] [animation-delay:650ms] motion-reduce:animate-none",
							)}
						>
							{visual}
						</div>
					)}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

// One band. `label` is the subnav's word for this section ("Overview",
// "Features"); IBM writes the label small and the section's actual claim big
// underneath, with the "view everything" link on the intro's baseline.
export function ProductSection({
	id,
	label,
	title,
	intro,
	link,
	tone = "light",
	children,
}: {
	id: string;
	label: string;
	title: string;
	intro?: React.ReactNode;
	link?: { label: string; href: string };
	/**
	 * "light" is gray-10, "layer" is the white card layer — alternate them so
	 * two adjacent light bands still read as two bands, "dark" is gray-100.
	 */
	tone?: "light" | "layer" | "dark";
	children?: React.ReactNode;
}) {
	const dark = tone === "dark";
	return (
		<section
			id={id}
			// 96px of sticky chrome (48px masthead + 48px product nav) plus air.
			className={cn(
				"scroll-mt-24",
				dark
					? cn("text-white", INK)
					: tone === "layer"
						? "bg-card"
						: "bg-background",
			)}
		>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					label={label}
					title={title}
					tone={dark ? "dark" : "light"}
				/>
				{(intro || link) && (
					<div className="mt-10 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
						{intro && (
							<p
								className={cn(
									"max-w-2xl text-[17px] leading-[1.75]",
									dark ? "text-[#c6c6c6]" : "text-foreground/80",
								)}
							>
								{intro}
							</p>
						)}
						{link && (
							<div className="shrink-0 lg:pb-1">
								<TextLink href={link.href} tone={dark ? "dark" : "light"}>
									{link.label}
								</TextLink>
							</div>
						)}
					</div>
				)}
				{children}
			</div>
		</section>
	);
}

// The by-the-numbers rule under an overview. Every figure is passed in already
// derived from the live corpus — nothing on these pages states a count that a
// human typed.
export function StatRow({
	items,
	tone = "light",
}: {
	items: { value: string; label: string; sub?: string }[];
	tone?: "light" | "dark";
}) {
	const dark = tone === "dark";
	if (items.length === 0) return null;
	return (
		<dl className="mt-14 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
			{items.map((s) => (
				<div
					key={s.label}
					className={cn(
						"border-t pt-5",
						dark ? "border-[#393939]" : "border-border",
					)}
				>
					<dt
						className={cn(
							"font-mono text-[11px] uppercase tracking-[0.22em]",
							dark ? "text-[#a8a8a8]" : "text-muted-foreground",
						)}
					>
						{s.label}
					</dt>
					<dd className="mt-4 font-light text-3xl tabular-nums lg:text-4xl">
						{s.value}
					</dd>
					{s.sub && (
						<dd
							className={cn(
								"mt-2 text-[13px]",
								dark ? "text-[#a8a8a8]" : "text-muted-foreground",
							)}
						>
							{s.sub}
						</dd>
					)}
				</div>
			))}
		</dl>
	);
}

// ---------------------------------------------------------------------------
// Use cases — IBM's audience tiles: who it is for, and what they do with it
// ---------------------------------------------------------------------------

export type UseCase = { audience: string; title: string; body: string };

export function UseCaseGrid({
	items,
	tone = "dark",
}: {
	items: UseCase[];
	tone?: "light" | "dark";
}) {
	const dark = tone === "dark";
	return (
		<div
			className={cn(
				"mt-14 grid gap-px sm:grid-cols-2 lg:grid-cols-3",
				dark
					? "border border-[#393939] bg-[#393939]"
					: "border border-border bg-border",
			)}
		>
			{items.map((u) => (
				<div
					key={u.title}
					className={cn("p-8", dark ? "bg-[#161616]" : "bg-card")}
				>
					<Eyebrow tone={tone}>{u.audience}</Eyebrow>
					<h3 className="mt-5 font-light text-xl leading-snug">{u.title}</h3>
					<p
						className={cn(
							"mt-3 text-[14px] leading-relaxed",
							dark ? "text-[#c6c6c6]" : "text-muted-foreground",
						)}
					>
						{u.body}
					</p>
				</div>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Resources — type label, title, one line, and the link that opens it
// ---------------------------------------------------------------------------

export type Resource = {
	type: string;
	title: string;
	body: string;
	href: string;
	cta: string;
};

export function ResourceCards({ items }: { items: Resource[] }) {
	return (
		<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
			{items.map((r) => (
				<Link
					key={r.href + r.title}
					href={r.href}
					className="group flex min-h-[260px] flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8]"
				>
					<Eyebrow>{r.type}</Eyebrow>
					<h3 className="mt-5 font-light text-xl leading-snug">{r.title}</h3>
					<p className="mt-3 text-[13.5px] text-muted-foreground leading-relaxed">
						{r.body}
					</p>
					<span className="mt-auto flex items-center justify-between gap-4 pt-8 font-medium text-[#0f62fe] text-sm">
						{r.cta}
						<span
							aria-hidden
							className="transition-transform group-hover:translate-x-0.5"
						>
							→
						</span>
					</span>
				</Link>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Pricing — the plan summary that sits on the product page itself
// ---------------------------------------------------------------------------

// `included` is the one line that says what THIS product is within the plan —
// the corpus page and the MCP page share the same $49, but not the same reason
// for quoting it.
export function PlanBand({ included }: { included?: string }) {
	return (
		<>
			{included && (
				<p className="mt-14 max-w-2xl border-border border-t pt-5 text-[15px] text-foreground/85 leading-relaxed">
					{included}
				</p>
			)}
			<div
				className={cn(
					"grid divide-y divide-border border border-border lg:grid-cols-3 lg:divide-x lg:divide-y-0",
					included ? "mt-8" : "mt-14",
				)}
			>
				{PLANS.map((p) => (
					<div
						key={p.key}
						className={cn(
							"flex flex-col bg-card p-8",
							p.key === "solo" && "border-t-[3px] border-t-[#0f62fe]",
						)}
					>
						<Eyebrow>{p.badge}</Eyebrow>
						<h3 className="mt-5 font-light text-2xl">{p.name}</h3>
						<div className="mt-4 flex items-baseline gap-1.5">
							<span className="font-light text-4xl tabular-nums">
								{p.price}
							</span>
							{p.cadence && (
								<span className="text-muted-foreground text-sm">
									{p.cadence}
								</span>
							)}
						</div>
						<p className="mt-1.5 min-h-5 text-[13px] text-muted-foreground tabular-nums">
							{p.subPrice ?? ""}
						</p>
						<p className="mt-4 text-muted-foreground text-sm leading-relaxed">
							{p.tagline}
						</p>
						<div className="mt-auto pt-10">
							<TextLink href={p.cta.href}>{p.cta.label}</TextLink>
						</div>
					</div>
				))}
			</div>
			<div className="mt-8 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
				<p className="max-w-2xl text-[13px] text-muted-foreground">
					{PRICING_NOTE}
				</p>
				<div className="shrink-0">
					<HairlineLink href={COMPARE_PLANS_HREF} tone="light">
						{BILLING_LIVE ? "Compare plans" : "See full pricing"}
					</HairlineLink>
				</div>
			</div>
		</>
	);
}

// ---------------------------------------------------------------------------
// Take the next step — IBM's closer: the action, then the quieter doors
// ---------------------------------------------------------------------------

export function NextStep({
	title,
	body,
	actions,
	explore,
}: {
	title: string;
	body: string;
	actions: React.ReactNode;
	/** The "Explore more" row: quieter destinations, not calls to action. */
	explore?: { label: string; href: string }[];
}) {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">{title}</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							{body}
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						{actions}
					</div>
				</div>

				{explore && explore.length > 0 && (
					<div className="mt-14 border-[#393939] border-t pt-6">
						<Eyebrow tone="dark">Explore more</Eyebrow>
						<div className="mt-4 flex flex-wrap gap-x-10 gap-y-3">
							{explore.map((l) => (
								<Link
									key={l.href + l.label}
									href={l.href}
									className="text-[#c6c6c6] text-sm transition-colors hover:text-white hover:underline"
								>
									{l.label}
								</Link>
							))}
						</div>
					</div>
				)}
			</div>
		</section>
	);
}

// Re-exported so a product page imports its actions from one place.
export { HairlineLink, SolidLink };
