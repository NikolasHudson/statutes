// Marketing home — the Carbon (IBM design system) home: editorial ink bands
// alternating with light ones, hairline rules instead of cards, Plex-light
// display type, square Blue-60 actions. The hero speaks for the company; the
// flagship product gets the entire first band, anchored by a real screenshot.
// Chrome + primitives live in components/marketing/carbon.tsx (shared by all
// Carbon pages). Promoted from /home-2 on 2026-07-10; the legacy Geist/navy
// home is gone.

import type { Metadata } from "next";
import Link from "next/link";
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
	ABOUT_HREF,
	ARTICLES_HREF,
	CONSULTING_HREF,
	PRODUCT_HREF,
	PRODUCTS_INDEX_HREF,
} from "@/components/marketing/chrome";
import { HeroCodeRain } from "@/components/marketing/hero-code-rain";
import { GET_STARTED_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title:
		"Hudson Legal Technologies — Legal technology, accountable to the source",
	description:
		"We build research systems for the practice of law. Every answer is grounded in effective, citable text and verified before it reaches you.",
};

export default function HomePage() {
	return (
		<CarbonPage>
			<Hero />
			<Flagship />
			<Principles />
			<WhatWeDo />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero — the company speaks; the numbers close the band
// ---------------------------------------------------------------------------

const FACTS: { value: string; label: string }[] = [
	{ value: "105,734", label: "Documents in the corpus" },
	{ value: "496K", label: "Passages, semantically searchable" },
	{ value: "3", label: "Sources unified — code, rules, caselaw" },
	{ value: "100%", label: "Answers tied to citable sources" },
];

function Hero() {
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
						We build research systems for the practice of law. Every answer is
						grounded in effective, citable text and verified before it reaches
						you — built for the whole profession, from solo practice to in-house
						counsel.
					</p>

					<div className="mt-12 flex flex-col gap-3 sm:flex-row sm:items-center">
						<SolidLink href={PRODUCT_HREF}>Explore Hudson Corpus</SolidLink>
						<HairlineLink href={ABOUT_HREF}>Our approach</HairlineLink>
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
// 01 — Flagship: Hudson Corpus, with the real product and a spec sheet
// ---------------------------------------------------------------------------

const SPECS: { term: string; detail: string }[] = [
	{ term: "Jurisdiction", detail: "Iowa" },
	{ term: "Sources", detail: "Code · Court rules · Caselaw" },
	{ term: "Status", detail: "Live in beta" },
	{ term: "Access", detail: "Web · MCP · Email" },
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
		body: "Statutes, court rules, and caselaw in one searchable system — semantic and keyword retrieval over 496,000 passages.",
	},
	{
		title: "Open integration",
		body: "The same grounded research runs in the browser, over a production MCP endpoint, and as an assistant that answers your email.",
	},
];

function Flagship() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="Flagship product"
					title="Hudson Corpus. Research that shows its work."
				/>

				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<p className="max-w-xl text-[17px] text-foreground/80 leading-[1.75]">
						Hudson Corpus is a grounded research assistant for practitioners.
						Ask a question in plain language; it searches the corpus, reads the
						controlling text, and answers with citations that link to the source
						— each one verified before you see it. When the law is silent, it
						says so.
					</p>

					<dl className="border-border border-t">
						{SPECS.map((s) => (
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
				</div>

				<figure className="mt-16 border border-border bg-card">
					<figcaption className="flex items-center justify-between border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
						<span>Hudson Corpus — Assistant</span>
						<span>corpus.nick.law</span>
					</figcaption>
					{/* biome-ignore lint/performance/noImgElement: static marketing capture, no next/image needed */}
					<img
						src="/marketing/corpus/assistant.png"
						alt="Hudson Corpus answering an Iowa medical-malpractice limitations question, with the research run and verified citations visible"
						className="w-full"
					/>
				</figure>

				<div className="mt-16 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
					{CAPABILITIES.map((c) => (
						<div key={c.title} className="border-border border-t pt-5">
							<h3 className="font-semibold text-[15px]">{c.title}</h3>
							<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
								{c.body}
							</p>
						</div>
					))}
				</div>

				<div className="mt-14">
					<TextLink href={PRODUCT_HREF}>Explore Hudson Corpus</TextLink>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Principles
// ---------------------------------------------------------------------------

const PRINCIPLES: { n: string; claim: string; body: string }[] = [
	{
		n: "01",
		claim: "An answer that cannot be verified is not an answer.",
		body: "Every response traces to effective, citable text and is checked before it is delivered. Where the source does not exist, the system says so.",
	},
	{
		n: "02",
		claim: "Serious tools should be within reach of the whole profession.",
		body: "We build for solo practitioners, small firms, and in-house teams — not only the institutions with procurement departments.",
	},
	{
		n: "03",
		claim: "Complexity belongs in the system, not the interface.",
		body: "Our products are fast, modern, and legible on first use. A tool that requires a training program has failed a basic test.",
	},
	{
		n: "04",
		claim: "We advise only on what we have built.",
		body: "Our consulting practice draws on software we design, ship, and operate ourselves — the diagram comes after the work.",
	},
];

function Principles() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="Operating principles"
					title="The standard we build against."
					tone="dark"
				/>

				<div className="mt-14 grid gap-x-12 gap-y-12 sm:grid-cols-2">
					{PRINCIPLES.map((p) => (
						<div key={p.n} className="border-[#393939] border-t pt-6">
							<span className="font-mono text-[#78a9ff] text-sm">{p.n}</span>
							<h3 className="mt-4 text-xl leading-snug">{p.claim}</h3>
							<p className="mt-3 max-w-md text-[#a8a8a8] text-[15px] leading-relaxed">
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
// 03 — What we do: ruled tiles, whole tile clickable, arrow on the baseline
// ---------------------------------------------------------------------------

const DISCIPLINES: {
	tag: string;
	title: string;
	body: string;
	cta: string;
	href: string;
}[] = [
	{
		tag: "Products",
		title: "One corpus. Three doors.",
		body: "Hudson Corpus in the browser, an MCP endpoint for your AI tools, and an assistant that answers your email — the same grounded, verified research behind each. Live in beta.",
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
	{
		tag: "Research",
		title: "Articles & analysis",
		body: "Published work on grounding, retrieval, and the engineering of legal AI the profession can rely on. We write down what building it taught us.",
		cta: "Read the latest",
		href: ARTICLES_HREF,
	},
];

function WhatWeDo() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="What we do"
					title="Three disciplines. One standard."
				/>

				<div className="mt-14 grid divide-y divide-border border border-border lg:grid-cols-3 lg:divide-x lg:divide-y-0">
					{DISCIPLINES.map((d) => (
						<Link
							key={d.tag}
							href={d.href}
							className="group flex min-h-[280px] flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8]"
						>
							<Eyebrow>{d.tag}</Eyebrow>
							<h3 className="mt-5 text-2xl">{d.title}</h3>
							<p className="mt-3 text-[15px] text-muted-foreground leading-relaxed">
								{d.body}
							</p>
							<span className="mt-auto flex items-center justify-between pt-10 font-medium text-[#0f62fe] text-sm">
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
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// CTA band — left-aligned, declarative
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
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
