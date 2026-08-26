// Product page for Hudson Corpus — the flagship grounded legal-research
// product, laid out the way ibm.com/products/* is (see
// components/marketing/product-page.tsx for the shell): breadcrumb, a leadspace
// whose H1 is the product's name, a sticky in-page nav carrying the section
// anchors and the primary action, then Overview → Features → Use cases →
// Resources → Pricing → "Take the next step".
//
// Still the Carbon register the rest of the site uses: dark #161616 bands
// alternating with the gray-10 and white layers, hairline rules, Plex-light
// display type, square Blue-60 actions. Server component (carries <metadata>).

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
	Eyebrow,
	Frame,
	HairlineLink,
	SolidLink,
} from "@/components/marketing/carbon";
import {
	ARTICLES_HREF,
	CONSULTING_HREF,
	CONTACT_HREF,
	DATA_HREF,
	MCP_PRODUCT_HREF,
	PRICING_HREF,
} from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import {
	FeatureTabs,
	type ProductFeature,
} from "@/components/marketing/product-features";
import {
	NextStep,
	PlanBand,
	ProductLeadspace,
	ProductSection,
	type Resource,
	ResourceCards,
	StatRow,
	type UseCase,
	UseCaseGrid,
} from "@/components/marketing/product-page";
import {
	ProductSubnav,
	type SubnavSection,
} from "@/components/marketing/product-subnav";
import {
	type CorpusStats,
	corpusSourceProse,
	fetchCorpusStats,
	formatCount,
} from "@/lib/api";
import { APP_URL, BRAND_NAME } from "@/lib/site";

// Every source list on this page is DERIVED, like / and /products already do.
//
// All three used to be hand-typed as "the Iowa Code, Court Rules, and caselaw",
// silently dropping the Iowa Administrative Code — 17,690 rules, live on prod
// since 2026-07-10. /products renders the API-derived "Caselaw · Code ·
// Administrative Code · Court Rules" and links straight here, so a visitor
// clicking a source list that advertises admin rules landed on the product page
// that never mentioned them. That understates our own corpus-breadth lead, which
// is the worst direction to be wrong in.
const FALLBACK_SOURCES = "Code, Administrative Code, Court Rules & caselaw";

function sourceList(stats: CorpusStats): string {
	return corpusSourceProse(stats) || FALLBACK_SOURCES;
}

// Async: the description states the corpus as fact, so it is fetched, not typed.
// Next dedupes this fetch against the page's own call in the same render pass.
export async function generateMetadata(): Promise<Metadata> {
	const stats = await fetchCorpusStats();
	return {
		title: "Hudson Corpus — Grounded legal research",
		description: `A grounded, citable research assistant for the Iowa ${sourceList(stats)}. Every answer traced to the effective text, with verified citations.`,
	};
}

const SECTIONS: SubnavSection[] = [
	{ id: "overview", label: "Overview" },
	{ id: "features", label: "Features" },
	{ id: "use-cases", label: "Use cases" },
	{ id: "resources", label: "Resources" },
	{ id: "pricing", label: "Pricing" },
];

