"use client";

// Marketing / public-facing home page mockup for Hudson Legal Tech.
//
// Self-contained on its own route (/home-mockup) so it can be shown and iterated
// on without touching the app. The whole /home-mockup tree is registered as
// public in auth-gate so it renders for signed-out visitors with no flash.
//
// This is the *company* landing — it leads with the flagship grounded-citable
// legal-AI product, but the structure (nav + "More from Hudson" + footer) is
// already scaffolded for the next things on the roadmap: Articles/Insights,
// additional Products, and Consultation services. Shared chrome (nav, footer,
// wordmark, navy backdrops) lives in components/marketing/chrome.

import {
	ArrowRightIcon,
	BadgeCheckIcon,
	BookOpenIcon,
	BriefcaseIcon,
	CheckIcon,
	GitCompareArrowsIcon,
	LayersIcon,
	type LucideIcon,
	NewspaperIcon,
	ScaleIcon,
	ScrollTextIcon,
	SearchIcon,
	ShieldCheckIcon,
	SparklesIcon,
	TerminalIcon,
} from "lucide-react";
import Link from "next/link";
import {
	ARTICLE_HREF,
	CONSULTING_HREF,
	gridTexture,
	navyBackdrop,
	PRODUCT_HREF,
	SiteFooter,
	SiteNav,
} from "@/components/marketing/chrome";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function HomeMockup() {
	return (
		<div className="min-h-dvh bg-background text-foreground">
			<SiteNav />
			<Hero />
			<StatBand />
			<Features />
			<HowItWorks />
			<MoreFromHudson />
			<CtaBand />
			<SiteFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Hero — navy field, headline + CTAs, floating product preview
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<section
			className="relative overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />
			{/* Soft fade into the page below so the navy doesn't end on a hard line. */}
			<div
				aria-hidden
				className="absolute inset-x-0 bottom-0 h-24"
				style={{
					backgroundImage:
						"linear-gradient(to bottom, rgba(11,28,48,0), var(--color-background))",
				}}
			/>

			<div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:py-28">
				{/* Left — message */}
				<div className="max-w-xl">
					<span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-3 py-1 font-medium text-[12px] text-white/80 tracking-wide">
						<SparklesIcon className="size-3.5" />
						Grounded legal AI · Iowa Code, Court Rules & Caselaw
					</span>

					<h1 className="mt-6 font-bold text-4xl leading-[1.08] tracking-tight sm:text-5xl lg:text-[3.4rem]">
						The answer,
						<br />
						<span className="text-white/95">with the citation.</span>
					</h1>

					<p className="mt-6 max-w-lg text-lg text-white/75 leading-relaxed">
						Hudson is a research assistant for practitioners who need the
						effective text — not a guess. Every answer is traced to the
						currently-in-force statute, rule, or decision, with a real citation
						you can hand to a partner or a court.
					</p>

					<div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
						<Button
							asChild
							size="lg"
							className="bg-white text-[#11243d] hover:bg-white/90"
						>
							<Link href="/">
								Start researching
								<ArrowRightIcon />
							</Link>
						</Button>
						<Button
							asChild
							size="lg"
							variant="outline"
							className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
						>
							<a href="#how">See how it works</a>
						</Button>
					</div>

					<p className="mt-6 text-[13px] text-white/55">
						No credit card required · Free during beta · Available in your
						browser and in Claude Desktop via MCP
					</p>
				</div>

				{/* Right — product preview */}
				<HeroPreview />
			</div>
		</section>
	);
}

