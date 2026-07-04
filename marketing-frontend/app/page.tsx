// Marketing home page for Hudson Legal Technologies (the public site root, "/").
//
// A corporate overview with a point of view — NOT a product pitch and NOT a
// repetition of the same tagline. Each section does a distinct job: hero (who we
// are + flagship product) → the short version (narrative w/ voice) → by the
// numbers (facts) → what we believe (opinions) → what we make (offerings) → CTA.
// Hudson Corpus is featured in the hero and routes to /products/corpus.

import {
	ArrowRightIcon,
	BookOpenIcon,
	BriefcaseIcon,
	CheckIcon,
	type LucideIcon,
	NewspaperIcon,
	ScaleIcon,
	ScrollTextIcon,
	SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import {
	ABOUT_HREF,
	ARTICLES_HREF,
	CONSULTING_HREF,
	gridTexture,
	navyBackdrop,
	PRICING_HREF,
	PRODUCT_HREF,
	SiteFooter,
	SiteNav,
} from "@/components/marketing/chrome";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function HomePage() {
	return (
		<div className="min-h-dvh bg-background text-foreground">
			<SiteNav />
			<Hero />
			<ShortVersion />
			<ByTheNumbers />
			<Beliefs />
			<WhatWeMake />
			<CtaBand />
			<SiteFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<section
			className="relative overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />

			<div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:py-28">
				<div className="max-w-xl">
					<span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-3 py-1 font-medium text-[12px] text-white/80 tracking-wide">
						<SparklesIcon className="size-3.5" />
						Hudson Legal Technologies
					</span>

					<h1 className="mt-6 font-bold text-4xl leading-[1.08] tracking-tight sm:text-5xl lg:text-[3.4rem]">
						Modern legal software,
						<br />
						<span className="text-white/95">finally.</span>
					</h1>

					<p className="mt-6 max-w-lg text-lg text-white/75 leading-relaxed">
						Legal work runs on tools that are clunky, overpriced, and a decade
						behind. We build the opposite — fast, trustworthy software priced
						for the whole profession. It starts with Hudson Corpus, our grounded
						research assistant.
					</p>

					<div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
						<Button
							asChild
							size="lg"
							className="bg-white text-[#11243d] hover:bg-white/90"
						>
							<Link href={PRODUCT_HREF}>
								Meet Hudson Corpus
								<ArrowRightIcon />
							</Link>
						</Button>
						<Button
							asChild
							size="lg"
							variant="outline"
							className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
						>
							<Link href={ABOUT_HREF}>Why we exist</Link>
						</Button>
					</div>

					<p className="mt-6 text-[13px] text-white/55">
						A small, independent team building legal software worth using.
					</p>
				</div>

				<FeaturedProduct />
			</div>
		</section>
	);
}

// Flagship product as a clickable card → product page. The preview is real DOM
// (not a scaled screenshot), so it stays crisp at any size.
function FeaturedProduct() {
	return (
		<div className="relative w-full max-w-md lg:justify-self-end">
			<div
				aria-hidden
				className="-inset-4 absolute rounded-3xl bg-primary/20 blur-2xl"
			/>
			<p className="relative mb-3 font-semibold text-[11px] text-white/60 uppercase tracking-[0.18em]">
				Our flagship product
			</p>
			<Link
				href={PRODUCT_HREF}
				className="group relative block overflow-hidden rounded-2xl border border-white/10 bg-white text-foreground shadow-2xl transition-transform hover:-translate-y-0.5"
			>
				<div className="flex items-center gap-2 border-border border-b bg-secondary/60 px-4 py-3">
					<span className="size-2.5 rounded-full bg-[#ff5f57]" />
					<span className="size-2.5 rounded-full bg-[#febc2e]" />
					<span className="size-2.5 rounded-full bg-[#28c840]" />
					<span className="ms-2 font-semibold text-[12px] text-foreground tracking-wide">
						Hudson Corpus
					</span>
				</div>

				<div className="space-y-4 p-5">
					<div className="flex justify-end">
						<div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[13px] text-primary-foreground leading-relaxed">
							Does Iowa recognize a private right of action under the Consumer
							Fraud Act?
						</div>
					</div>

					<div className="rounded-2xl rounded-bl-sm bg-secondary/70 px-4 py-3 text-[13px] leading-relaxed">
						<p>
							Yes. Iowa created a private cause of action by statute in 2009,
							codified at <CitationChip>Iowa Code § 714H.5</CitationChip>,
							allowing a consumer to recover actual damages.
						</p>
						<p className="mt-2.5">
							The older Consumer Fraud Act,{" "}
							<CitationChip>§ 714.16</CitationChip>, remains enforceable only by
							the Attorney General — see{" "}
							<CitationChip kind="case">State v. Vest</CitationChip>.
						</p>
					</div>

					<div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
						<span className="flex size-5 items-center justify-center rounded-full bg-emerald-500 text-white">
							<CheckIcon className="size-3" strokeWidth={3} />
						</span>
						<span className="font-medium text-[12px] text-emerald-800">
							3 citations verified against the effective text
						</span>
					</div>
				</div>

				<div className="flex items-center justify-between border-border border-t bg-secondary/40 px-4 py-3">
					<span className="font-medium text-primary text-sm">
						Explore Hudson Corpus
					</span>
					<ArrowRightIcon className="size-4 text-primary transition-transform group-hover:translate-x-0.5" />
				</div>
			</Link>
		</div>
	);
}

function CitationChip({
	children,
	kind = "statute",
}: {
	children: React.ReactNode;
	kind?: "statute" | "case";
}) {
	return (
		<span
			className={cn(
				"mx-0.5 inline-flex items-center gap-1 rounded border px-1.5 py-px font-medium text-[12px]",
				kind === "case"
					? "border-violet-200 bg-violet-50 text-violet-700"
					: "border-primary/20 bg-primary/10 text-primary",
			)}
		>
			{kind === "case" ? (
				<ScaleIcon className="size-3" />
			) : (
				<ScrollTextIcon className="size-3" />
			)}
			{children}
		</span>
	);
}

// ---------------------------------------------------------------------------
// The short version — narrative with a point of view
// ---------------------------------------------------------------------------

function ShortVersion() {
	return (
		<section className="scroll-mt-20">
			<div className="mx-auto max-w-3xl px-5 py-20 sm:px-8 lg:py-24">
				<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
					The short version
				</span>
				<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
					Legal tech has a bad reputation. We're out to fix it.
				</h2>
				<div className="mt-6 space-y-5 text-[17px] text-foreground/85 leading-[1.75]">
					<p>
						Hudson Legal Technologies builds software for legal work — the kind
						that's actually quick to use and easy to trust. Everything we make
						is grounded in real, citable sources, so you can check the answer
						instead of taking it on faith.
					</p>
					<p>
						And we price it for the whole profession. Powerful tools shouldn't
						be a luxury reserved for firms with their own IT floor — so ours are
						built for solos, small firms, and in-house teams too.
					</p>
				</div>

				<div className="my-11">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Our bet
					</span>
					<p className="mt-4 font-bold text-3xl leading-[1.2] tracking-tight sm:text-[2.5rem]">
						“Affordable” and “excellent” were never{" "}
						<span className="text-primary">actually opposites.</span>
					</p>
				</div>

				<p className="text-[17px] text-foreground/85 leading-[1.75]">
					We're small, independent, and we'd rather ship something real than
					promise something big. Hudson Corpus is the first product. It won't be
					the last.
				</p>
				<Link
					href={ABOUT_HREF}
					className="mt-6 inline-flex items-center gap-1.5 font-medium text-primary text-sm hover:underline"
				>
					Read our story
					<ArrowRightIcon className="size-4" />
				</Link>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// By the numbers
// ---------------------------------------------------------------------------

const FACTS: { value: string; label: string }[] = [
	{ value: "105,355", label: "Documents in the corpus" },
	{ value: "3", label: "Sources unified — code, rules & caselaw" },
	{ value: "496K+", label: "Passages, semantically searchable" },
	{ value: "100%", label: "Of answers tied to a citable source" },
];

function ByTheNumbers() {
	const [hero, ...rest] = FACTS;
	return (
		<section className="bg-card">
			<div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
				<div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
					<div>
						<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
							By the numbers
						</span>
						<div className="mt-4 font-bold text-[4.5rem] text-foreground leading-[0.95] tracking-tight tabular-nums sm:text-[6rem]">
							{hero.value}
						</div>
						<p className="mt-5 max-w-md text-lg text-foreground/80 leading-relaxed">
							Documents in one searchable corpus — Iowa Code, Court Rules, and
							caselaw, finally unified.
						</p>
						<p className="mt-7 text-[13px] text-muted-foreground">
							Iowa today — more jurisdictions next.{" "}
							<Link
								href={PRICING_HREF}
								className="font-medium text-primary underline-offset-2 hover:underline"
							>
								See pricing →
							</Link>
						</p>
					</div>

					<dl className="border-border border-t">
						{rest.map((f) => (
							<div
								key={f.label}
								className="flex items-baseline justify-between gap-6 border-border border-b py-5"
							>
								<dt className="font-bold text-4xl text-foreground tracking-tight tabular-nums">
									{f.value}
								</dt>
								<dd className="max-w-[55%] text-right text-[14px] text-muted-foreground leading-snug">
									{f.label}
								</dd>
							</div>
						))}
					</dl>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// What we believe — a few strong opinions
// ---------------------------------------------------------------------------

const BELIEFS: { n: string; claim: string; body: string }[] = [
	{
		n: "01",
		claim: "If you can't check it, it isn't an answer.",
		body: "Every answer traces back to a real, citable source. When the source isn't there, our software says so instead of guessing.",
	},
	{
		n: "02",
		claim: "Good software shouldn't cost more than the associate using it.",
		body: "We price for solos, small firms, and in-house teams — not just the firms with an IT floor and a procurement department.",
	},
	{
		n: "03",
		claim: "Nobody should need IT to open an app.",
		body: "Fast, modern, and obvious. If a tool needs a training manual, we designed it wrong.",
	},
	{
		n: "04",
		claim: "Show, don't pitch.",
		body: "We build and ship our own products. Our consulting comes from doing the work, not drawing the diagram.",
	},
];

function Beliefs() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						What we believe
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						A few strong opinions
					</h2>
				</div>

				<div className="mt-12 grid gap-x-10 gap-y-10 sm:grid-cols-2">
					{BELIEFS.map((b) => (
						<div key={b.n} className="flex gap-5">
							<span className="font-bold text-2xl text-primary/30 tabular-nums">
								{b.n}
							</span>
							<div>
								<h3 className="font-semibold text-xl leading-snug tracking-tight">
									{b.claim}
								</h3>
								<p className="mt-2 text-[15px] text-muted-foreground leading-relaxed">
									{b.body}
								</p>
							</div>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// What we make — products, consulting, writing
// ---------------------------------------------------------------------------

type Offering = {
	icon: LucideIcon;
	tag: string;
	title: string;
	body: string;
	cta: string;
	href: string;
	badge?: string;
};

const OFFERINGS: Offering[] = [
	{
		icon: BookOpenIcon,
		tag: "Products",
		title: "Hudson Corpus",
		body: "Grounded legal research with citations you can actually follow. The first of several practice tools — Iowa today, more on the way.",
		cta: "Explore Corpus",
		href: PRODUCT_HREF,
		badge: "Flagship",
	},
	{
		icon: BriefcaseIcon,
		tag: "Consulting",
		title: "Technology consulting",
		body: "Need it built? We help teams ship real software — strategy, custom builds, data, and AI — with the same bar we hold ourselves to.",
		cta: "Talk to us",
		href: CONSULTING_HREF,
	},
	{
		icon: NewspaperIcon,
		tag: "Writing",
		title: "Articles & insights",
		body: "We write down what we learn — on grounding, retrieval, and building legal software the profession can trust. Opinions included.",
		cta: "Read the blog",
		href: ARTICLES_HREF,
	},
];

function WhatWeMake() {
	return (
		<section id="more" className="scroll-mt-20 bg-card">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						What we make
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						Products first — and the help to build them
					</h2>
				</div>

				<div className="mt-12 grid gap-6 md:grid-cols-3">
					{OFFERINGS.map((c) => {
						const Icon = c.icon;
						return (
							<Link
								key={c.tag}
								href={c.href}
								className="group flex flex-col rounded-2xl border border-border bg-card p-7 shadow-sm transition-shadow hover:shadow-md"
							>
								<div className="flex items-center justify-between">
									<div className="flex size-11 items-center justify-center rounded-xl bg-secondary text-foreground">
										<Icon className="size-5.5" />
									</div>
									{c.badge && (
										<span className="rounded-full bg-emerald-100 px-2.5 py-1 font-medium text-[11px] text-emerald-700 uppercase tracking-wider">
											{c.badge}
										</span>
									)}
								</div>
								<p className="mt-5 font-semibold text-[12px] text-primary uppercase tracking-[0.14em]">
									{c.tag}
								</p>
								<h3 className="mt-1.5 font-semibold text-xl tracking-tight">
									{c.title}
								</h3>
								<p className="mt-2 flex-1 text-[14px] text-muted-foreground leading-relaxed">
									{c.body}
								</p>
								<span className="mt-5 inline-flex items-center gap-1.5 font-medium text-primary text-sm transition-transform group-hover:translate-x-0.5">
									{c.cta}
									<ArrowRightIcon className="size-4" />
								</span>
							</Link>
						);
					})}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// CTA band
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section
			className="relative overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />
			<div className="relative mx-auto max-w-4xl px-5 py-20 text-center sm:px-8 lg:py-24">
				<div className="mb-7 inline-block bg-black px-5 py-2.5 text-left">
					<div className="font-bold text-lg leading-tight tracking-[0.04em] text-white uppercase">
						Better tools.
						<br />
						Fair price.
					</div>
				</div>
				<h2 className="font-bold text-3xl tracking-tight sm:text-4xl">
					See it on a real question
				</h2>
				<p className="mx-auto mt-4 max-w-xl text-lg text-white/75 leading-relaxed">
					Hudson Corpus is live in beta. Ask a real question, follow a citation
					to its source, and tell us what's missing.
				</p>
				<div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
					<Button
						asChild
						size="lg"
						className="bg-white text-[#11243d] hover:bg-white/90"
					>
						<Link href={PRODUCT_HREF}>
							Explore Hudson Corpus
							<ArrowRightIcon />
						</Link>
					</Button>
					<Button
						asChild
						size="lg"
						variant="outline"
						className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
					>
						<Link href={CONSULTING_HREF}>Talk to us</Link>
					</Button>
				</div>
			</div>
		</section>
	);
}
