// Marketing home — the single-product, mission-first page (2026-08-30).
//
// One product launches: Hudson Corpus. The email assistant and EDMSpro are off
// the page (and off the nav and footer) because a product line-up was diluting
// the mission; MCP stays, but as a door into the corpus, not a product.
//
// The page walks the three classical appeals in order — the structure Nick
// asked for — with the Greek kept to the small mono eyebrows:
//   01 Ethos   who we are, and the standard we hold
//   02 Pathos  the stakes: an attorney using AI will outperform one who isn't,
//              and the threat to the profession is AI only big firms can afford
//   03 Logos   the proof: the corpus itself, how an answer is made, the three
//              tests (accessible / affordable / intuitive) with receipts
//   04 Pricing affordability is the mission, so the announced prices sit here
//
// House rule for this page: no em dashes in rendered copy. Numbers come off the
// live corpus (lib/api) and the frozen citation-graph snapshot (lib/briefs);
// prices render from lib/pricing so they cannot drift from /pricing.

import type { Metadata } from "next";
import {
	CarbonPage,
	Eyebrow,
	Frame,
	HairlineLink,
	INK,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import {
	ABOUT_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import { HeroCodeRain } from "@/components/marketing/hero-code-rain";
import { type CorpusStats, fetchCorpusStats, formatCount } from "@/lib/api";
import { formatAsOf, MOST_CITED_CASES } from "@/lib/briefs";
import { COMPARE_PLANS_HREF, PLANS, PRICING_NOTE } from "@/lib/pricing";
import { GET_STARTED_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title:
		"Hudson Legal Technologies: serious legal research, within reach of every practicing attorney",
	description:
		"Hudson Corpus is the effective law of Iowa: the Code, the administrative and court rules, and every appellate decision, with an assistant that answers from the text and verifies every citation before you see it. Priced for a solo, learnable in an afternoon.",
};

// The one frozen number on the page: the citation graph, from the same brief
// snapshot as /data (which carries the as-of date rendered beside it).
const EDGES = MOST_CITED_CASES.totals.edges;

const SOLO = PLANS[0];
const FIRM = PLANS[1];

export default async function HomePage() {
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<Hero stats={stats} />
			<Ethos />
			<Pathos />
			<Logos stats={stats} />
			<Pricing />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero — the mission speaks; the numbers (and the price) close the band
// ---------------------------------------------------------------------------

function facts(stats: CorpusStats): { value: string; label: string }[] {
	const caselaw = stats.sources
		.filter((s) => s.kind === "caselaw")
		.reduce((n, s) => n + s.entries, 0);
	return [
		{
			value: formatCount(stats.documents),
			label: "Documents of effective Iowa law in the corpus",
		},
		{
			value: formatCount(caselaw),
			label: `Iowa appellate decisions, with ${formatCount(EDGES)} citations mapped between them`,
		},
		{
			value: SOLO.price,
			label: "A month for the Solo plan, the announced launch price",
		},
		{
			value: "1",
			label:
				"Product. No suite, no add-ons. The corpus and the assistant over it.",
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
						Serious legal research, within reach
						<br />
						of every practicing attorney.
					</h1>

					<div aria-hidden className="mt-10 h-0.5 w-24 bg-[#0f62fe]" />

					<p className="mt-10 max-w-2xl text-[#c6c6c6] text-lg leading-relaxed">
						We make one product. Hudson Corpus is the effective law of Iowa: the
						Code, the administrative and court rules, and every appellate
						decision, with an assistant that answers from the text and verifies
						every citation before you see it. Priced for a solo. Learnable in an
						afternoon. Built by a lawyer who believes the advantage AI gives a
						practice should belong to the whole profession, not only the firms
						that can afford it.
					</p>

					<div className="mt-12 flex flex-col gap-3 sm:flex-row sm:items-center">
						<SolidLink href={GET_STARTED_URL}>Start researching</SolidLink>
						<HairlineLink href={PRICING_HREF}>See pricing</HairlineLink>
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
// 01 — Ethos: who we are, and the standard we hold
// ---------------------------------------------------------------------------

const STANDARD: { title: string; body: string }[] = [
	{
		title: "Nothing is asserted that cannot be traced to the text.",
		body: "Every answer traces to effective, citable law and is checked before it is delivered. Where the source does not exist, the system says so.",
	},
	{
		title: "Serious tools belong within reach of the whole profession.",
		body: "We build for solo practitioners, small firms and in-house teams, not only the institutions with procurement departments.",
	},
	{
		title: "What we learn from the corpus, we publish.",
		body: "The analysis that makes the product work goes out as data briefs and articles, frozen, sourced and open to being checked.",
	},
];

function Ethos() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					label="01 · Ethos · Who we are"
					title="A lawyer who builds software, and a standard we won't ship without."
				/>

				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<div className="max-w-xl space-y-5 text-[17px] text-foreground/85 leading-[1.75]">
						<p>
							Hudson Legal Technologies was started by a practicing attorney who
							writes software: the two things he cares most about, and a choice
							he refused to make. The company exists for one reason: to bring
							affordable, accessible, intuitive tools to the lawyers who
							actually practice.
						</p>
						<p>
							That focus is deliberate. We do not make a suite. We make one
							research system, we build the corpus underneath it ourselves, and
							what we learn from that corpus we publish, with the method and the
							data attached, so a lawyer can check it.
						</p>
						<div className="pt-2">
							<p className="text-[15px] text-foreground">Nick Hudson</p>
							<p className="mt-1 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
								Founder, Hudson Legal Technologies
							</p>
						</div>
						<div className="pt-1">
							<TextLink href={ABOUT_HREF}>About the company</TextLink>
						</div>
					</div>

					<div>
						<Eyebrow>The standard</Eyebrow>
						<ul className="mt-4 border-border border-t">
							{STANDARD.map((s, i) => (
								<li
									key={s.title}
									className="grid grid-cols-[40px_1fr] gap-x-4 border-border border-b py-5"
								>
									<span className="pt-0.5 font-mono text-[#0f62fe] text-[13px]">
										0{i + 1}
									</span>
									<div>
										<h3 className="text-[17px] leading-snug">{s.title}</h3>
										<p className="mt-1.5 text-[14px] text-muted-foreground leading-relaxed">
											{s.body}
										</p>
									</div>
								</li>
							))}
						</ul>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Pathos: the stakes. The argument, in Nick's framing: the threat to the
// profession is not AI; it is AI that only the largest firms can afford.
// ---------------------------------------------------------------------------

const NEEDS: { title: string; body: string }[] = [
	{
		title: "It has to be where the work already happens.",
		body: "A browser tab, and the AI tools a practice already runs. Not another portal to remember to open.",
	},
	{
		title: "It has to cost what a practice can pay.",
		body: "A solo's research budget is real money. The price belongs on the website, not behind a sales call.",
	},
	{
		title: "It has to be usable the day it arrives.",
		body: "A five-lawyer firm has no training week to spare. If it needs one, it will not get used.",
	},
];

function Pathos() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					label="02 · Pathos · Why it matters"
					title="An attorney using AI will outperform one who isn't."
					tone="dark"
				/>

				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<div className="max-w-xl space-y-5 text-[#c6c6c6] text-[17px] leading-[1.75]">
						<p>
							Anyone can now ask an AI a legal question and get a fluent answer
							in seconds. Your clients are doing it before they call you.
							Opposing counsel is doing it before they file.
						</p>
						<p>
							The firms that have put AI to work are doing in an hour what used
							to take a day, and they will outperform the attorney who hasn't:
							on speed, on price, on the matters they can take on. That is the
							competitive reality of practicing law now, not a forecast.
						</p>
						<p>
							The threat to the profession isn't AI. It's AI that only the
							largest firms can afford. If the advantage stays with the
							institutions with procurement departments, the solo and the small
							firm fall behind, and so do the clients who depend on them. Hudson
							exists so that isn't how it goes: research as capable as what the
							big firms are buying, priced for one lawyer, in the browser they
							already have open. And because this is law, built so every answer
							can be checked.
						</p>
					</div>

					<div className="space-y-10">
						<figure className="border-[#393939] border-t pt-6">
							<blockquote className="font-light text-2xl leading-[1.35]">
								“The threat to the profession isn't AI. It's a profession where
								only the biggest firms have it.”
							</blockquote>
							<figcaption className="mt-4 font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.18em]">
								Nick Hudson, Founder
							</figcaption>
						</figure>

						<div>
							<Eyebrow tone="dark">
								For every attorney to have it, it has to be
							</Eyebrow>
							<ul className="mt-4 border-[#393939] border-t">
								{NEEDS.map((n) => (
									<li key={n.title} className="border-[#393939] border-b py-4">
										<h3 className="text-[16px] leading-snug">{n.title}</h3>
										<p className="mt-1.5 text-[#a8a8a8] text-[14px] leading-relaxed">
											{n.body}
										</p>
									</li>
								))}
							</ul>
						</div>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Logos: the proof. The corpus itself, how an answer is made, and the
// three tests with receipts.
// ---------------------------------------------------------------------------

// The tile grid names the four corpus pillars explicitly (terms a lawyer
// recognizes); counts come off the live /api/browse/sources payload by source
// name, so they move the day the corpus does. A source the backend doesn't
// serve renders its degraded state rather than a stale number.
const CORPUS_TILES: { name: string; term: string; detail: string }[] = [
	{
		name: "Iowa Caselaw",
		term: "Caselaw",
		detail: "Decisions of the Iowa Supreme Court and Court of Appeals",
	},
	{
		name: "Iowa Code",
		term: "Code",
		detail: "Sections of the Iowa Code in force",
	},
	{
		name: "Iowa Administrative Code",
		term: "Administrative Code",
		detail: "Rules of the Iowa Administrative Code, agency by agency",
	},
	{
		name: "Iowa Court Rules",
		term: "Court Rules",
		detail: "Rules: civil, criminal, appellate, evidence, professional conduct",
	},
];

const STEPS: { title: string; body: string }[] = [
	{
		title: "Ask in plain language, or by citation number.",
		body: "The assistant shows its work as it goes: what it searched and which sections it read.",
	},
	{
		title: "It answers from the controlling text, and nothing else.",
		body: "Retrieval runs against the human-reviewed corpus. No support in the record, no answer.",
	},
	{
		title: "Every quote and citation is verified before you see it.",
		body: "A deterministic pass checks each one against its source; anything superseded or overruled is flagged, not quietly served. The source is one click away.",
	},
];

const TESTS: { n: string; title: string; body: string; receipt: string }[] = [
	{
		n: "01",
		title: "Accessible: where you already work.",
		body: "In the browser, and over MCP for Claude and any MCP client: the same corpus and the same verification, inside the AI tools a practice already runs.",
		receipt: "Web · MCP",
	},
	{
		n: "02",
		title: "Affordable: priced for a practice.",
		body: `Solo at ${SOLO.price} a month or $490 a year. Firm at ${FIRM.price} a month with three seats. Public pricing, no per-search charges, and no sales call to find out what it costs.`,
		receipt: `Solo ${SOLO.price} / mo · Firm ${FIRM.price} / mo`,
	},
	{
		n: "03",
		title: "Intuitive: learnable in an afternoon.",
		body: "Ask, read the answer with every citation linked, open the source. That is the whole workflow. Nothing to configure and nothing to train.",
		receipt: "Plain language in · Cited text out",
	},
];

function Logos({ stats }: { stats: CorpusStats }) {
	const byName = new Map(stats.sources.map((s) => [s.name, s.entries]));
	return (
		<section className="bg-card">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					label="03 · Logos · The proof"
					title="One corpus of the effective law. Every answer checked against it."
				/>

				<p className="mt-10 max-w-2xl text-[17px] text-foreground/85 leading-[1.75]">
					Hudson Corpus is one research surface over the effective law of Iowa,
					retrieved, quoted and cited by an assistant that cannot answer from
					memory. The difference is what happens before you see the answer.
				</p>

				<div className="mt-16">
					<Eyebrow>The corpus</Eyebrow>
					<dl className="mt-6 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
						{CORPUS_TILES.map((t) => (
							<div key={t.term} className="border-border border-t pt-5">
								<dt className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.22em]">
									{t.term}
								</dt>
								<dd className="mt-4 font-light text-3xl tabular-nums lg:text-4xl">
									{formatCount(byName.get(t.name) ?? 0)}
								</dd>
								<dd className="mt-2 text-[13px] text-muted-foreground leading-snug">
									{t.detail}
								</dd>
							</div>
						))}
					</dl>
					<p className="mt-8 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
						Live counts · {formatCount(EDGES)} citations mapped between the
						decisions as of {formatAsOf(MOST_CITED_CASES.as_of)}
					</p>
				</div>

				<div className="mt-16 grid gap-12 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
					<div>
						<Eyebrow>How an answer is made</Eyebrow>
						<ul className="mt-4 border-border border-t">
							{STEPS.map((s, i) => (
								<li
									key={s.title}
									className="grid grid-cols-[40px_1fr] gap-x-4 border-border border-b py-5"
								>
									<span className="pt-0.5 font-mono text-[#0f62fe] text-[13px]">
										0{i + 1}
									</span>
									<div>
										<h3 className="text-[16px] leading-snug">{s.title}</h3>
										<p className="mt-1.5 text-[14px] text-muted-foreground leading-relaxed">
											{s.body}
										</p>
									</div>
								</li>
							))}
						</ul>
						<div className="mt-7">
							<TextLink href={PRODUCT_HREF}>Explore Hudson Corpus</TextLink>
						</div>
					</div>

					<Frame
						src="/marketing/corpus/assistant.png"
						alt="Hudson Corpus answering an Iowa medical-malpractice limitations question, with the research run and verified citations visible"
						caption="Hudson Corpus · Assistant"
					/>
				</div>

				<div className="mt-20">
					<Eyebrow>Three tests, and the receipts</Eyebrow>
					<div className="mt-6 grid gap-x-8 gap-y-10 sm:grid-cols-3">
						{TESTS.map((t) => (
							<div key={t.n} className="border-border border-t pt-5">
								<span className="font-mono text-[#0f62fe] text-sm">{t.n}</span>
								<h3 className="mt-4 text-[19px] leading-snug">{t.title}</h3>
								<p className="mt-2.5 max-w-md text-[14px] text-muted-foreground leading-relaxed">
									{t.body}
								</p>
								<p className="mt-6 font-mono text-[#0f62fe] text-[11px] uppercase tracking-[0.18em]">
									{t.receipt}
								</p>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 04 — Pricing: affordability is the mission, so the announced prices sit on
// the home page, rendered from lib/pricing so they cannot drift from /pricing.
// ---------------------------------------------------------------------------

function Pricing() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					label="04 · Pricing"
					title="Announced before launch, and the same for everyone."
				/>

				<div className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-3">
					{PLANS.map((p) => (
						<div key={p.key} className="border-border border-t pt-6">
							<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
								{p.name}
							</p>
							<div className="mt-2 flex items-baseline gap-2">
								<span className="font-light text-4xl lg:text-5xl">
									{p.price}
								</span>
								{p.cadence && (
									<span className="text-muted-foreground text-sm">
										{p.cadence}
									</span>
								)}
							</div>
							<p className="mt-2 min-h-[1.25rem] text-[13px] text-muted-foreground">
								{p.subPrice}
							</p>
							<p className="mt-3 max-w-xs text-[15px] text-foreground/85 leading-relaxed">
								{p.tagline}
							</p>
						</div>
					))}
				</div>

				<p className="mt-10 max-w-2xl text-[13px] text-muted-foreground leading-relaxed">
					{PRICING_NOTE}
				</p>
				<div className="mt-6">
					<TextLink href={COMPARE_PLANS_HREF}>Compare the plans</TextLink>
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
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							See what grounded research feels like.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							In beta now. Ask a question, follow the citation to the source.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={GET_STARTED_URL}>Start researching</SolidLink>
						<HairlineLink href={PRICING_HREF}>See pricing</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
