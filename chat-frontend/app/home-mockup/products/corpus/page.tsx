// Product page for Hudson Corpus — the flagship grounded legal-research product.
//
// Lives under the marketing tree (/home-mockup/products/corpus) and uses the
// shared site chrome. Server component (carries <metadata>); the only client
// pieces are the nav and the drop-in Screenshot slots. Product imagery is
// supplied later: each <Screenshot> points at a /public path and shows a
// labeled placeholder until that file exists (see public/marketing/corpus/).

import {
	ArrowRightIcon,
	BadgeCheckIcon,
	GitCompareArrowsIcon,
	type LucideIcon,
	ScrollTextIcon,
	ShieldCheckIcon,
	TerminalIcon,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
	CONSULTING_HREF,
	gridTexture,
	MARKETING_HOME,
	navyBackdrop,
	SiteFooter,
	SiteNav,
} from "@/components/marketing/chrome";
import { Screenshot } from "@/components/marketing/screenshot";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
	title: "Hudson Corpus — Grounded legal research",
	description:
		"A grounded, citable research assistant for the Iowa Code, Court Rules, and caselaw. Every answer traced to the effective text, with verified citations.",
};

const SHOTS = {
	hero: "/marketing/corpus/assistant.png",
	browse: "/marketing/corpus/browse.png",
	reader: "/marketing/corpus/reader.png",
	search: "/marketing/corpus/search.png",
};

export default function CorpusProductPage() {
	return (
		<div className="min-h-dvh bg-background text-foreground">
			<SiteNav />
			<Hero />
			<FeatureSections />
			<CapabilityGrid />
			<CtaBand />
			<SiteFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Hero — navy band with copy; the primary screenshot overlaps into the page
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<>
			<section
				className="relative overflow-hidden text-white"
				style={navyBackdrop}
			>
				<div aria-hidden className="absolute inset-0" style={gridTexture} />
				<div className="relative mx-auto max-w-3xl px-5 pt-20 pb-44 text-center sm:px-8 lg:pt-24">
					<nav className="flex items-center justify-center gap-1.5 text-[13px] text-white/55">
						<Link
							href={`${MARKETING_HOME}#more`}
							className="hover:text-white/90"
						>
							Products
						</Link>
						<span>/</span>
						<span className="text-white/80">Corpus</span>
					</nav>

					<p className="mt-6 font-semibold text-[12px] text-white/70 uppercase tracking-[0.18em]">
						Hudson Corpus
					</p>
					<h1 className="mt-3 font-bold text-4xl leading-[1.1] tracking-tight sm:text-5xl">
						Grounded legal research, with the citation built in
					</h1>
					<p className="mx-auto mt-5 max-w-xl text-lg text-white/75 leading-relaxed">
						One assistant over the Iowa Code, Court Rules, and caselaw — every
						answer traced to the currently-effective text, every citation
						verified before you see it.
					</p>

					<div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
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
							<a href="#features">Tour the product</a>
						</Button>
					</div>
				</div>
			</section>

			{/* Primary product shot, pulled up to straddle the navy/light boundary. */}
			<div className="relative z-10 mx-auto -mt-36 max-w-5xl px-5 sm:px-8">
				<div
					aria-hidden
					className="-inset-x-4 absolute inset-y-6 rounded-3xl bg-primary/20 blur-3xl"
				/>
				<Screenshot
					src={SHOTS.hero}
					alt="The Hudson Corpus assistant answering a question with verified citations"
					label="Assistant — answer with verified citations"
					className="relative"
				/>
			</div>
		</>
	);
}

// ---------------------------------------------------------------------------
// Alternating feature sections — text + framed screenshot
// ---------------------------------------------------------------------------

type FeatureBlock = {
	eyebrow: string;
	title: string;
	body: string;
	points: string[];
	shot: string;
	alt: string;
	label: string;
};