export default async function CorpusProductPage() {
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<Lead stats={stats} />
			<ProductSubnav product={BRAND_NAME} sections={SECTIONS} />
			<Overview stats={stats} />
			<Features stats={stats} />
			<UseCases />
			<Resources />
			<Pricing />
			<NextStep
				title="See Hudson Corpus on your next question."
				body="In beta now. Ask, follow the citation to the source, and see what grounded research feels like."
				actions={
					<>
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</>
				}
				explore={[
					{ label: "Pricing", href: PRICING_HREF },
					{ label: "Research & data", href: DATA_HREF },
					{ label: "Articles", href: ARTICLES_HREF },
					{ label: "Consulting", href: CONSULTING_HREF },
					{ label: "Contact us", href: CONTACT_HREF },
				]}
			/>
			<ProductFamily current="corpus" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Leadspace — product name as the headline, the promise under it, the
// assistant capture in the right column
// ---------------------------------------------------------------------------

function Lead({ stats }: { stats: CorpusStats }) {
	return (
		<ProductLeadspace
			product={BRAND_NAME}
			tagline="Grounded legal research, with the citation built in."
			lede={`One assistant over the Iowa ${sourceList(stats)} — every answer traced to the currently-effective text, every citation verified before you see it.`}
			actions={
				<>
					<SolidLink href={APP_URL}>Start researching</SolidLink>
					<HairlineLink href="#features">See the features</HairlineLink>
				</>
			}
			visual={
				// Cropped: the leadspace wants the answer and its verification
				// steps, not the whole workspace. The uncropped capture is the
				// Ask tab's, below.
				<Frame
					src="/marketing/corpus/assistant.png"
					alt="The Hudson Corpus assistant answering a question with verified citations"
					caption="Assistant — answer with verified citations"
					aspect="16 / 10"
					className="border-[#393939]"
				/>
			}
		/>
	);
}

// ---------------------------------------------------------------------------
// Overview — the claim, then the corpus by the numbers
// ---------------------------------------------------------------------------

// One tile per populated source, largest first, straight off /api/browse/sources.
// A degraded fetch (dev, no backend) yields no sources and StatRow renders
// nothing — an empty row beats a row of em dashes presented as figures.
function statTiles(stats: CorpusStats) {
	return stats.sources.slice(0, 4).map((s) => ({
		value: formatCount(s.entries),
		label: s.name.replace(/^Iowa\s+/, ""),
		sub: s.entry_label,
	}));
}

function Overview({ stats }: { stats: CorpusStats }) {
	return (
		<ProductSection
			id="overview"
			label="Overview"
			title="Research that shows its work."
			intro={`Hudson Corpus is one research surface over the Iowa ${sourceList(stats)} — ${formatCount(stats.documents)} documents, retrieved, quoted, and cited by an assistant that cannot answer from memory. Ask in plain English or by citation number; every claim comes back attached to the provision or opinion it came from.`}
		>
			<p className="mt-6 max-w-2xl text-[17px] text-foreground/80 leading-[1.75]">
				The difference is what happens before you see the answer. Retrieval runs
				against the human-reviewed text, a deterministic pass checks every quote
				and citation against its source, and anything superseded or overruled is
				flagged rather than quietly served. No support in the record, no answer.
			</p>
			<StatRow items={statTiles(stats)} />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Features — the rail of surfaces, then what holds the answers up
// ---------------------------------------------------------------------------

function features(stats: CorpusStats): ProductFeature[] {
	return [
		{
			id: "ask",
			label: "Ask",
			title: "Ask in plain English. Get the citation.",
			body: "The assistant shows its work as it goes — what it searched, which sections it read, and how many citations and quotations survived verification — then answers from that record and nothing else.",
			points: [
				"Every step of the research run, in the open",
				"Quotes and citations checked before you see them",
				"Follow any citation straight to the text",
			],
			shot: {
				src: "/marketing/corpus/assistant.png",
				alt: "The Hudson Corpus assistant answering a question with verified citations",
				caption: "Assistant — answer with verified citations",
			},
		},
		{
			id: "browse",
			label: "Browse",
			title: "The whole corpus, one library.",
			body: "Statutes, rules, and decisions in a single navigable workspace — search across everything at once or drill into one source and read it end to end.",
			points: [
				`Iowa ${sourceList(stats)} side by side`,
				"Jump from a search hit straight into context",
				"Live counts, so you know the coverage",
			],
			shot: {
				src: "/marketing/corpus/browse.png",
				alt: "The Hudson Corpus library / browse view",
				caption: "Browse — the unified library",
			},
		},
		{
			id: "read",
			label: "Read",
			title: "Read the source, not a summary.",
			body: "Open the effective text with its citation, effective date, and enacting session law attached — and follow inline links straight to the official publication.",
			points: [
				"Currently-in-force text, version-aware",
				"Citation & effective date on every provision",
				"One click to the official source",
			],
			shot: {
				src: "/marketing/corpus/reader.png",
				alt: "The Hudson Corpus statute / case reader",
				caption: "Reader — the effective text",
			},
		},
		{
			id: "search",
			label: "Search",
			title: "Search that finds what you mean.",
			body: "Full-text, trigram, and vector embeddings fused with Reciprocal Rank Fusion — type a citation number or describe the issue, and the on-point provision surfaces either way.",
			points: [
				"Keyword precision + semantic recall",
				"Filter by source, court, and date",
				"Ranked, cited results — not ten blue links",
			],
			shot: {
				src: "/marketing/corpus/search.png",
				alt: "The Hudson Corpus search results view",
				caption: "Search — hybrid results",
			},
		},
	];
}

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

function Features({ stats }: { stats: CorpusStats }) {
	return (
		<ProductSection
			id="features"
			tone="layer"
			label="Features"
			title="One workspace for the whole record."
			intro="Browse, read, search, and ask — four views of the same corpus, so a question that starts as a hunch ends on the page that governs it."
			link={{ label: "See the developer tools", href: MCP_PRODUCT_HREF }}
		>
			<div className="mt-14">
				<FeatureTabs features={features(stats)} />
			</div>

			<div className="mt-20 border-border border-t pt-10">
				<Eyebrow>Under the hood</Eyebrow>
				<h3 className="mt-6 max-w-3xl font-light text-2xl leading-snug sm:text-3xl">
					Why the answers hold up.
				</h3>
				<div className="mt-12 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{CAPABILITIES.map((c) => {
						const Icon = c.icon;
						return (
							<div key={c.title} className="bg-card p-8">
								<Icon className="size-5" strokeWidth={1.5} aria-hidden />
								<h4 className="mt-6 font-semibold text-[15px]">{c.title}</h4>
								<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
									{c.body}
								</p>
							</div>
						);
					})}
				</div>
			</div>
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Use cases — who reaches for it, and for what
// ---------------------------------------------------------------------------

const USE_CASES: UseCase[] = [
	{
		audience: "Litigation",
		title: "Check the brief before it is filed.",
		body: "Every citation in a draft validated against the corpus and every quotation checked verbatim against its source — the pass you would do by hand, done in one.",
	},
	{
		audience: "Advisory work",
		title: "Answer the client with the text in force.",
		body: "Provisions carry their effective date and enacting session law, and a version that is no longer the operative one says so before you rely on it.",
	},
	{
		audience: "Agency practice",
		title: "The rule beside the statute it implements.",
		body: "The Administrative Code sits in the same library as the Code, with the links between statute and rule mapped rather than left for you to chase.",
	},
	{
		audience: "Appellate research",
		title: "Follow the authority, not a summary.",
		body: "Search by issue or by citation, read the opinion itself, and see negative-treatment flags on decisions the citation graph says have moved.",
	},
	{
		audience: "Solos & small firms",
		title: "A research department that fits in a tab.",
		body: "No seat minimum, no per-search meter, and nothing to learn beyond asking the question the way you would ask a colleague.",
	},
	{
		audience: "Building with AI",
		title: "The same corpus, inside your own tools.",
		body: "Grounded retrieval behind a production MCP endpoint and an email address — read-only, keyed, and stamped with its source and as-of date.",
	},
];

function UseCases() {
	return (
		<ProductSection
			id="use-cases"
			tone="dark"
			label="Use cases"
			title="Where it fits in practice."
			intro="The same corpus, reached for in six different moments of a working week."
		>
			<UseCaseGrid items={USE_CASES} tone="dark" />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

const RESOURCES: Resource[] = [
	{
		type: "Data brief 001",
		title: "The Most-Cited Cases in Iowa",
		body: "The fifty decisions Iowa's appellate courts cite most, counted from every citation in the corpus — a list of workhorse standards, not landmarks, with the full table and method on the page.",
		href: "/data/most-cited-cases",
		cta: "Read the brief",
	},
	{
		type: "Series",
		title: "Data briefs",
		body: "One question per brief, answered from the full record and frozen when published: which cases do the work, what changes, who regulates.",
		href: "/data",
		cta: "See the series",
	},
	{
		type: "Writing",
		title: "Articles & analysis",
		body: "Our writing on grounded retrieval, citation verification, and where legal AI goes wrong — and what we do about it.",
		href: ARTICLES_HREF,
		cta: "Read the articles",
	},
	{
		type: "For developers",
		title: "The MCP endpoint",
		body: "Ten read-only tools over this corpus — citation lookup, hybrid search, version history, brief auditing — for Claude and any MCP client.",
		href: MCP_PRODUCT_HREF,
		cta: "See the tools",
	},
];

function Resources() {
	return (
		<ProductSection
			id="resources"
			label="Resources"
			title="What we learn, we publish."
			intro="The corpus is also a research instrument. When it answers a question about Iowa law that nobody has answered from the whole record before, we write it up — numbers frozen, methodology on the page."
			link={{ label: "All research & data", href: DATA_HREF }}
		>
			<ResourceCards items={RESOURCES} />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Pricing
// ---------------------------------------------------------------------------

function Pricing() {
	return (
		<ProductSection
			id="pricing"
			tone="layer"
			label="Pricing"
			title="One product. Terms you can plan around."
		>
			<PlanBand included="Every plan includes the full corpus, unlimited cited research, the citator's negative-treatment flags, the MCP connector, and the email assistant. Firm adds brief cite-check uploads, seats, and an org console." />
		</ProductSection>
	);
}
