// Products index — "/products", the nav's Products destination.
//
// IBM's /products model: the index is a CATALOG, not a set of essays. The hero
// stays; underneath it, each product is a tile with just enough to choose by —
// category, name, one paragraph, its capabilities, and its spec row — and every
// tile links to the landing page that carries the depth (screenshots, tool
// catalog, custody model, how-it-works). Nothing was lost in the trade: the
// Corpus screenshot lives on /products/corpus, the ten MCP tools on
// /products/mcp, the EDMSpro feature set on /products/edms.
//
// Two tiers, because the family really is two tiers: two products (Corpus,
// EDMSpro), then two more doors into Corpus (MCP, email). Server component
// (carries <metadata>).

import {
	FolderDownIcon,
	type LucideIcon,
	MailIcon,
	ScrollTextIcon,
	TerminalIcon,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
	CarbonPage,
	Eyebrow,
	HairlineLink,
	PageHero,
	SectionHead,
	SolidLink,
} from "@/components/marketing/carbon";
import {
	CONSULTING_HREF,
	CONTACT_HREF,
	EDMS_PRODUCT_HREF,
	EMAIL_PRODUCT_HREF,
	MCP_PRODUCT_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import { HeroCitationLattice } from "@/components/marketing/hero-citation-lattice";
import {
	type CorpusStats,
	corpusSourceNames,
	fetchCorpusStats,
	formatCount,
} from "@/lib/api";
import { APP_URL, MCP_URL } from "@/lib/site";

export const metadata: Metadata = {
	title: "Products — Hudson Legal Technologies",
	description:
		"Grounded legal research and court-filing management for Iowa practice: Hudson Corpus in the browser, over MCP, and by email — every answer verified against the effective text — and Hudson EDMSpro, which previews and saves filings straight from the docket, never through our servers.",
};

export default async function ProductsIndexPage() {
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Products"
				title={
					<>
						Research, verified.
						<br />
						Filings, filed.
					</>
				}
				lede="Everything we ship holds to one standard: accountable to the source. Hudson Corpus answers legal questions with citations verified against the effective text — in the browser, inside your AI tools, or by email. Hudson EDMSpro handles the other half of the day: getting filings off the docket and into your own files, without a copy ever passing through our servers."
				actions={
					<>
						<SolidLink href={APP_URL}>Open Hudson Corpus</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>Talk to our team</HairlineLink>
					</>
				}
				visual={<HeroCitationLattice />}
			/>
			<Catalog />
			<Doors />
			<SharedFoundation stats={stats} />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Tile scaffolding — one card shape, two sizes
// ---------------------------------------------------------------------------

type Product = {
	key: string;
	icon: LucideIcon;
	category: string;
	tag?: string;
	name: string;
	body: React.ReactNode;
	capabilities: string[];
	specs: { term: string; detail: string }[];
	cta: string;
	href: string;
};

function ProductTile({ p, size }: { p: Product; size: "lg" | "sm" }) {
	const Icon = p.icon;
	return (
		<Link
			href={p.href}
			className="group flex flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8] lg:p-10"
		>
			<div className="flex items-start justify-between gap-6">
				<div>
					<Eyebrow>{p.category}</Eyebrow>
					<h3
						className={
							size === "lg" ? "mt-5 font-light text-3xl" : "mt-5 text-2xl"
						}
					>
						{p.name}
					</h3>
				</div>
				<Icon
					aria-hidden
					className="size-6 shrink-0 text-[#0f62fe]"
					strokeWidth={1.25}
				/>
			</div>
			{p.tag && (
				<p className="mt-4 inline-flex w-fit border border-[#0f62fe] px-2 py-0.5 font-mono text-[#0f62fe] text-[11px] uppercase tracking-[0.16em]">
					{p.tag}
				</p>
			)}
			<p className="mt-5 max-w-xl text-[15.5px] text-muted-foreground leading-[1.7]">
				{p.body}
			</p>
			<ul className="mt-7 flex flex-wrap gap-2">
				{p.capabilities.map((c) => (
					<li
						key={c}
						className="border border-border px-2.5 py-1 font-mono text-[11.5px] text-foreground/70"
					>
						{c}
					</li>
				))}
			</ul>
			<dl className="mt-auto grid grid-cols-2 gap-x-6 gap-y-3 border-border border-t pt-6 sm:grid-cols-3">
				{p.specs.map((s) => (
					<div key={s.term}>
						<dt className="font-mono text-[10.5px] text-muted-foreground uppercase tracking-[0.18em]">
							{s.term}
						</dt>
						<dd className="mt-1.5 text-[13.5px] leading-snug">{s.detail}</dd>
					</div>
				))}
			</dl>
			<span className="mt-8 flex items-center justify-between font-medium text-[#0f62fe] text-sm">
				{p.cta}
				<span
					aria-hidden
					className="transition-transform group-hover:translate-x-0.5"
				>
					→
				</span>
			</span>
		</Link>
	);
}

// ---------------------------------------------------------------------------
// 01 — The two products
// ---------------------------------------------------------------------------

const PRODUCTS: Product[] = [
	{
		key: "corpus",
		icon: ScrollTextIcon,
		category: "Legal research",
		tag: "Flagship",
		name: "Hudson Corpus",
		body: "Ask a question in plain language; the assistant searches the corpus, reads the controlling text, and answers with citations that link to the source — each one verified before you see it. Browse the library, read the effective text, and search across everything from one box.",
		capabilities: [
			"verified citations",
			"semantic + full-text search",
			"effective-date history",
			"official-source links",
		],
		specs: [
			{ term: "Surface", detail: "Web app" },
			{ term: "Status", detail: "Live in beta" },
			{ term: "Best for", detail: "Day-to-day research" },
		],
		cta: "Explore Hudson Corpus",
		href: PRODUCT_HREF,
	},
	{
		key: "edms",
		icon: FolderDownIcon,
		category: "Court filings",
		name: "Hudson EDMSpro",
		body: "A Chrome extension for Iowa's EDMS. Preview any filing in a panel beside the docket, then download it — one or all — under clean, consistent names drawn from your own rules, not the court's opaque ones. Documents move from the court straight to you, never through Hudson's servers.",
		capabilities: [
			"docket-side PDF preview",
			"smart local download",
			"download all",
			"your naming rules",
			"cloud save — next",
		],
		specs: [
			{ term: "Surface", detail: "Chrome extension" },
			{ term: "Status", detail: "Early access" },
			{ term: "Best for", detail: "Docket triage & downloads" },
		],
		cta: "Explore Hudson EDMSpro",
		href: EDMS_PRODUCT_HREF,
	},
];

function Catalog() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="The products"
					title="Two products, one standard."
				/>
				<div className="mt-14 grid gap-px border border-border bg-border lg:grid-cols-2">
					{PRODUCTS.map((p) => (
						<ProductTile key={p.key} p={p} size="lg" />
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — The other two doors into Hudson Corpus
// ---------------------------------------------------------------------------

const DOORS: Product[] = [
	{
		key: "mcp",
		icon: TerminalIcon,
		category: "For your AI stack",
		name: "MCP endpoint",
		body: (
			<>
				A production MCP endpoint at{" "}
				<span className="font-mono text-[0.95em] text-foreground">
					{MCP_URL}
				</span>{" "}
				— the same grounded corpus for Claude Desktop, Claude Code, and any
				MCP-capable agent. Ten read-only tools, every response stamped with its
				official source and as-of date.
			</>
		),
		capabilities: ["ten read-only tools", "as-of dates", "no write access"],
		specs: [
			{ term: "Surface", detail: "MCP · streamable HTTP" },
			{ term: "Auth", detail: "OAuth 2.0 · X-API-Key" },
			{ term: "Best for", detail: "Agents & integrations" },
		],
		cta: "Explore the MCP endpoint",
		href: MCP_PRODUCT_HREF,
	},
	{
		key: "email",
		icon: MailIcon,
		category: "For your inbox",
		name: "Email assistant",
		body: "Send a question to the assistant's address and a verified answer comes back — citations linked to the source, official PDFs attached on request, follow-ups in the same thread. The full verification gate runs on every reply before it sends.",
		capabilities: ["reply with citations", "PDFs on request", "threaded"],
		specs: [
			{ term: "Surface", detail: "Plain email" },
			{ term: "Status", detail: "In pilot — allowlisted" },
			{ term: "Best for", detail: "Questions on the go" },
		],
		cta: "Explore the email assistant",
		href: EMAIL_PRODUCT_HREF,
	},
];

function Doors() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-28">
				<SectionHead
					n="02"
					label="More ways in"
					title="Two more doors into the same corpus."
				/>
				<div className="mt-14 grid gap-px border border-border bg-border lg:grid-cols-2">
					{DOORS.map((p) => (
						<ProductTile key={p.key} p={p} size="sm" />
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — The shared foundation + CTA
// ---------------------------------------------------------------------------

// The corpus line is fetched, not typed: the literal that used to live here
// (105,734 documents, three sources) had gone stale in the direction that hurts
// most — it understated the breadth we lead on. See lib/api.ts.
function foundation(stats: CorpusStats): { title: string; body: string }[] {
	return [
		{
			title: "One verified corpus",
			body: `${corpusSourceNames(stats)} — ${formatCount(stats.documents)} documents, semantically indexed, with treatment flags on decisions.`,
		},
		{
			title: "One verification gate",
			body: "Every research surface runs the same deterministic citation-and-quote check before an answer reaches you.",
		},
		{
			title: "One source of truth",
			body: "Everything traces to the official publication — effective dates, session laws, and links to legis.iowa.gov.",
		},
		{
			title: "One custody model",
			body: "Your documents are yours. EDMSpro moves filings from the court straight to your files — Hudson never receives, stores, or reads them.",
		},
	];
}

function SharedFoundation({ stats }: { stats: CorpusStats }) {
	const FOUNDATION = foundation(stats);
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-24">
				<SectionHead
					n="03"
					label="Shared foundation"
					title="Different doors. Same standard behind them."
				/>
				<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
					{FOUNDATION.map((f) => (
						<div key={f.title} className="bg-card p-8">
							<Eyebrow>{f.title}</Eyebrow>
							<p className="mt-4 text-[14.5px] text-muted-foreground leading-relaxed">
								{f.body}
							</p>
						</div>
					))}
				</div>
				<div className="mt-16 flex flex-col gap-10 border-border border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							Start where your work is.
						</h2>
						<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
							The app is open in beta; MCP keys come with your account; the
							email assistant is in limited pilot; EDMSpro early access is open
							to Solo and Firm plans.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={CONTACT_HREF} tone="light">
							Contact us
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
