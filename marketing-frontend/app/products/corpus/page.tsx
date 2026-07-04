// Product page for Hudson Corpus — the flagship grounded legal-research
// product, in the Carbon (IBM design system) register.
//
// Lives under the marketing tree (/products/corpus) on the shared Carbon
// chrome (components/marketing/carbon.tsx): dark #161616 leadspace, light and
// ink bands alternating, hairline rules, Plex-light display type, square
// Blue-60 actions. Server component (carries <metadata>).

import {
	BadgeCheckIcon,
	GitCompareArrowsIcon,
	type LucideIcon,
	ScrollTextIcon,
	ShieldCheckIcon,
	TerminalIcon,
} from "lucide-react";
import type { Metadata } from "next";
import {
	CarbonPage,
	Frame,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import { CONSULTING_HREF, MARKETING_HOME } from "@/components/marketing/chrome";
import { APP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Hudson Corpus — Grounded legal research",
	description:
		"A grounded, citable research assistant for the Iowa Code, Court Rules, and caselaw. Every answer traced to the effective text, with verified citations.",
};

export default function CorpusProductPage() {
	return (
		<CarbonPage>
			<Hero />
			<HeroShot />
			<FeatureSections />
			<CapabilityGrid />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero — dark leadspace; the primary product shot follows in a light band
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<PageHero
			eyebrow="Products — Hudson Corpus"
			title={
				<>
					Grounded legal research,
					<br />
					with the citation built in.
				</>
			}
			lede="One assistant over the Iowa Code, Court Rules, and caselaw — every answer traced to the currently-effective text, every citation verified before you see it."
			actions={
				<>
					<SolidLink href={APP_URL}>Start researching</SolidLink>
					<HairlineLink href="#features">Tour the product</HairlineLink>
				</>
			}
		/>
	);
}

function HeroShot() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-20">
				<Frame
					src="/marketing/corpus/assistant.png"
					alt="The Hudson Corpus assistant answering a question with verified citations"
					caption="Assistant — answer with verified citations"
				/>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 01–03 Feature sections — SectionHead, then a full-width Frame. The app
// screens are dense (sidebars + rails + fine text), so they take the full
// container width; the supporting points sit in a ruled row beneath. Bands
// alternate dark / light / dark to keep the Carbon rhythm.
// ---------------------------------------------------------------------------

type FeatureBlock = {
	n: string;
	label: string;
	title: string;
	body: string;
	points: string[];
	shot: string;
	alt: string;
	caption: string;
};

const BLOCKS: FeatureBlock[] = [
	{
		n: "01",
		label: "Browse",
		title: "The whole corpus, one library.",
		body: "Statutes, rules, and decisions in a single, navigable workspace — search across everything or drill into one source.",
		points: [
			"Iowa Code, Court Rules & caselaw side by side",
			"Jump from a search hit straight into context",
			"Live counts so you know the coverage",
		],
		shot: "/marketing/corpus/browse.png",
		alt: "The Hudson Corpus library / browse view",
		caption: "Browse — the unified library",
	},
	{
		n: "02",
		label: "Read",
		title: "Read the source, not a summary.",
		body: "Open the effective text with its citation, effective date, and enacting session law attached — and follow inline links to the official publication.",
		points: [
			"Currently-in-force text, version-aware",
			"Citation & effective date on every provision",
			"One click to the official source",
		],
		shot: "/marketing/corpus/reader.png",
		alt: "The Hudson Corpus statute / case reader",
		caption: "Reader — the effective text",
	},
	{
		n: "03",
		label: "Search",
		title: "Search that finds what you mean.",
		body: "Full-text, trigram, and vector embeddings fused with Reciprocal Rank Fusion — type a citation number or describe the issue and the on-point provision surfaces either way.",
		points: [
			"Keyword precision + semantic recall",
			"Filter by source, court, and date",
			"Ranked, cited results — not ten blue links",
		],
		shot: "/marketing/corpus/search.png",
		alt: "The Hudson Corpus search results view",
		caption: "Search — hybrid results",
	},
];

function FeatureSection({ b, dark }: { b: FeatureBlock; dark: boolean }) {
	return (
		<section
			id={b.n === "01" ? "features" : undefined}
			className={cn(
				"scroll-mt-20",
				dark ? cn("text-white", INK) : "bg-background",
			)}
		>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n={b.n}
					label={b.label}
					title={b.title}
					tone={dark ? "dark" : "light"}
				/>

				<p
					className={cn(
						"mt-10 max-w-xl text-[17px] leading-[1.75]",
						dark ? "text-[#c6c6c6]" : "text-foreground/80",
					)}
				>
					{b.body}
				</p>

				<Frame
					src={b.shot}
					alt={b.alt}
					caption={b.caption}
					className={cn("mt-12", dark && "border-[#393939]")}
				/>

				<ul className="mt-12 grid gap-x-8 gap-y-8 sm:grid-cols-3">
					{b.points.map((p) => (
						<li
							key={p}
							className={cn(
								"border-t pt-5 text-[14px] leading-snug",
								dark
									? "border-[#393939] text-[#c6c6c6]"
									: "border-border text-foreground/85",
							)}
						>
							{p}
						</li>
					))}
				</ul>
			</div>
		</section>
	);
}

function FeatureSections() {
	return (
		<>
			{BLOCKS.map((b, i) => (
				<FeatureSection key={b.n} b={b} dark={i % 2 === 0} />
			))}
		</>
	);
}

// ---------------------------------------------------------------------------
// 04 — Capability grid: the substance that needs no screenshot
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
		<section className="scroll-mt-20 bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="04"
					label="Under the hood"
					title="Why the answers hold up."
				/>

				<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{CAPABILITIES.map((c) => {
						const Icon = c.icon;
						return (
							<div key={c.title} className="bg-card p-8">
								<Icon className="size-5" strokeWidth={1.5} aria-hidden />
								<h3 className="mt-6 font-semibold text-[15px]">{c.title}</h3>
								<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
									{c.body}
								</p>
							</div>
						);
					})}
				</div>

				<div className="mt-14">
					<TextLink href={`${MARKETING_HOME}#more`}>All products</TextLink>
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
							See Hudson Corpus on your next question.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							In beta now. Ask, follow the citation to the source, and see what
							grounded research feels like.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