const BLOCKS: FeatureBlock[] = [
	{
		eyebrow: "Browse",
		title: "The whole corpus, one library",
		body: "Statutes, rules, and decisions in a single, navigable workspace — search across everything or drill into one source.",
		points: [
			"Iowa Code, Court Rules & caselaw side by side",
			"Jump from a search hit straight into context",
			"Live counts so you know the coverage",
		],
		shot: "/marketing/corpus/browse.png",
		alt: "The Hudson Corpus library / browse view",
		label: "Browse — the unified library",
	},
	{
		eyebrow: "Read",
		title: "Read the source, not a summary",
		body: "Open the effective text with its citation, effective date, and enacting session law attached — and follow inline links to the official publication.",
		points: [
			"Currently-in-force text, version-aware",
			"Citation & effective date on every provision",
			"One click to the official source",
		],
		shot: "/marketing/corpus/reader.png",
		alt: "The Hudson Corpus statute / case reader",
		label: "Reader — the effective text",
	},
	{
		eyebrow: "Search",
		title: "Search that finds what you mean",
		body: "Full-text, trigram, and vector embeddings fused with Reciprocal Rank Fusion — type a citation number or describe the issue and the on-point provision surfaces either way.",
		points: [
			"Keyword precision + semantic recall",
			"Filter by source, court, and date",
			"Ranked, cited results — not ten blue links",
		],
		shot: "/marketing/corpus/search.png",
		alt: "The Hudson Corpus search results view",
		label: "Search — hybrid results",
	},
];

function FeatureSections() {
	return (
		<section id="features" className="scroll-mt-20">
			<div className="mx-auto flex max-w-6xl flex-col gap-20 px-5 pt-28 pb-8 sm:px-8 lg:gap-28 lg:pt-32">
				{BLOCKS.map((b, i) => (
					<div
						key={b.title}
						className="grid items-center gap-10 lg:grid-cols-2 lg:gap-14"
					>
						{/* Copy. On lg, every other block puts the copy on the right. */}
						<div className={i % 2 === 1 ? "lg:order-2" : undefined}>
							<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
								{b.eyebrow}
							</span>
							<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-[2rem]">
								{b.title}
							</h2>
							<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
								{b.body}
							</p>
							<ul className="mt-6 space-y-3">
								{b.points.map((p) => (
									<li key={p} className="flex items-start gap-3">
										<span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
											<BadgeCheckIcon className="size-3.5" />
										</span>
										<span className="text-[15px] text-foreground/85">{p}</span>
									</li>
								))}
							</ul>
						</div>

						{/* Screenshot slot. */}
						<div className={i % 2 === 1 ? "lg:order-1" : undefined}>
							<Screenshot src={b.shot} alt={b.alt} label={b.label} />
						</div>
					</div>
				))}
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Capability grid — the substance that needs no screenshot
// ---------------------------------------------------------------------------

type Capability = { icon: LucideIcon; title: string; body: string };

const CAPABILITIES: Capability[] = [
	{
		icon: ShieldCheckIcon,
		title: "Grounded retrieval",
		body: "Answers are built from the retrieved, human-reviewed text — not the model's memory. No support, no answer.",
	},
	{
		icon: BadgeCheckIcon,
		title: "Citation verification",
		body: "A deterministic check confirms every quote and citation against the source before the answer reaches you.",
	},
	{
		icon: GitCompareArrowsIcon,
		title: "Currency tracking",
		body: "Amendments and editions over time, with flags when a provision or holding has been superseded or overruled.",
	},
	{
		icon: ScrollTextIcon,
		title: "Real citations",
		body: "Citation, effective date, and enacting session law on every provision, linked to the official publication.",
	},
	{
		icon: TerminalIcon,
		title: "MCP & API",
		body: "Use it in the browser, or wire the corpus into Claude Desktop and your own tools over a production MCP endpoint.",
	},
	{
		icon: ShieldCheckIcon,
		title: "Built for trust",
		body: "Sourced from the official record and clearly scoped — a research tool that shows its work, not a black box.",
	},
];

function CapabilityGrid() {
	return (
		<section className="scroll-mt-20">
			<div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Under the hood
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						Why the answers hold up
					</h2>
				</div>

				<div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{CAPABILITIES.map((c) => {
						const Icon = c.icon;
						return (
							<div key={c.title} className="bg-card p-7">
								<div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
									<Icon className="size-5.5" />
								</div>
								<h3 className="mt-5 font-semibold text-lg tracking-tight">
									{c.title}
								</h3>
								<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
									{c.body}
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
// CTA band
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section
			className="relative overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />
			<div className="relative mx-auto max-w-3xl px-5 py-20 text-center sm:px-8 lg:py-24">
				<h2 className="font-bold text-3xl tracking-tight sm:text-4xl">
					See Hudson Corpus on your next question
				</h2>
				<p className="mx-auto mt-4 max-w-xl text-lg text-white/75 leading-relaxed">
					Free during beta. Ask, follow the citation to the source, and see what
					grounded research feels like.
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
