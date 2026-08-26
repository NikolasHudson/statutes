// Marketing home — the Carbon (IBM design system) home: editorial ink bands
// alternating with light ones, hairline rules instead of cards, Plex-light
// display type, square Blue-60 actions. Chrome + primitives live in
// components/marketing/carbon.tsx (shared by all Carbon pages). Promoted from
// /home-2 on 2026-07-10; the legacy Geist/navy home is gone.
//
// Rebalanced 2026-08-15: the page used to give each product a full band of its
// own, which read as a two-item product catalogue. The work is wider than that
// — we build the corpus, publish original analysis of it, ship tools on top of
// it, and advise on the rest — so research now takes the first section, the
// latest data brief is on the page, and both products share the second band.

import type { Metadata } from "next";
import Link from "next/link";
import { FeaturedBrief } from "@/components/marketing/briefs/featured-brief";
import {
	CarbonPage,
	Eyebrow,
	HairlineLink,
	INK,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import {
	ARTICLES_HREF,
	CONSULTING_HREF,
	DATA_HREF,
	EDMS_PRODUCT_HREF,
	PRODUCT_HREF,
	PRODUCTS_INDEX_HREF,
} from "@/components/marketing/chrome";
import { HeroCodeRain } from "@/components/marketing/hero-code-rain";
import {
	type CorpusSource,
	type CorpusStats,
	corpusSourceNames,
	fetchCorpusStats,
	formatCount,
} from "@/lib/api";
import { MOST_CITED_CASES } from "@/lib/briefs";
import { APP_HOST, GET_STARTED_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title:
		"Hudson Legal Technologies — Legal technology, accountable to the source",
	description:
		"We work across legal AI: the Iowa corpus underneath it, original data briefs on what the record actually says, research tools with every citation verified against the effective text, and consulting for the teams adopting it.",
};

export default async function HomePage() {
	// Every number on this page comes off the live corpus (see lib/api.ts). The
	// figures that used to sit here as literals were 18k documents and a whole
	// source out of date, and understated the breadth that is our actual lead.
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<Hero stats={stats} />
			<Research />
			<Products stats={stats} />
			<Principles />
			<WhatWeDo />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero — the company speaks; the numbers close the band
// ---------------------------------------------------------------------------

// The statutory tiers and the caselaw tier, counted separately: they sum to the
// total, and a lawyer reads "46,752 statutes and rules" very differently from
// "76,672 decisions". The last tile is the citation graph we built over those
// decisions — the only frozen number in the row (it comes off the same brief
// snapshot as § 01, which carries the as-of date), and the one that says we do
// something with the corpus besides serve it.
function facts(stats: CorpusStats): { value: string; label: string }[] {
	const of = (kind: CorpusSource["kind"]) =>
		stats.sources
			.filter((s) => s.kind === kind)
			.reduce((n, s) => n + s.entries, 0);
	return [
		{ value: formatCount(stats.documents), label: "Documents in the corpus" },
		{
			value: formatCount(of("statutes")),
			label: "Statutes, administrative rules and court rules",
		},
		{ value: formatCount(of("caselaw")), label: "Iowa decisions" },
		{
			value: formatCount(MOST_CITED_CASES.totals.edges),
			label: "Citations mapped between those decisions",
		},
	];
}

function Hero({ stats }: { stats: CorpusStats }) {
	const FACTS = facts(stats);
	return (
		<section className={cn("relative overflow-hidden text-white", INK)}>
			{/* Statute text → binary, painting the whole band… */}
			<HeroCodeRain />
			{/* …under a dark overlay, heaviest where the headline sits. */}
			<div
				aria-hidden
				className="absolute inset-0"
				style={{
					background:
						"linear-gradient(90deg, rgba(22,22,22,0.85) 0%, rgba(22,22,22,0.6) 45%, rgba(22,22,22,0.22) 100%)",
				}}
			/>
			<div className="relative mx-auto max-w-7xl px-5 sm:px-8">
				<div className="border-[#393939] border-b py-20 lg:py-28">
					<Eyebrow tone="dark">Hudson Legal Technologies</Eyebrow>

					<h1 className="mt-8 max-w-5xl font-light text-4xl leading-[1.1] sm:text-5xl lg:text-[4.25rem]">
						Legal technology,
						<br />
						accountable to the source.
					</h1>

					<div aria-hidden className="mt-10 h-0.5 w-24 bg-[#0f62fe]" />

					<p className="mt-10 max-w-2xl text-[#c6c6c6] text-lg leading-relaxed">
						We work across legal AI — the corpus it has to be grounded in, the
						research into what is actually in that record, and the tools
						practitioners use every day. One standard runs through all of it:
						nothing is asserted that cannot be traced back to the text.
					</p>

					<div className="mt-12 flex flex-col gap-3 sm:flex-row sm:items-center">
						<SolidLink href={PRODUCTS_INDEX_HREF}>
							Explore the products
						</SolidLink>
						<HairlineLink href={DATA_HREF}>
							Read our latest analysis
						</HairlineLink>
					</div>
				</div>

				<dl className="grid grid-cols-2 gap-x-8 py-14 lg:grid-cols-4">
					{FACTS.map((f) => (
						<div key={f.label} className="border-[#393939] border-t pt-6">
							<dt className="sr-only">{f.label}</dt>
							<dd className="font-light text-4xl tabular-nums sm:text-5xl">
								{f.value}
							</dd>
							<p className="mt-3 max-w-[16rem] text-[#a8a8a8] text-[13px] leading-snug">
								{f.label}
							</p>
						</div>
					))}
				</dl>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 01 — Research: the data-brief series, with the latest brief on the page
// ---------------------------------------------------------------------------

// The series contract, condensed from the three rules stated in full on /data.
// It belongs next to the card because it is the reason to believe the card:
// anyone can publish a chart, and the argument for these is that they are
// frozen, sourced, and answerable.
const SERIES_RULES: { title: string; body: string }[] = [
	{
		title: "An argument, not a dashboard",
		body: "One question per brief, with a point of view — not a filter panel handed to the reader.",
	},
	{
		title: "The method is on the page",
		body: "How it was measured, what it misses, and the full data behind every figure.",
	},
	{
		title: "Frozen and citable",
		body: "Published with an as-of date and no drift. A refresh is a deliberate, reviewed re-export.",
	},
];

function Research() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="Research"
					title="We study the record, not just search it."
					tone="dark"
				/>

				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<p className="max-w-xl text-[#c6c6c6] text-[17px] leading-[1.75]">
						Building a research system means computing things about the law that
						nobody had computed before: every citation between every Iowa
						appellate decision, every act that has amended the Code, every rule
						an agency hangs off a statute. Our data briefs publish that work —
						original analysis of the Iowa record, answered from the whole of it
						rather than a sample, and written so a lawyer can check it.
					</p>

					<ul className="border-[#393939] border-t">
						{SERIES_RULES.map((r) => (
							<li key={r.title} className="border-[#393939] border-b py-4">
								<h3 className="font-semibold text-[14.5px]">{r.title}</h3>
								<p className="mt-1.5 text-[#a8a8a8] text-[13.5px] leading-relaxed">
									{r.body}
								</p>
							</li>
						))}
					</ul>
				</div>

				<FeaturedBrief className="mt-14" />

				<div className="mt-12 flex flex-wrap gap-x-12 gap-y-4">
					<TextLink href={DATA_HREF} tone="dark">
						All data briefs
					</TextLink>
					<TextLink href={ARTICLES_HREF} tone="dark">
						Notes on building it
					</TextLink>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Products: both of them, one band. Hudson Corpus leads (it is the
// flagship and the only one with a screenshot worth the space); Hudson EDMSpro
// follows below the hairline in a compact block.
// ---------------------------------------------------------------------------

// The source list is rendered from the same payload as the counts, so it cannot
// drift from what we actually serve — and it grows by itself the day a new
// source is ingested to production.
function specs(stats: CorpusStats): { term: string; detail: string }[] {
	return [
		{ term: "Jurisdiction", detail: "Iowa" },
		{ term: "Sources", detail: corpusSourceNames(stats) || "—" },
		{ term: "Status", detail: "Live in beta" },
		{ term: "Access", detail: "Web · MCP · Email" },
	];
}

const EDMS_SPECS: { term: string; detail: string }[] = [
	{ term: "Surface", detail: "Chrome extension" },
	{ term: "Works with", detail: "Iowa EDMS" },
	{ term: "Status", detail: "Rolling out — early access" },
	{ term: "Included with", detail: "Solo & Firm plans" },
];

const CAPABILITIES: { title: string; body: string }[] = [
	{
		title: "Grounded answers",
		body: "Responses are drawn from the effective text of the law — not from a model's recollection of it.",
	},
	{
		title: "Verified citations",
		body: "Every citation is checked against the source before the answer is delivered. Failures are surfaced, not smoothed over.",
	},
	{
		title: "A unified corpus",
		body: "Statutes, administrative rules, court rules, and caselaw in one searchable system — semantic and keyword retrieval, fused and reranked.",
	},
	{
		title: "Open integration",
		body: "The same grounded research runs in the browser, over a production MCP endpoint, and as an assistant that answers your email.",
	},
];

const EDMS_POINTS: { title: string; body: string }[] = [
	{
		title: "Docket-side preview",
		body: "Read any filing in a panel beside the docket — no downloads-folder detour, no losing your place in the list.",
	},
	{
		title: "Smart download",
		body: "Filings land under clean, consistent names from your own rules instead of the court's — one at a time, or the whole docket at once.",
	},
	{
		title: "Never through our servers",
		body: "Documents move from the court straight to you. Hudson never receives, stores, or reads a filing — by construction, not by policy.",
	},
];

function SpecList({ items }: { items: { term: string; detail: string }[] }) {
	return (
		<dl className="border-border border-t">
			{items.map((s) => (
				<div
					key={s.term}
					className="flex items-baseline justify-between gap-6 border-border border-b py-3.5"
				>
					<dt className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
						{s.term}
					</dt>
					<dd className="text-right font-medium text-sm">{s.detail}</dd>
				</div>
			))}
		</dl>
	);
}

function Products({ stats }: { stats: CorpusStats }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="Products"
					title="Tools built on the same record."
				/>

				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<div className="max-w-xl">
						<Eyebrow>Flagship — research</Eyebrow>
						<h3 className="mt-4 font-light text-3xl">Hudson Corpus</h3>
						<p className="mt-5 text-[17px] text-foreground/80 leading-[1.75]">
							A grounded research assistant for practitioners. Ask a question in
							plain language; it searches the corpus, reads the controlling
							text, and answers with citations that link to the source — each
							one verified before you see it. When the law is silent, it says
							so.
						</p>
						<div className="mt-7">
							<TextLink href={PRODUCT_HREF}>Explore Hudson Corpus</TextLink>
						</div>
					</div>

					<SpecList items={specs(stats)} />
				</div>

				<figure className="mt-14 border border-border bg-card">
					<figcaption className="flex items-center justify-between border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
						<span>Hudson Corpus — Assistant</span>
						<span>{APP_HOST}</span>
					</figcaption>
					{/* biome-ignore lint/performance/noImgElement: static marketing capture, no next/image needed */}
					<img
						src="/marketing/corpus/assistant.png"
						alt="Hudson Corpus answering an Iowa medical-malpractice limitations question, with the research run and verified citations visible"
						className="w-full"
					/>
				</figure>

				<div className="mt-14 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
					{CAPABILITIES.map((c) => (
						<div key={c.title} className="border-border border-t pt-5">
							<h4 className="font-semibold text-[15px]">{c.title}</h4>
							<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
								{c.body}
							</p>
						</div>
					))}
				</div>

				<div className="mt-20 grid gap-12 border-border border-t pt-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<div className="max-w-xl">
						<Eyebrow>New — court filings</Eyebrow>
						<h3 className="mt-4 font-light text-3xl">Hudson EDMSpro</h3>
						<p className="mt-5 text-[17px] text-foreground/80 leading-[1.75]">
							Research is half the day; the other half is paper. A Chrome
							extension for Iowa's EDMS that turns docket work into one click —
							preview a filing beside the docket, then download it named the way
							your office actually files things, straight from the court to you.
						</p>
						<div className="mt-7">
							<TextLink href={EDMS_PRODUCT_HREF}>
								Explore Hudson EDMSpro
							</TextLink>
						</div>
					</div>

					<SpecList items={EDMS_SPECS} />
				</div>

				<div className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-3">
					{EDMS_POINTS.map((c) => (
						<div key={c.title} className="border-border border-t pt-5">
							<h4 className="font-semibold text-[15px]">{c.title}</h4>
							<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
								{c.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Principles. White (card) rather than the page's light gray: it follows
// the products band, and two light bands running together need the step.
// ---------------------------------------------------------------------------

const PRINCIPLES: { n: string; claim: string; body: string }[] = [
	{
		n: "01",
		claim: "An answer that cannot be verified is not an answer.",
		body: "Every response traces to effective, citable text and is checked before it is delivered. Where the source does not exist, the system says so.",
	},
	{
		n: "02",
		claim: "What we learn from the corpus, we publish.",
		body: "The analysis that makes the products work is worth reading on its own — so it goes out as briefs and articles, with the method and the data attached.",
	},
	{
		n: "03",
		claim: "Serious tools should be within reach of the whole profession.",
		body: "We build for solo practitioners, small firms, and in-house teams — not only the institutions with procurement departments.",
	},
	{
		n: "04",
		claim: "We advise only on what we have built.",
		body: "Our consulting practice draws on software we design, ship, and operate ourselves — the diagram comes after the work.",
	},
];

function Principles() {
	return (
		<section className="bg-card">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="Operating principles"
					title="The standard we build against."
				/>

				<div className="mt-14 grid gap-x-12 gap-y-12 sm:grid-cols-2">
					{PRINCIPLES.map((p) => (
						<div key={p.n} className="border-border border-t pt-6">
							<span className="font-mono text-[#0f62fe] text-sm">{p.n}</span>
							<h3 className="mt-4 text-xl leading-snug">{p.claim}</h3>
							<p className="mt-3 max-w-md text-[15px] text-muted-foreground leading-relaxed">
								{p.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 04 — What we do: ruled tiles, whole tile clickable, arrow on the baseline;
// the page's CTA closes the band (keeps the light/ink rhythm intact)
// ---------------------------------------------------------------------------

const DISCIPLINES: {
	tag: string;
	title: string;
	body: string;
	cta: string;
	href: string;
}[] = [
	{
		tag: "Research",
		title: "Data briefs & analysis",
		body: "Original analysis of the Iowa record — which cases do the work, what changes, who regulates — published frozen, sourced, and open to being checked.",
		cta: "Read the latest brief",
		href: DATA_HREF,
	},
	{
		tag: "Products",
		title: "Tools for Iowa practice",
		body: "Hudson Corpus in the browser, over MCP, and by email — and Hudson EDMSpro for court filings. The research is verified; the filings stay yours.",
		cta: "Explore the products",
		href: PRODUCTS_INDEX_HREF,
	},
	{
		tag: "Consulting",
		title: "Technology consulting",
		body: "Strategy, custom software, data, and applied AI for teams that need it built correctly — delivered against the same standard we hold our own products to.",
		cta: "Engage our team",
		href: CONSULTING_HREF,
	},
];

function WhatWeDo() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="04"
					label="What we do"
					title="Three disciplines. One standard."
					tone="dark"
				/>

				<div className="mt-14 grid divide-y divide-[#393939] border border-[#393939] lg:grid-cols-3 lg:divide-x lg:divide-y-0">
					{DISCIPLINES.map((d) => (
						<Link
							key={d.tag}
							href={d.href}
							className="group flex min-h-[280px] flex-col bg-[#161616] p-8 transition-colors hover:bg-[#292929]"
						>
							<Eyebrow tone="dark">{d.tag}</Eyebrow>
							<h3 className="mt-5 text-2xl">{d.title}</h3>
							<p className="mt-3 text-[#a8a8a8] text-[15px] leading-relaxed">
								{d.body}
							</p>
							<span className="mt-auto flex items-center justify-between pt-10 font-medium text-[#78a9ff] text-sm">
								{d.cta}
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

				<div className="mt-16 flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							Evaluate it on real questions.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							Hudson Corpus is live in beta. Ask a question you already know the
							answer to — then follow every citation to its source.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={GET_STARTED_URL}>Open Hudson Corpus</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>Talk to our team</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