// A faux assistant exchange that shows the actual product differentiators:
// inline citations and the deterministic citation-verification step.
function HeroPreview() {
	return (
		<div className="relative lg:justify-self-end">
			<div
				aria-hidden
				className="-inset-4 absolute rounded-3xl bg-primary/20 blur-2xl"
			/>
			<div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-white text-foreground shadow-2xl">
				{/* window chrome */}
				<div className="flex items-center gap-2 border-border border-b bg-secondary/60 px-4 py-3">
					<span className="size-2.5 rounded-full bg-[#ff5f57]" />
					<span className="size-2.5 rounded-full bg-[#febc2e]" />
					<span className="size-2.5 rounded-full bg-[#28c840]" />
					<span className="ms-2 font-medium text-[12px] text-muted-foreground tracking-wide">
						HUDSON · Assistant
					</span>
				</div>

				<div className="space-y-4 p-5">
					{/* user */}
					<div className="flex justify-end">
						<div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[13px] text-primary-foreground leading-relaxed">
							Does Iowa recognize a private right of action under the Consumer
							Fraud Act?
						</div>
					</div>

					{/* assistant */}
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

					{/* verification step */}
					<div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
						<span className="flex size-5 items-center justify-center rounded-full bg-emerald-500 text-white">
							<CheckIcon className="size-3" strokeWidth={3} />
						</span>
						<span className="font-medium text-[12px] text-emerald-800">
							3 citations verified against the effective text
						</span>
					</div>
				</div>
			</div>
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
// Credibility band — corpus facts in lieu of (not-yet-real) customer logos
// ---------------------------------------------------------------------------

const STATS: { value: string; label: string }[] = [
	{ value: "3", label: "Sources unified — Code, Rules & Caselaw" },
	{ value: "100%", label: "Answers traced to effective text" },
	{ value: "496K+", label: "Embedded passages, semantically searchable" },
	{ value: "1 click", label: "From answer to the official source" },
];

function StatBand() {
	return (
		<section className="border-border border-y bg-card">
			<div className="mx-auto max-w-7xl px-5 py-10 sm:px-8">
				<p className="text-center font-medium text-[12px] text-muted-foreground uppercase tracking-[0.18em]">
					Built on the official Iowa Code, Court Rules, and a century of Iowa
					caselaw
				</p>
				<dl className="mt-8 grid grid-cols-2 gap-8 lg:grid-cols-4">
					{STATS.map((s) => (
						<div key={s.label} className="text-center">
							<dt className="font-bold text-3xl text-primary tracking-tight">
								{s.value}
							</dt>
							<dd className="mt-1.5 text-[13px] text-muted-foreground leading-snug">
								{s.label}
							</dd>
						</div>
					))}
				</dl>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Features — the "why Hudson" grid
// ---------------------------------------------------------------------------

type Feature = { icon: LucideIcon; title: string; body: string };

const FEATURES: Feature[] = [
	{
		icon: ShieldCheckIcon,
		title: "Grounded, never guessed",
		body: "Retrieval-augmented from the currently effective, human-reviewed text. If the corpus doesn't support it, Hudson says so.",
	},
	{
		icon: ScrollTextIcon,
		title: "Real citations, every time",
		body: "Citation, effective date, and enacting session law on every provision — and inline links straight to the official source.",
	},
	{
		icon: BadgeCheckIcon,
		title: "Verified before you see it",
		body: "A deterministic check confirms each quote and citation against the source text before the answer ever reaches you.",
	},
	{
		icon: LayersIcon,
		title: "Search that actually finds it",
		body: "Full-text, trigram, and vector embeddings fused with Reciprocal Rank Fusion — keyword precision with semantic recall.",
	},
	{
		icon: GitCompareArrowsIcon,
		title: "Currency you can trust",
		body: "Track amendments and editions over time, and surface when a provision or holding has been superseded or overruled.",
	},
	{
		icon: TerminalIcon,
		title: "In your tools, not a silo",
		body: "Use it in the browser, or wire the corpus into Claude Desktop and your own integrations over a production MCP endpoint.",
	},
];

function Features() {
	return (
		<section id="product" className="scroll-mt-20">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Why Hudson
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						Research you can put your name on
					</h2>
					<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
						General chatbots hallucinate citations. Hudson is built around the
						one thing legal work can't compromise on: every claim tied to text
						you can verify.
					</p>
				</div>

				<div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{FEATURES.map((f) => {
						const Icon = f.icon;
						return (
							<div
								key={f.title}
								className="group bg-card p-7 transition-colors hover:bg-secondary/40"
							>
								<div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
									<Icon className="size-5.5" />
								</div>
								<h3 className="mt-5 font-semibold text-lg tracking-tight">
									{f.title}
								</h3>
								<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
									{f.body}
								</p>
							</div>
						);
					})}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// How it works — three steps
// ---------------------------------------------------------------------------

const STEPS: { icon: LucideIcon; step: string; title: string; body: string }[] =
	[
		{
			icon: SearchIcon,
			step: "01",
			title: "Ask in plain language",
			body: "Pose the question the way you'd ask a colleague — or paste a citation and ask what's changed.",
		},
		{
			icon: LayersIcon,
			step: "02",
			title: "Hudson retrieves & grounds",
			body: "Hybrid search pulls the on-point statutes, rules, and decisions and assembles the effective text.",
		},
		{
			icon: BadgeCheckIcon,
			step: "03",
			title: "You get a verified answer",
			body: "A cited, source-linked answer — with each citation checked against the text before it reaches you.",
		},
	];

function HowItWorks() {
	return (
		<section id="how" className="scroll-mt-20 border-border border-y bg-card">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						How it works
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						From question to citation in seconds
					</h2>
				</div>

				<div className="mt-12 grid gap-6 md:grid-cols-3">
					{STEPS.map((s, i) => {
						const Icon = s.icon;
						return (
							<div key={s.step} className="relative">
								<div className="flex items-center gap-3">
									<div className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
										<Icon className="size-5" />
									</div>
									<span className="font-bold text-4xl text-border tabular-nums">
										{s.step}
									</span>
								</div>
								<h3 className="mt-5 font-semibold text-lg tracking-tight">
									{s.title}
								</h3>
								<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
									{s.body}
								</p>
								{i < STEPS.length - 1 && (
									<ArrowRightIcon className="-right-3 absolute top-3 hidden size-5 text-border md:block" />
								)}
							</div>
						);
					})}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// More from Hudson — scaffolds the roadmap: articles, products, consulting
// ---------------------------------------------------------------------------

type RoadmapCard = {
	icon: LucideIcon;
	tag: string;
	title: string;
	body: string;
	cta: string;
	href: string;
	live?: boolean;
};

const ROADMAP: RoadmapCard[] = [
	{
		icon: NewspaperIcon,
		tag: "Articles & Insights",
		title: "Field notes on legal AI",
		body: "Practical writing on grounding, retrieval, and what it takes to trust AI with a citation — from the team building it.",
		cta: "Read the blog",
		href: ARTICLE_HREF,
		live: true,
	},
	{
		icon: BookOpenIcon,
		tag: "Products",
		title: "A growing legal corpus",
		body: "Iowa today, more jurisdictions and practice tools next. One verified, citable foundation across everything we build.",
		cta: "Explore Hudson Corpus",
		href: PRODUCT_HREF,
		live: true,
	},
	{
		icon: BriefcaseIcon,
		tag: "Consulting",
		title: "Technology consulting that ships",
		body: "Strategy, custom software, data, and AI — pragmatic engineering help from the team that builds and ships its own products.",
		cta: "Talk to us",
		href: CONSULTING_HREF,
		live: true,
	},
];

function MoreFromHudson() {
	return (
		<section id="more" className="scroll-mt-20">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-wrap items-end justify-between gap-4">
					<div className="max-w-2xl">
						<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
							More from Hudson
						</span>
						<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
							A practice, not just a product
						</h2>
						<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
							The assistant is the first thing we shipped. Writing, more
							products, and hands-on consulting are next.
						</p>
					</div>
				</div>

				<div className="mt-12 grid gap-6 md:grid-cols-3">
					{ROADMAP.map((c) => {
						const Icon = c.icon;
						return (
							<Link
								key={c.tag}
								href={c.href}
								className="group flex flex-col rounded-2xl border border-border bg-card p-7 transition-shadow hover:shadow-md"
							>
								<div className="flex items-center justify-between">
									<div className="flex size-11 items-center justify-center rounded-xl bg-secondary text-foreground">
										<Icon className="size-5.5" />
									</div>
									<span
										className={cn(
											"rounded-full px-2.5 py-1 font-medium text-[11px] uppercase tracking-wider",
											c.live
												? "bg-emerald-100 text-emerald-700"
												: "bg-secondary text-muted-foreground",
										)}
									>
										{c.live ? "New" : "Coming soon"}
									</span>
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
			id="pricing"
			className="relative scroll-mt-20 overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />
			<div className="relative mx-auto max-w-4xl px-5 py-20 text-center sm:px-8 lg:py-24">
				{/* Brand's black banner block, reused as the marketing kicker. */}
				<div className="mb-7 inline-block bg-black px-5 py-2.5 text-left">
					<div className="font-bold text-lg leading-tight tracking-[0.04em] text-white uppercase">
						Stop guessing.
						<br />
						Start citing.
					</div>
				</div>
				<h2 className="font-bold text-3xl tracking-tight sm:text-4xl">
					Try Hudson free during beta
				</h2>
				<p className="mx-auto mt-4 max-w-xl text-lg text-white/75 leading-relaxed">
					Spin up an account in under a minute. Ask your first question, follow
					the citation to the source, and see the difference grounding makes.
				</p>
				<div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
					<Button
						asChild
						size="lg"
						className="bg-white text-[#11243d] hover:bg-white/90"
					>
						<Link href="/">
							Get started free
							<ArrowRightIcon />
						</Link>
					</Button>
					<Button
						asChild
						size="lg"
						variant="outline"
						className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
					>
						<Link href={CONSULTING_HREF}>Book a consultation</Link>
					</Button>
				</div>
			</div>
		</section>
	);
}
